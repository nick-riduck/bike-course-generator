import psycopg2
from psycopg2.extras import RealDictCursor
import os
from dotenv import load_dotenv
import json

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": os.getenv("DB_PORT", "5432"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD", "password"),
    "dbname": os.getenv("DB_NAME", "postgres")
}

def list_tags():
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        with conn.cursor() as cur:
            query = """
                SELECT t.type, t.slug, t.names, COUNT(rt.route_id) as usage_count
                FROM tags t
                LEFT JOIN route_tags rt ON t.id = rt.tag_id
                GROUP BY t.id, t.type, t.slug, t.names
                ORDER BY t.type, usage_count DESC;
            """
            cur.execute(query)
            rows = cur.fetchall()
            
            summary = {}
            for row in rows:
                t_type = row['type']
                if t_type not in summary:
                    summary[t_type] = []
                
                # Try to get ko name, then en, then slug
                names = row['names']
                display_name = names.get('ko') or names.get('en') or row['slug']
                
                summary[t_type].append({
                    'name': display_name,
                    'slug': row['slug'],
                    'usage_count': row['usage_count']
                })
            
            for t_type, tags in summary.items():
                print(f"\n[Type: {t_type}]")
                print(f"{'Name':<20} | {'Slug':<20} | {'Usage':<5}")
                print("-" * 50)
                for tag in tags:
                    print(f"{tag['name']:<20} | {tag['slug']:<20} | {tag['usage_count']:<5}")
                    
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    list_tags()
