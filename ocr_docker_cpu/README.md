# OCR + Flask Docker Project

## Overview

This project contains **two independent services** packaged using Docker:

1. **OCR Service**
   * A local Python service running in a loop
   * ocr_service read and process 2 images from a given external folder (/image_folder) outside of the project directory
   * Uses **PaddleOCR (GPU-accelerated)** to process images in batches
   * Writes recognized text into an **SQLite database**
   * Communicates via a **Unix domain socket**
   * Automatically restarts on crashes using Docker restart policy

2. **Web Service (Flask)**
   * A lightweight Flask application  
   * Displays SQLite database on a web page
   * Hosted using **Gunicorn**
   * Also protected by Docker restart policy

This system is **fully offline** and designed to be **deployed on the client’s machine**.
No cloud services, no Docker Hub, no external APIs.

## Project Structure

ocr_docker/
│
├── ocr/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── ocr_service.py
│ 
├── flask/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py
│   └── templates/index.html
│
│── data/
│   ├── temp.png    
│   ├── ocr_data.db
│   └── paddle_models/whl
│
├── ocr_database.db
├── docker-compose.yml
├── .dockerignore
├── .gitignore
└── README.md


## Key Design Decisions

* **Separated services**
  OCR and Flash run independently to avoid mutual failure.

* **Unix Domain Socket**
  Used instead of TCP for local IPC, lower overhead and more secure.

* **SQLite with Access Control**
  * OCR service: read + write
  * Flask service: read + write

* **No Docker Hub dependency**
  All images are built locally from source.

* **Minimal dependency overlap**
  Each service has its own `requirements.txt`.


## Requirements
* Docker ≥ 20.x
* Docker Compose ≥ v2
* NVIDIA GPU + CUDA (for OCR service)
* NVIDIA Container Toolkit installed


## Build & Run
### 1. Clone the Repository
```bash
git clone <your-repo-url>
cd project-root
```

### 2. Build and Start Services
```bash
docker compose up --build -d
```

## Service Details

### OCR Service
* Runs continuously in a loop
* Listens for processing signals
* Processes images in batches
* Stores results in `ocr_data.db`
* Uses PaddleOCR with GPU acceleration

Restart behavior:

* Handled **only by Docker** (`restart: always`)

### Flask Service
* Flask + Gunicorn
* Displays `ocr_data.db` on a webpage
* `ocr_data.db` read only

Access the web interface at:

http://localhost:5000

Restart behavior:
* Gunicorn manages worker failures
* Docker handles container restarts

## Database Sharing
The SQLite database is mounted as a shared volume: /data/ocr_data.db


Permissions:
* OCR service: read/write
* Flash service:  read only

This prevents accidental data corruption from the web layer.


## Stopping the System
```bash
docker compose down
```

---
## Logs & Debugging
View logs for each service:

```bash
docker compose logs ocr_service
docker compose logs web_service
```

Restart a single service:
```bash
docker compose restart ocr_service
```

---
## Deployment Notes (Client Machines)

* Clients only need:
  * Docker
  * NVIDIA drivers (if GPU OCR is required)
* No internet connection required after setup
* Entire system runs locally

---

## License
Internal / Proprietary
Not intended for public redistribution without permission.

