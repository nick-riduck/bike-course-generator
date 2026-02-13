import psycopg2
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()

# DB 설정 (환경변수 없으면 기본값 사용)
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5433")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "postgres")

def init_db():
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )
    cur = conn.cursor()
    
    print("WARNING: This script will DROP all existing tables and recreate them.")
    
    try:
        # 1. Extension
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
        
        # 2. Drop Tables
        cur.execute("DROP TABLE IF EXISTS auth_mapping_temp CASCADE;")
        cur.execute("DROP TABLE IF EXISTS route_tags CASCADE;")
        cur.execute("DROP TABLE IF EXISTS tags CASCADE;")
        cur.execute("DROP TABLE IF EXISTS route_segments CASCADE;")
        cur.execute("DROP TABLE IF EXISTS route_stats CASCADE;")
        cur.execute("DROP TABLE IF EXISTS routes CASCADE;")
        cur.execute("DROP TABLE IF EXISTS segments CASCADE;")
        cur.execute("DROP TABLE IF EXISTS user_tokens CASCADE;")
        cur.execute("DROP TABLE IF EXISTS users CASCADE;")
        
        # 3. Create Types (Drop first)
        cur.execute("DROP TYPE IF EXISTS user_status CASCADE;")
        cur.execute("DROP TYPE IF EXISTS route_status CASCADE;")
        cur.execute("DROP TYPE IF EXISTS auth_provider CASCADE;")
        cur.execute("DROP TYPE IF EXISTS token_status CASCADE;")

        cur.execute("CREATE TYPE user_status AS ENUM ('ACTIVE', 'BANNED', 'PENDING_DELETION', 'DELETED');")
        cur.execute("CREATE TYPE route_status AS ENUM ('PUBLIC', 'PRIVATE', 'LINK_ONLY', 'DELETED');")
        cur.execute("CREATE TYPE auth_provider AS ENUM ('RIDUCK', 'GOOGLE', 'STRAVA');")
        cur.execute("CREATE TYPE token_status AS ENUM ('ACTIVE', 'EXPIRED', 'REVOKED');")

        # 4. Create Tables
        
        # Users
        print("Creating table: users...")
        cur.execute("""
            CREATE TABLE users (
                id BIGINT GENERATED ALWAYS AS IDENTITY (START WITH 100000000) PRIMARY KEY,
                uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
                riduck_id INTEGER UNIQUE, -- Nullable for temp auth
                username VARCHAR(50) NOT NULL,
                email VARCHAR(255),
                profile_image_url VARCHAR(255),
                status user_status DEFAULT 'ACTIVE' NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE INDEX idx_users_status_email ON users(status, email);")
        cur.execute("CREATE INDEX idx_users_status_riduck_id ON users(status, riduck_id);")

        # UserTokens (Optional for now)
        print("Creating table: user_tokens...")
        cur.execute("""
            CREATE TABLE user_tokens (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                user_id BIGINT NOT NULL,
                provider auth_provider NOT NULL,
                access_token TEXT NOT NULL,
                refresh_token TEXT,
                expires_at TIMESTAMP WITH TIME ZONE,
                status token_status DEFAULT 'ACTIVE' NOT NULL,
                scope TEXT,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE INDEX idx_user_tokens_status_access ON user_tokens(status, access_token);")

        # AuthMappingTemp (Dev Only)
        print("Creating table: auth_mapping_temp...")
        cur.execute("""
            CREATE TABLE auth_mapping_temp (
                provider VARCHAR(50) NOT NULL,
                provider_uid VARCHAR(128) NOT NULL,
                user_id BIGINT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (provider, provider_uid)
            );
        """)

        # Routes
        print("Creating table: routes...")
        cur.execute("""
            CREATE TABLE routes (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
                route_num SERIAL UNIQUE NOT NULL,
                user_id BIGINT NOT NULL,
                parent_route_id BIGINT,
                title VARCHAR(255) NOT NULL,
                description TEXT,
                status route_status DEFAULT 'PUBLIC' NOT NULL,
                thumbnail_url VARCHAR(255),
                is_verified BOOLEAN DEFAULT FALSE NOT NULL,
                data_file_path TEXT NOT NULL,
                summary_path GEOMETRY(LineString, 4326),
                start_point GEOMETRY(Point, 4326),
                distance INTEGER NOT NULL,
                elevation_gain INTEGER NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE INDEX idx_routes_status_user ON routes(status, user_id);")
        cur.execute("CREATE INDEX idx_routes_summary_path ON routes USING GIST (summary_path);")

        # RouteStats
        print("Creating table: route_stats...")
        cur.execute("""
            CREATE TABLE route_stats (
                route_id BIGINT PRIMARY KEY,
                view_count INTEGER DEFAULT 0 NOT NULL,
                download_count INTEGER DEFAULT 0 NOT NULL,
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # Segments
        print("Creating table: segments...")
        cur.execute("""
            CREATE TABLE segments (
                id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                uuid UUID DEFAULT gen_random_uuid() UNIQUE NOT NULL,
                creator_id BIGINT,
                name VARCHAR(100) NOT NULL,
                type VARCHAR(50) NOT NULL,
                geometry GEOMETRY(LineString, 4326),
                start_point GEOMETRY(Point, 4326),
                end_point GEOMETRY(Point, 4326),
                length INTEGER NOT NULL,
                avg_grade FLOAT NOT NULL,
                elevation_gain INTEGER NOT NULL,
                is_verified BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
            );
        """)
        cur.execute("CREATE INDEX idx_segments_start_point ON segments USING GIST (start_point);")

        # RouteSegments
        print("Creating table: route_segments...")
        cur.execute("""
            CREATE TABLE route_segments (
                route_id BIGINT NOT NULL,
                segment_id BIGINT NOT NULL,
                sequence INTEGER NOT NULL,
                start_index INTEGER NOT NULL, 
                end_index INTEGER NOT NULL,
                PRIMARY KEY (route_id, sequence)
            );
        """)

        # Tags
        print("Creating table: tags...")
        cur.execute("""
            CREATE TABLE tags (
                id SERIAL PRIMARY KEY,
                names JSONB NOT NULL, 
                slug VARCHAR(50) UNIQUE NOT NULL,
                type VARCHAR(20) DEFAULT 'GENERAL',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """)

        # RouteTags
        print("Creating table: route_tags...")
        cur.execute("""
            CREATE TABLE route_tags (
                route_id BIGINT NOT NULL,
                tag_id INTEGER NOT NULL,
                PRIMARY KEY (route_id, tag_id)
            );
        """)

        conn.commit()
        print("Database initialization completed successfully.")
        
    except Exception as e:
        print(f"Error initializing database: {e}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    init_db()
