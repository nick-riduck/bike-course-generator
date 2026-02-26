#!/usr/bin/env python3
"""
suimi.tistory.com 블로그 GPX/TCX 크롤러
- 카테고리 '다녀온 코스'의 모든 포스트에서 GPX/TCX 파일과 제목 수집
- suimi_gpx/[코스명]/ 디렉토리 구조로 저장
"""

import os
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, urljoin

BASE_URL = "https://suimi.tistory.com"
CATEGORY_URL = f"{BASE_URL}/category/%EB%8B%A4%EB%85%80%EC%98%A8%20%EC%BD%94%EC%8A%A4"
OUTPUT_DIR = "/Users/nick/bike_course_generator/suimi_gpx"
DELAY = 1  # 서버 부하 방지용 딜레이 (초)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": BASE_URL,
}

session = requests.Session()
session.headers.update(HEADERS)


def sanitize_dirname(name: str) -> str:
    """파일시스템에 사용할 수 없는 문자 제거"""
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:100]


def get_post_urls_from_page(page: int) -> list:
    """카테고리 페이지에서 포스트 URL 목록 추출"""
    url = CATEGORY_URL if page == 1 else f"{CATEGORY_URL}?page={page}"
    try:
        resp = session.get(url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        post_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if re.match(r'^https://suimi\.tistory\.com/\d+$', href):
                if href not in post_links:
                    post_links.append(href)
            elif re.match(r'^/\d+$', href):
                full = urljoin(BASE_URL, href)
                if full not in post_links:
                    post_links.append(full)

        print(f"  페이지 {page}: {len(post_links)}개 포스트 URL 수집")
        return post_links
    except Exception as e:
        print(f"  페이지 {page} 오류: {e}")
        return []


def extract_post_data(post_url: str) -> dict:
    """포스트에서 제목, 본문, GPX/TCX 링크 추출"""
    try:
        resp = session.get(post_url, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, 'lxml')

        # 제목: og:title 또는 <title> 태그 사용 (가장 정확)
        title = ""
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content'].strip()
        elif soup.find('title'):
            title = soup.find('title').get_text(strip=True)

        # 본문 텍스트 추출
        body_text = ""
        # Tistory 본문 영역 탐색
        content_div = (
            soup.find('div', class_='entry-content') or
            soup.find('div', class_='post-content') or
            soup.find('div', id=re.compile(r'article|content', re.I)) or
            soup.find('article')
        )
        if content_div:
            for tag in content_div.find_all(['script', 'style']):
                tag.decompose()
            # img 태그를 <사진> 텍스트로 교체
            for img in content_div.find_all('img'):
                img.replace_with('\n<사진>\n')
            body_text = content_div.get_text(separator='\n', strip=True)
            body_text = re.sub(r'\n{3,}', '\n\n', body_text)

        # GPX/TCX 파일 링크 추출 (카카오 CDN - 서명된 전체 URL 필요)
        file_links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            decoded = unquote(href)
            if re.search(r'\.(gpx|tcx)', decoded, re.I):
                if href not in file_links:
                    file_links.append(href)

        typed_links = []
        for link in file_links:
            decoded = unquote(link)
            ext_match = re.search(r'\.(gpx|tcx)', decoded, re.I)
            ext = ext_match.group(1).lower() if ext_match else 'gpx'
            # 원본 파일명 추출
            fname_match = re.search(r'/([^/?]+\.(gpx|tcx))', decoded, re.I)
            fname = fname_match.group(1) if fname_match else f"course.{ext}"
            typed_links.append({'url': link, 'ext': ext, 'fname': fname})

        return {
            'url': post_url,
            'title': title,
            'body': body_text,
            'files': typed_links,
        }

    except Exception as e:
        print(f"  포스트 파싱 오류 ({post_url}): {e}")
        return None


def download_file(url: str, save_path: str) -> bool:
    """파일 다운로드"""
    try:
        resp = session.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(save_path, 'wb') as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    다운로드 실패: {e}")
        return False


def process_post(post_url: str, idx: int, total: int):
    """포스트 1개 처리"""
    print(f"\n[{idx}/{total}] {post_url}")
    data = extract_post_data(post_url)
    if not data:
        return False

    title = data['title'] or f"course_{idx}"
    print(f"  제목: {title}")
    print(f"  파일: {len(data['files'])}개 발견")

    if not data['files']:
        print("  GPX/TCX 파일 없음 - 건너뜀")
        return False

    # 디렉토리 생성
    dir_name = sanitize_dirname(title)
    dir_path = os.path.join(OUTPUT_DIR, dir_name)
    os.makedirs(dir_path, exist_ok=True)

    # 본문 텍스트 저장
    txt_path = os.path.join(dir_path, "description.txt")
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"제목: {title}\n")
        f.write(f"출처: {post_url}\n")
        f.write("-" * 60 + "\n\n")
        f.write(data['body'])
    print(f"  description.txt 저장 완료")

    # GPX/TCX 파일 다운로드
    for file_info in data['files']:
        fname = sanitize_dirname(file_info['fname'])
        save_path = os.path.join(dir_path, fname)

        print(f"  다운로드: {fname} ...", end=' ', flush=True)
        if download_file(file_info['url'], save_path):
            size = os.path.getsize(save_path)
            print(f"완료 ({size:,} bytes)")
        else:
            print("실패")

    return True


def get_total_pages() -> int:
    """카테고리 총 페이지 수 확인"""
    resp = session.get(CATEGORY_URL, timeout=15)
    soup = BeautifulSoup(resp.text, 'lxml')

    max_page = 1
    for a in soup.find_all('a', href=True):
        m = re.search(r'\?page=(\d+)', a['href'])
        if m:
            max_page = max(max_page, int(m.group(1)))

    return max_page


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"저장 디렉토리: {OUTPUT_DIR}")
    print("총 페이지 수 확인 중...")

    total_pages = get_total_pages()
    print(f"총 {total_pages}페이지 발견\n")

    # 모든 포스트 URL 수집
    all_post_urls = []
    for page in range(1, total_pages + 1):
        urls = get_post_urls_from_page(page)
        all_post_urls.extend(urls)
        time.sleep(DELAY)

    # 중복 제거
    all_post_urls = list(dict.fromkeys(all_post_urls))
    print(f"\n총 {len(all_post_urls)}개 포스트 수집 완료")
    print("=" * 60)

    # 각 포스트 처리
    success = 0
    skipped = 0
    for i, url in enumerate(all_post_urls, 1):
        result = process_post(url, i, len(all_post_urls))
        if result:
            success += 1
        else:
            skipped += 1
        time.sleep(DELAY)

    print("\n" + "=" * 60)
    print(f"완료! 성공: {success}개, 건너뜀(파일없음): {skipped}개")
    print(f"저장 위치: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
