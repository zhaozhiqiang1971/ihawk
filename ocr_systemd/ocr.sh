#!/bin/bash

set -e

cd ~/ocr_systemd
source venv/bin/activate

exec python3 ocr.py
