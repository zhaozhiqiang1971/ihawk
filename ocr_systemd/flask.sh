#!/usr/bin/env bash
set -e

cd ~/ocr_systemd
source venv/bin/activate

gunicorn app:app --bind 127.0.0.1:8000
