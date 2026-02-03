# OCR + Flask Systemd Project

## Overview
This project contains **two independent services**:

1. **OCR**
   * A local Python service running in a loop
   * ocr_service read and process images from /image_folder
   * Uses **PaddleOCR (GPU-accelerated)** to process images in batches
   * Writes recognized text into an **SQLite database** `/data/ocr_data.db`
   * Communicates via a **Unix domain socket**
   * Automatically restarts on crashes using Systemd

2. **Flask**
   * A lightweight Flask application  
   * Displays SQLite database on a web page
   * Hosted using **Gunicorn**
   * Also protected by Systemd restart policy

## Project Structure
ocr_systemd/
│
├── templates/  
│   └── index.html
│
├── image_folder/  
│   └── image1.jpeg
│
├── data/
│   ├── temp.png    
│   └── ocr_data.db
│
├── paddle_models/
│   └── whl/
│
├── ocr.py
├── app.py
├── Requirements.txt
└── README.md


## Key Design Decisions
* **Separated services**
  OCR and Flask run independently to avoid mutual failure.


## Service Details

### OCR Service
* Runs continuously in a loop in `ocr.py`
* Listens for processing signals
* Processes images in batches
* Stores results in `\data\ocr_data.db`
* Uses PaddleOCR with GPU acceleration

### Flask Service
* Flask + Gunicorn in `app.py`
* Displays `\data\ocr_data.db` on a webpage

Access the web interface at:
http://localhost:5000

Restart behavior:
* Gunicorn manages worker failures
* Systemd handles restarts
