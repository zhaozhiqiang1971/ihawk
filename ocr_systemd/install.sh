#!/usr/bin/env bash
set -e

REPO_URL="https://github.com/zhaozhiqiang1971/ihawk.git"
INSTALL_DIR="$HOME/ocr_systemd"
SERVICE_NAME="ocr"

echo "📥 Cloning repository..."
git clone "$REPO_URL" "$INSTALL_DIR"

cd "$INSTALL_DIR"

echo "🐍 Creating Python venv..."
$PYTHON_BIN -m venv venv

echo "⬆️ Upgrading pip..."
./venv/bin/pip install --upgrade pip

echo "📦 Installing dependencies..."
./venv/bin/pip install -r requirements.txt

echo "🧩 Generating systemd service..."
sed \
  -e "s|%INSTALL_DIR%|$INSTALL_DIR|g" \
  -e "s|%USER%|$USER|g" \
  "$INSTALL_DIR/ocr.service.template" \
  | sudo tee /etc/systemd/system/$SERVICE_NAME.service > /dev/null

echo "🔄 Reloading systemd..."
sudo systemctl daemon-reexec
sudo systemctl daemon-reload

echo "🚀 Enabling service..."
sudo systemctl enable $SERVICE_NAME
sudo systemctl start $SERVICE_NAME

echo "✅ OCR service installed and running"
