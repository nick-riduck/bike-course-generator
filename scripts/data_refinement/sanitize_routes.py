import os
import json
import time
import psycopg2
from psycopg2.extras import RealDictCursor
import google.generativeai as genai
from dotenv import load_dotenv

# Load environment variables
load_dotenv("backend/.env")

# Gemini Configuration
genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))
# Using the latest flash preview as requested
model = genai.GenerativeModel("gemini-3-flash-preview")

def get_db_connection():
    return psycopg2.connect(
        host=os.environ.get("DB_HOST"),
        port=os.environ.get("DB_PORT"),
        user=os.environ.get("DB_USER"),
        password=os.environ.get("DB_PASSWORD"),
        dbname=os.environ.get("DB_NAME")
    )

def sanitize_content(title, description):
    prompt = f"""
당신은 사이클링 코스 데이터 정제 전문가입니다. 
다음은 블로그나 커뮤니티에서 수집된 코스 데이터입니다. 
저작권 문제나 개인정보 노출을 방지하기 위해 다음 규칙에 따라 텍스트를 정제해 주세요.

규칙:
1. 특정 제작자나 인물 언급 제거: '우여사', '노감독', '김선생님', '지부장' 등 특정 인물의 닉네임이나 성함이 들어간 문장을 삭제하거나 자연스럽게 수정하세요.
2. 개인적인 사담 및 인사 제거: '다녀왔습니다', '연기되어 아쉽네요', '우중 라이딩' 등 개인적인 경험이나 감정 표현을 제거하세요.
3. 플랫폼 전용 문구 제거: '사진', '첨부파일', '구독', '좋아요', '댓글', '공유하기' 등 블로그/유튜브와 관련된 문구를 삭제하세요.
4. 코스 정보 보존: 'xx고개', 'xx령', 'xx역', 'xxkm', '획고 xxm' 등 지리적 정보와 코스의 기술적 스펙은 반드시 보존하세요.
5. 어조: 기존의 정중한 경어체(~입니다, ~합니다)를 반드시 유지하세요. 문장은 완전한 서술형으로 자연스럽게 작성해 주세요.
6. 보급: ~~ 주차/화장실: ~~~ 의 대한 정보가 있을경우 보존하되, 개인적인 경험이나 감정 표현이 포함된 경우에는 제거하세요.

입력:
제목: {title}
설명: {description}

출력 형식 (JSON):
{{
  "new_title": "정제된 제목",
  "new_description": "정제된 설명"
}}
"""
    try:
        response = model.generate_content(prompt)
        content = response.text.strip()
        # Extract JSON from potential markdown blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0].strip()
        elif "```" in content:
            content = content.split("```")[1].split("```")[0].strip()
        
        return json.loads(content)
    except Exception as e:
        print(f"AI refinement error: {e}")
        return None

def analyze_all():
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    print("Reading data from DB...")
    cur.execute("SELECT id, title, description FROM routes ORDER BY id")
    routes = cur.fetchall()
    
    candidates = []
    print(f"Analyzing {len(routes)} routes.")
    
    # Create the result file if it doesn't exist to store partial results
    result_path = "scripts/data_refinement/refinement_candidates.json"
    
    for i, route in enumerate(routes):
        print(f"[{i+1}/{len(routes)}] Analyzing: {route['title']}")
        
        # AI Refinement request
        refined = sanitize_content(route['title'], route['description'] or "")
        
        if refined:
            candidates.append({
                "id": route['id'],
                "old_title": route['title'],
                "new_title": refined['new_title'],
                "old_description": route['description'],
                "new_description": refined['new_description']
            })
        
        # Save every 10 items or at the end to prevent data loss
        if (i + 1) % 10 == 0 or (i + 1) == len(routes):
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(candidates, f, ensure_ascii=False, indent=2)
        
        time.sleep(0.5) # Reduced sleep for flash model
        
    print(f"Analysis complete! Check {result_path}")
    cur.close()
    conn.close()

def generate_sql():
    input_path = "scripts/data_refinement/refinement_candidates.json"
    output_path = "scripts/data_refinement/update_routes.sql"
    
    if not os.path.exists(input_path):
        print(f"Error: {input_path} not found. Run 'analyze' first.")
        return

    with open(input_path, "r", encoding="utf-8") as f:
        candidates = json.load(f)
        
    sql_lines = ["BEGIN;"]
    
    for c in candidates:
        # Basic escaping for SQL
        new_title = c['new_title'].replace("'", "''")
        new_desc = c['new_description'].replace("'", "''")
        
        sql = f"UPDATE routes SET title = '{new_title}', description = '{new_desc}', updated_at = CURRENT_TIMESTAMP WHERE id = {c['id']};"
        sql_lines.append(sql)
        
    sql_lines.append("COMMIT;")
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(sql_lines))
        
    print(f"SQL file generated: {output_path}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python sanitize_routes.py [analyze|generate-sql]")
    elif sys.argv[1] == "analyze":
        analyze_all()
    elif sys.argv[1] == "generate-sql":
        generate_sql()
