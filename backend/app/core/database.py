import psycopg2
from psycopg2.pool import SimpleConnectionPool
from psycopg2.extras import RealDictCursor
from app.core.config import DB_CONFIG

_pool = None

class PooledConnection:
    def __init__(self, pool, conn):
        self._pool = pool
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def cursor(self, *args, **kwargs):
        kwargs['cursor_factory'] = RealDictCursor
        return self._conn.cursor(*args, **kwargs)

    def close(self):
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)
        
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

def get_db_conn():
    global _pool
    if _pool is None:
        _pool = SimpleConnectionPool(1, 10, **DB_CONFIG)
    
    conn = _pool.getconn()
    
    return PooledConnection(_pool, conn)
