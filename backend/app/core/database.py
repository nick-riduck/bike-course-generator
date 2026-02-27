import psycopg2
from psycopg2.extras import RealDictCursor
from app.core.config import DB_CONFIG

def get_db_conn():
    return psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
