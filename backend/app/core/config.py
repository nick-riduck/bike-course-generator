import os
from dotenv import load_dotenv

load_dotenv()

# Storage Configuration
STORAGE_TYPE = os.getenv("STORAGE_TYPE", "LOCAL") # 'LOCAL' or 'GCS'
STORAGE_BASE_DIR = os.getenv("STORAGE_BASE_DIR", "storage")
GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME", "riduck-course-data")

# Valhalla Configuration
VALHALLA_URL = os.getenv("VALHALLA_URL", "http://localhost:8002")

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname": os.getenv("DB_NAME", "postgres")
}
