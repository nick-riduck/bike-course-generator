import os
import re

def parse_description_file(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    lines = content.split('\n')
    title = ""
    source_url = ""
    description_lines = []
    youtube_url = ""
    
    # Metadata extraction state
    parsing_body = False
    
    # Regex for dates (YYYY.MM.DD)
    date_pattern = re.compile(r'^\d{4}\.\d{1,2}\.\d{1,2}\.?$')

    # Keywords to exclude
    exclude_keywords = [
        "접수", "예정", "첨부", "파일", "MB", "KB", "다운", "참조", "클릭", 
        "구독", "좋아요", "공유", "게시글", "카테고리", "다녀왔", "참가", 
        "사진", "찍혔", "컨디션", "지부장", "선생님", "감독", "지인", "우여사"
    ]

    # Keywords to prioritize (if a line has these, we are more likely to keep it, unless it has exclude keywords)
    course_keywords = [
        "코스", "출발", "복귀", "순환", "km", "m", "고개", "령", "재", 
        "산", "강", "호수", "저수지", "길", "구간", "업힐", "라이딩", "투어"
    ]
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith("제목:"):
            title = line.replace("제목:", "").strip()
        elif line.startswith("출처:"):
            source_url = line.replace("출처:", "").strip()
        elif line.startswith("------------------------------------------------------------"):
            parsing_body = True
            continue
        elif parsing_body:
            # Check for footer start or end of content
            if line == "공유하기" or line == "게시글 관리" or line.startswith("우여사의 투어라이딩") or line.startswith("'") or line == "다녀온 코스" or line.startswith("카테고리의 다른 글") or ".gpx" in line or "gpx파일 첨부합니다" in line:
                break
            
            # Check for YouTube link
            if "youtu.be" in line or "youtube.com" in line:
                youtube_url = line
                continue
                
            # Skip <사진> tags
            if line == "<사진>":
                continue

            # --- Intelligent Cleaning Logic ---
            
            # 1. Skip Dates
            if date_pattern.match(line):
                continue

            # 2. Skip Exclude Keywords
            if any(keyword in line for keyword in exclude_keywords):
                continue
            
            # 3. Check for meaningful content
            # If it's a very short line without course keywords, it might be noise
            if len(line) < 10 and not any(keyword in line for keyword in course_keywords):
                continue

            description_lines.append(line)

    description = "\n".join(description_lines).strip()
    return title, source_url, description, youtube_url

def generate_tags(title, description):
    tags = set()
    
    # Region keywords
    regions = {
        "서울": ["서울", "한강", "남산", "북악"],
        "경기": ["경기", "양평", "가평", "포천", "연천", "여주", "이천", "광주", "남한산성", "수원", "안성", "평택", "화성", "용인", "안산", "시흥", "김포", "파주", "고양", "의정부", "동두천", "구리", "남양주", "하남", "양주", "의왕", "군포", "오산", "광명", "과천"],
        "강원": ["강원", "춘천", "원주", "강릉", "속초", "동해", "태백", "삼척", "홍천", "횡성", "영월", "평창", "정선", "철원", "화천", "양구", "인제", "고성", "양양", "설악", "대관령", "미시령", "한계령", "진부령", "구룡령"],
        "충북": ["충북", "청주", "충주", "제천", "보은", "옥천", "영동", "증평", "진천", "괴산", "음성", "단양", "소백산", "속리산", "월악산"],
        "충남": ["충남", "천안", "공주", "보령", "아산", "서산", "논산", "계룡", "당진", "금산", "부여", "서천", "청양", "홍성", "예산", "태안"],
        "전북": ["전북", "전주", "군산", "익산", "정읍", "남원", "김제", "완주", "진안", "무주", "장수", "임실", "순창", "고창", "부안", "내장산", "지리산", "덕유산"],
        "전남": ["전남", "목포", "여수", "순천", "나주", "광양", "담양", "곡성", "구례", "고흥", "보성", "화순", "장흥", "강진", "해남", "영암", "무안", "함평", "영광", "장성", "완도", "진도", "신안"],
        "경북": ["경북", "포항", "경주", "김천", "안동", "구미", "영주", "영천", "상주", "문경", "경산", "군위", "의성", "청송", "영양", "영덕", "청도", "고령", "성주", "칠곡", "예천", "봉화", "울진", "울릉"],
        "경남": ["경남", "창원", "진주", "통영", "사천", "김해", "밀양", "거제", "양산", "의령", "함안", "창녕", "고성", "남해", "하동", "산청", "함양", "거창", "합천"],
        "제주": ["제주", "서귀포", "한라산", "1100고지"]
    }
    
    combined_text = (title + " " + description).replace(" ", "")

    for region, keywords in regions.items():
        for keyword in keywords:
            if keyword in combined_text or keyword in title or keyword in description:
                tags.add(region)
                tags.add(keyword)
                
    # Type keywords
    types = {
        "힐클라임": ["업힐", "고개", "령", "재", "산", "정상", "ヒルクライム"],
        "평지": ["평지", "강변", "뚝방", "천", "호수", "저수지"],
        "순환": ["순환", "한바퀴", "원점회귀"],
        "투어": ["투어", "여행", "관광"],
        "바다": ["바다", "해안", "해변", "항", "섬", "대교"],
        "벚꽃": ["벚꽃", "봄"],
        "단풍": ["단풍", "가을"],
        "계곡": ["계곡"],
        "그란폰도": ["그란폰도", "메디오폰도", "대회"]
    }

    for tag_type, keywords in types.items():
        for keyword in keywords:
            if keyword in combined_text or keyword in title or keyword in description:
                tags.add(tag_type)

    return list(tags)

def create_markdown_content(title, source_url, description, youtube_url, tags):
    tags_str = " ".join([f"#{t}" for t in tags])
    
    lines = []
    lines.append(f"# {title}")
    lines.append("")
    if source_url:
        lines.append(f"- **Source**: [{source_url}]({source_url})")
    if youtube_url:
        lines.append(f"- **Youtube**: [{youtube_url}]({youtube_url})")
    
    lines.append(f"- **Tags**: {tags_str}")
    lines.append("")
    lines.append("## Description")
    lines.append(description)
    lines.append("")
    lines.append("---")
    lines.append("## Database Info")
    lines.append(f"- **Title**: {title}")
    lines.append("- **Status**: PUBLIC")
    lines.append("- **Is Verified**: FALSE")
    lines.append(f"- **Route Type**: {'Loop' if '순환' in tags else 'Point-to-Point'}")
    
    return "\n".join(lines)

def main():
    root_dir = "suimi_gpx"
    processed_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "description.txt" in filenames:
            txt_path = os.path.join(dirpath, "description.txt")
            md_path = os.path.join(dirpath, "route_info.md")
            
            try:
                title, source_url, description, youtube_url = parse_description_file(txt_path)
                tags = generate_tags(title, description)
                md_content = create_markdown_content(title, source_url, description, youtube_url, tags)
                
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(md_content)
                
                print(f"Processed: {title} -> {md_path}")
                processed_count += 1
            except Exception as e:
                print(f"Error processing {txt_path}: {e}")

    print(f"Total processed: {processed_count}")

if __name__ == "__main__":
    main()
