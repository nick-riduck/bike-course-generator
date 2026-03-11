import os
import sys
import json
import re
import time
import argparse
import signal
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter
from tqdm import tqdm

from dotenv import load_dotenv
from google import genai
from google.genai import types

# --- Paths & Config ---
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

load_dotenv(PROJECT_ROOT / "backend" / ".env")

from app.core.database import get_db_conn
from app.services.embedding_service import set_cache, query_cache

MODEL = "gemini-3.1-pro-preview"
API_KEY = os.getenv("GEMINI_API_KEY")
MAX_RETRIES = 3

PROGRESS_FILE = Path(__file__).parent / "output" / "prefill_cache_progress.jsonl"
PROGRESS_FILE.parent.mkdir(parents=True, exist_ok=True)

PROMPT_TEMPLATE = """너는 한국의 자전거 라이딩 코스를 추천하는 전문가야. 지금 네게는 구글 검색 툴이 주어져 있어.

[지시 사항]
1. 구글 검색 툴을 사용해서 한국 자전거 동호인들의 최신 커뮤니티 글, 블로그 후기, 유튜브 영상 제목 등을 자유롭게 검색해서 읽어봐. 매 호출마다 완전히 새롭고 다양한 주제(예를 들어, 어느 날은 식도락 투어, 어느 날은 극강의 산악 훈련 등)를 스스로 설정해서 검색해.
2. 검색한 문서를 바탕으로, 한국의 자전거 라이더들이 코스나 장소를 찾을 때 머릿속에 떠올릴 만한 연관 키워드 50개를 추출해 줘.
3. 추출 대상: 지명, 코스 고유명사, 지형/난이도, 라이딩 목적/스타일, 동호인 은어, 먹거리, 경치 등 '자전거 라이딩'과 관련된 1~3어절의 모든 자유로운 단어.

[출력 규칙]
반드시 아래의 JSON 형식으로만 응답해. 네가 실제로 정보를 찾기 위해 사용했던 구글 검색어(1개 이상)를 `used_search_queries` 배열에 반드시 포함시켜줘.

{
  "used_search_queries": ["실제로 네가 구글링에 사용한 검색어1", "검색어2"],
  "keywords": ["단어1", "단어2", "단어3"]
}"""

# --- Graceful Shutdown ---
_shutdown = False
def _signal_handler(sig, frame):
    global _shutdown
    _shutdown = True
    print("\n⚠️  종료 요청 수신. 현재 작업 완료 후 안전하게 종료합니다...")

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# --- Helpers ---
def parse_json_response(text):
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"^```\s*$", "", text, flags=re.MULTILINE)
    text = text.strip()
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError(f"JSON not found in response: {text[:200]}")

