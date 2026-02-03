"""
Unified WSGI Application for PaddleOCR Service
"""
import os
import sqlite3
from pathlib import Path
import logging
from flask import Flask, jsonify, render_template, send_from_directory, abort

logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

# --------------------- App ---------------------
app = Flask(__name__)

# --------------------- Paths ---------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_FILE = DATA_DIR / "ocr_data.db"
TEMP_IMAGE_PATH = DATA_DIR / "temp.png"
TEMP_IMAGE_DIR = DATA_DIR
TEMP_IMAGE_FILENAME = TEMP_IMAGE_PATH.name

# --------------------- Database ---------------------
def fetch_codes(limit: int = 5):
    """Fetch codes from database, returns (data, latest_idx)"""
    query = """
            SELECT idx, timestamp, car_code, container_code, match_status 
            FROM codes
            ORDER BY idx DESC
            LIMIT ?
        """

    if not DB_FILE.exists():
        logger.warning("Database file does not exist: %s", DB_FILE)
        return [], 0

    with sqlite3.connect(f"file:{DB_FILE}?mode=ro", uri=True, timeout=3) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, (limit,)).fetchall()

    data_rows = [dict(row) for row in reversed(rows)]
    latest_idx = data_rows[-1]["idx"] if data_rows else 0

    return data_rows, latest_idx

# --------------------- Routes ---------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def data():
    rows, image_version = fetch_codes()
    return jsonify({
        "rows": rows,
        "image_version": image_version
    })

@app.route("/temp.png")
def serve_temp_image():
    if not TEMP_IMAGE_PATH.exists():
        abort(404)

    return send_from_directory(
        TEMP_IMAGE_PATH.parent,
        TEMP_IMAGE_PATH.name
    )

# --------------------- Entry Point ---------------------
if __name__ == "__main__":
    # For development only - use Gunicorn in Docker (not used in production)       
    app.run(host='0.0.0.0', port=5000, debug=False)
