# python: 3.10
# paddlepaddle-gpu: 2.6.2
# paddleocr: 2.7.0.3
# numpy: 1.26.4
# opencv-python: 4.6.0.66

import os
import re
import time
import shutil
from pathlib import Path
import sqlite3
from datetime import datetime
from PIL import Image, ImageEnhance
import logging
import socket
import signal
    
from paddleocr import PaddleOCR

# Use environment variables for paths, fallback to defaults
# NOTE: Keep these in sync with docker-compose.yml and README.md
IMG_DIR = Path(os.getenv("IMG_DIR", "/image_folder"))
DB_FILE = Path(os.getenv("DB_FILE", "/data/ocr_data.db"))
TEMP_IMAGE_PATH = Path(os.getenv("TEMP_IMAGE_PATH", "/data/temp.png"))


IMAGE_EXTS = ('.png', '.jpg', '.jpeg')
CAR_PREFIX = ('XD', 'XE', 'XF')
CAR_NUM_PATTERN = re.compile(r'^(\d{4}[A-Z]$|\d{3}[A-Z]$|\d{3}$)')
CONTAINER_PATTERN = re.compile(r'^([A-Z]{4}|\d{6})')

IPC_LISTEN_HOST = "0.0.0.0"
IPC_LISTEN_PORT = 6000

IPC_REPLY_IP = os.getenv("IPC_REPLY_IP", "127.0.0.1")
IPC_REPLY_PORT = int(os.getenv("IPC_REPLY_PORT", "5000"))


logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True  # optional, ensures config is applied even if logger already exists
)

logging.getLogger("ppocr").setLevel(logging.ERROR)


ocr = None
RUNNING = True

def shutdown_handler(*_):
    global RUNNING
    logging.info("Shutdown signal received, exiting OCR service...")
    RUNNING = False

signal.signal(signal.SIGTERM, shutdown_handler)
signal.signal(signal.SIGINT, shutdown_handler)

# --------------------- Database ---------------------
def record_to_db(timestamp, car_code, container_code, match_status):
    query = """
            INSERT INTO codes (timestamp, car_code, container_code, match_status)
            VALUES (?, ?, ?, ?)
        """

    with sqlite3.connect(DB_FILE) as conn:
        conn.execute(query, (
            timestamp,
            car_code,
            container_code,
            match_status
        ))

# --------------------- IPC Handling ---------------------
def start_ipc_server():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((IPC_LISTEN_HOST, IPC_LISTEN_PORT))
    server.listen(5)
    logging.info("IPC server listening on %s:%s", IPC_LISTEN_HOST, IPC_LISTEN_PORT)
    return server
    
def listen_ipc_signal() -> str:
    """Block until a single IPC message is received, then return it.

    The external system should connect and send e.g. 'IMAGE_READY'.
    """
    HOST = "0.0.0.0"  # listen on all network interfaces
    PORT = 6000       # pick a port >1024

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    logging.info("Waiting for IPC image signal on port %s...", PORT)

    conn, _ = server.accept()
    msg = conn.recv(1024).decode().strip()
    conn.close()
    server.close()

    logging.info("IPC message received: %s", msg)
    return msg

def send_signal_to_ipc(message: str):
    SERVER_IP = "172.27.42.157"  # replace with server's LAN IP
    PORT = 5000

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((SERVER_IP, PORT))
    client.sendall(message.encode())
    client.close()
    logging.info("IPC message sent: %s", message)

# --------------------- OCR Processing ---------------------
def init_ocr():
    global ocr

    logging.info("Initializing PaddleOCR (GPU)...")
    ocr = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        use_static=False,
        use_gpu=True, 
        det_model_dir="/home/zzq/.paddleocr/whl/det/en_PP-OCRv4_det_infer",
    	rec_model_dir="/home/zzq/.paddleocr/whl/rec/en_PP-OCRv4_rec_infer",
    	cls_model_dir="/home/zzq/.paddleocr/whl/cls/en_ppocr_mobile_v2.0_cls_infer",
    )

def extract_car_and_container_codes(list_text):
    car_license = extract_car_license_code(list_text)
    container_code = "" if car_license else extract_container_code(list_text)
    return car_license, container_code

