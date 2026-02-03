import socket
import time

def send_signal_network():  #different PCs, work for both Ubuntu and Windows
    SERVER_IP = "172.27.52.145"  # replace with server's LAN IP
    PORT = 6000

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((SERVER_IP, PORT))
    client.sendall(b"IMAGE_READY")
    client.close()
    print("IMAGE_READY sent")

def send_signal_local():    #same PC
    SOCKET_PATH = "/home/zzq/ocr_docker/run/ipc_image.sock"
    
    client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    client.connect(SOCKET_PATH)
    client.sendall(b"IMAGE_READY")
    client.close()

def listen_signal_local():
    import os
    SOCKET_PATH = "/tmp/ipc_image.sock"
    HOST = "127.0.0.1"  # localhost
    PORT = 50001

    if OS_TYPE=="Ubuntu":
        if os.path.exists(SOCKET_PATH):
            os.remove(SOCKET_PATH)

        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET_PATH)
        server.listen(1)
        print("Waiting for IPC image signal...")

        while True:
            conn, _ = server.accept()
            msg = conn.recv(1024).decode().strip()
            conn.close()

            if msg == "IMAGE_READY":
                print("IPC signal received")
                return
    else:     # Windows
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(1)
        print("Waiting for IPC image signal...")

        conn, addr = server.accept()
        msg = conn.recv(1024).decode().strip()
        conn.close()
        server.close()

        if msg == "IMAGE_READY":
            print("IPC signal received")

def listen_signal_network():  #different PCs, work for both Ubuntu and Windows
    HOST = "0.0.0.0"  # listen on all network interfaces
    PORT = 5000       # pick a port >1024

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(1)
    print(f"Waiting for IPC image signal on {PORT}...")

    while True:
        conn, addr = server.accept()
        msg = conn.recv(1024).decode().strip()
        print(f"Message from {addr}: {msg}")
        conn.close()
        if msg == "IMAGE_READY":
            print("IPC signal received")

while True:
    send_signal_network()
    time.sleep(20)