def get_existing_cache_keys(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT query FROM search_query_cache")
        return {row['query'] for row in cur.fetchall()}

def get_db_tags(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT slug FROM tags")
        return [row['slug'] for row in cur.fetchall()]

def get_top_waypoint_names(conn, limit=300):
    with conn.cursor() as cur:
        cur.execute("SELECT name FROM waypoints")
        names = []
        for row in cur.fetchall():
            for word in row['name'].split():
                clean_word = ''.join(c for c in word if c.isalnum())
                if len(clean_word) >= 2:
                    names.append(clean_word)
        return [word for word, count in Counter(names).most_common(limit)]

def generate_ai_keywords_single(client, attempt_index):
    """Call Gemini with timeout + retry to get keywords."""
    tool = {"google_search": {}}
    last_error = None
    
    for attempt in range(MAX_RETRIES):
        if _shutdown:
            return None
            
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=PROMPT_TEMPLATE,
                config=types.GenerateContentConfig(
                    tools=[tool],
                    temperature=0.8,
                    http_options=types.HttpOptions(timeout=60 * 1000),
                ),
            )

            result = parse_json_response(response.text)
            result['_batch_index'] = attempt_index
            return result

        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                wait = (2 ** attempt) * 2
                time.sleep(wait)

    raise last_error

def worker_embed_and_save(keyword):
    """Worker function to embed and save to DB."""
    if _shutdown:
        return keyword, "SHUTDOWN"
        
    try:
        if query_cache(keyword) is not None:
            return keyword, "SKIPPED"

        # Vertex AI client for embedding (backend standard)
        client = genai.Client(vertexai=True, location="us-central1")
        result = client.models.embed_content(
            model="gemini-embedding-001",
            contents=keyword,
        )
        embedding_values = result.embeddings[0].values
        set_cache(keyword, embedding_values)
        return keyword, "SUCCESS"
    except Exception as e:
        return keyword, f"ERROR: {e}"

def load_progress():
    completed_batches = []
    if not PROGRESS_FILE.exists():
        return completed_batches
    with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                completed_batches.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return completed_batches

def run_ai_generation(ai_client, ai_batches, ai_workers):
    """Phase 2: AI Brainstorming in parallel"""
    print(f"\n--- [Phase 2] AI Brainstorming ({ai_batches} batches) ---")
    
    completed_batches = load_progress()
    ai_keywords = []
    completed_indices = set()
    
    for b in completed_batches:
        ai_keywords.extend(b.get("keywords", []))
        if "_batch_index" in b:
            completed_indices.add(b["_batch_index"])
            
    if completed_indices:
        print(f"-> Resumed {len(completed_indices)} AI batches from progress file. (Loaded {len(ai_keywords)} words)")

    batches_to_run = [i for i in range(ai_batches) if i not in completed_indices]
    
    if batches_to_run:
        # Run AI requests in parallel
        with ThreadPoolExecutor(max_workers=min(ai_workers, len(batches_to_run))) as executor:
            futures = {executor.submit(generate_ai_keywords_single, ai_client, i): i for i in batches_to_run}
            
            for future in tqdm(as_completed(futures), total=len(futures), desc="AI Brainstorming"):
                if _shutdown:
                    break
                try:
                    result = future.result()
                    if result:
                        ai_keywords.extend(result.get("keywords", []))
                        queries = result.get("used_search_queries", [])
                        tqdm.write(f"🔎 AI Searched: {queries}")
                        
                        with open(PROGRESS_FILE, "a", encoding="utf-8") as f:
                            f.write(json.dumps(result, ensure_ascii=False) + "\n")
                except Exception as e:
                    tqdm.write(f"❌ AI Batch failed: {e}")

    return ai_keywords

def main():
    parser = argparse.ArgumentParser(description="Prefill DB Embedding Cache with Gemini 3.1 Pro")
    parser.add_argument("--workers", type=int, default=10, help="Number of concurrent workers for embedding")
    parser.add_argument("--ai-workers", type=int, default=3, help="Number of concurrent workers for AI generation")
    parser.add_argument("--ai-batches", type=int, default=20, help="Number of AI batches to run (50 words each)")
    parser.add_argument("--reset", action="store_true", help="처음부터 다시 (progress 삭제)")
    args = parser.parse_args()

    if not API_KEY:
        print("ERROR: GEMINI_API_KEY is missing.")
        return

    if args.reset and PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
        print("⚠️ Progress 초기화 완료")

    conn = get_db_conn()
    ai_client = genai.Client(api_key=API_KEY)
    
    try:
        print("\n--- [Phase 1] Collecting Data ---")
        existing_keys = get_existing_cache_keys(conn)
        print(f"[{len(existing_keys)} items currently in DB cache]")

        tags = get_db_tags(conn)
        print(f"-> Extracted {len(tags)} existing tags from DB.")

        wp_names = get_top_waypoint_names(conn, limit=300)
        print(f"-> Extracted {len(wp_names)} common waypoint names from DB.")
        
        # Run AI Generation (Parallelized internally)
        ai_keywords = run_ai_generation(ai_client, args.ai_batches, args.ai_workers)

        if _shutdown:
            print("중단됨.")
            return

        print("\n--- [Phase 3] Data Refining ---")
        
        # Save raw extraction data for user verification
        raw_data = {
            "tags": tags,
            "waypoints": wp_names,
            "ai_generated": ai_keywords
        }
        raw_out_path = Path(__file__).parent / "output" / "raw_extracted_keywords.json"
        with open(raw_out_path, "w", encoding="utf-8") as f:
            json.dump(raw_data, f, ensure_ascii=False, indent=2)
        print(f"💾 Raw extracted keywords saved to: {raw_out_path}")

        all_keywords = set(tags + wp_names + ai_keywords)
        
        # Filter: length > 1 and not already in cache
        to_process = [k for k in all_keywords if k not in existing_keys and len(k) > 1]
        
        # Save refined data for user verification
        refined_out_path = Path(__file__).parent / "output" / "refined_keywords_to_embed.json"
        with open(refined_out_path, "w", encoding="utf-8") as f:
            json.dump(list(to_process), f, ensure_ascii=False, indent=2)
        print(f"💾 Refined keywords (to be embedded) saved to: {refined_out_path}")
        
        print(f"\n🎉 Extraction and Refining Complete! Total unique keywords ready for embedding: {len(to_process)}")
        print("Stopping before DB insertion as requested.")

    finally:
        conn.close()

if __name__ == "__main__":
    main()