def extract_car_license_code(list_text):
    prefix = next((t for t in list_text if t.startswith(CAR_PREFIX)), "")
    if not prefix:    return ""

    number = next((t for t in list_text if CAR_NUM_PATTERN.match(t)), "")
    return prefix + number if number else prefix

def extract_container_code(list_text):
    matches = [t for t in list_text if CONTAINER_PATTERN.match(t)]
    return max(matches, key=len) if matches else ""

def ocr_text_extraction(image_path):
    global ocr

    logging.info("before ocr.ocr")
    result = ocr.ocr(str(image_path), cls=True)
    logging.info("after ocr.ocr")
    
    if not result or result == [None]:
        return "", ""

    texts = [
        text
        for block in result
        for (_, (text, _)) in block
    ]

    car_license, container_code = extract_car_and_container_codes(texts)

    if car_license:
        shutil.copy2(image_path, TEMP_IMAGE_PATH)

    return car_license, container_code

def ocr_text_extraction_with_image_enhancement(image_path):
    global ocr

    with Image.open(image_path) as img:
        img = ImageEnhance.Contrast(img).enhance(2.0)
        result = ocr.ocr(img, cls=True)

    if not result or result == [None]:
        return "", ""

    texts = [
        text
        for block in result
        for (_, (text, _)) in block
    ]

    car_license, container_code = extract_car_and_container_codes(texts)

    if car_license:
        shutil.copy2(image_path, TEMP_IMAGE_PATH)

    return car_license, container_code

# --------------------- Image Handling ---------------------
def get_latest_images(limit=2):
    files = [
        IMG_DIR / f for f in os.listdir(IMG_DIR)
        if f.lower().endswith(IMAGE_EXTS)
    ]
    files.sort(key=os.path.getmtime, reverse=True)
    return files[:limit]

def is_image_readable(path):
    try:
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False

# --------------------- Processing ---------------------
def process_latest_images():
    logging.info("enter process_latest_images()")
    image_files = get_latest_images(4)
    if len(image_files) ==0:
        send_signal_to_ipc("retake images")
        return

    car_code, container_code  = "", ""
    for img_file in image_files:
        if not is_image_readable(img_file):
            logging.info("invalid image", img_file)
            continue
            
        logging.info("enter ocr_text_extraction")	
        logging.info(img_file)					
        car, container = ocr_text_extraction(img_file)
        logging.info("after ocr_text_extraction")

        if not car and not container:
            car, container = ocr_text_extraction_with_image_enhancement(img_file)

        if car and len(car) > len(car_code):
            car_code = car

        if container and len(container) > len(container_code):
            container_code = container

    # write into database
    if car_code or container_code:
        timestamp_value = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        match_status_value = 'Yes'
        record_to_db(timestamp_value, car_code, container_code, match_status_value)
    else:
        logging.warning("OCR failed, requesting retake")
        send_signal_to_ipc("retake images")

# ---------------------------- main ------------------------
def main():
    logging.info("main()")
    init_ocr()
    logging.info("before start_ipc_server()")
    server = start_ipc_server()
    logging.info("after start_ipc_server()")

    while RUNNING:
        try:
            conn, addr = server.accept()
            msg = conn.recv(1024).decode().strip()
            conn.close()

            logging.info("IPC message from %s: %s", addr, msg)

            if msg == "IMAGE_READY":
                process_latest_images()

        except Exception as e:
            if RUNNING:
                logging.error("IPC server error: %s", e)

    server.close()
    logging.info("OCR service stopped")

def function_test():
    
    logging.info("AAA")
    
    ocr1 = PaddleOCR(
        use_angle_cls=True,
        lang="en",
        use_static=False,
        use_gpu=True,  
    )
    	
    logging.info("BBB")
    
    image_files = get_latest_images(4)
    
    for img_file in image_files:
    	logging.info(img_file)
    	result = ocr1.ocr(str(img_file), cls=True)
    	logging.info("after ocr.ocr")
    
    	if not result or result == [None]:
        	return "", ""

    	texts = [
        	text
        	for block in result
        	for (_, (text, _)) in block
    	]	
    	
    	logging.info(texts)  

if __name__ == "__main__":
    #main()       
    function_test()
    
