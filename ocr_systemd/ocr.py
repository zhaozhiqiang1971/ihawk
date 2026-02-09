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

# --------------------- Paths ---------------------
# DATA_DIR = Path("/home/zzq/ocr_systemd/data")
# IMG_DIR = Path("/home/zzq/image_folder")
# DB_FILE = Path("/home/zzq/ocr_systemd/data/ocr_data.db")
# TEMP_IMAGE_PATH = Path("/home/zzq/ocr_systemd/data/temp.png")

#project path
PROJ_DIR = Path(__file__).resolve().parent
DB_FILE = PROJ_DIR / "data/ocr_data.db"
TEMP_IMAGE_PATH = PROJ_DIR / "data/temp.png"

#change the path manually
IMG_DIR = Path("/home/zzq/image_folder")
# Unix domain socket path for IPC
SOCKET_PATH = "/home/zzq/ocr_tmp/ipc_image.sock"  #receive from IPC
SOCKET_PATH2 = "/home/zzq/ocr_tmp/ocr_result.sock" #send to IPC

# --------------------- Config ---------------------
IMAGE_EXTS = ('.png', '.jpg', '.jpeg')
CAR_PREFIX = ('XD', 'XE', 'XF')
CAR_NUM_PATTERN = re.compile(r'^(\d{4}[A-Z]$|\d{3}[A-Z]$|\d{3}$)')
CONTAINER_PATTERN = re.compile(r'^([A-Z]{4}|\d{6})')

# PaddleOCR
ocr = None
RUNNING = True

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    force=True  # optional, ensures config is applied even if logger already exists
)
logging.getLogger("ppocr").setLevel(logging.ERROR)

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
    # Local Unix socket client
    os.makedirs(os.path.dirname(SOCKET_PATH), exist_ok=True)
    
    # Remove stale socket if exists. This is important, otherwise bind() will fail next time.
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)
    server.settimeout(1.0)
    os.chmod(SOCKET_PATH, 0o666)  # allows all users R/W
    
    logging.info("IPC Unix socket listening at %s", SOCKET_PATH)
    return server

def send_signal_to_ipc(message: str):
    for _ in range(50):  # retry for ~5 seconds
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(SOCKET_PATH2)
            client.sendall(message.encode())
            client.close()
            print("IPC_RESULTsent")
            return
        except ConnectionRefusedError:
            time.sleep(0.1)

    raise RuntimeError("IPC_RESULT service not available")

# --------------------- OCR Processing ---------------------
def init_ocr():
    global ocr

    try:
        logging.info("Initializing PaddleOCR...")
        ocr = PaddleOCR(
            use_angle_cls=True,
            lang="en",
            use_static=False,
            #use_gpu=True, 
            det_model_dir="/home/zzq/ocr_systemd/paddle_models/det",
            rec_model_dir="/home/zzq/ocr_systemd/paddle_models/rec",
            cls_model_dir="/home/zzq/ocr_systemd/paddle_models/cls"
            )
    except Exception:
        logging.exception("Failed to initialize PaddleOCR")
        sys.exit(1)

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
    result = ocr.ocr(str(image_path), cls=True)
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
    image_files = get_latest_images(2)
    if len(image_files) != 2:
        send_signal_to_ipc("retake images")
        return

    car_code, container_code  = "", ""
    for img_file in image_files:
        if not is_image_readable(img_file):
            continue

        car, container = ocr_text_extraction(img_file)

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
    init_ocr()
    server = start_ipc_server()      

    while RUNNING:
        try:
            conn, addr = server.accept()
            msg = conn.recv(1024).decode().strip()
            conn.close()

            logging.info("IPC message received: %s", msg)

            if msg == "IMAGE_READY":
                process_latest_images()

        except socket.timeout:
            continue
            
        except Exception as e:
            if RUNNING:
                logging.error("IPC error: %s", e)

    server.close()
    # Cleanup socket file on exit
    if os.path.exists(SOCKET_PATH):
        os.remove(SOCKET_PATH)
        
    logging.info("OCR service stopped!")

if __name__ == "__main__":
    main()
