import os
import time
import google.generativeai as genai

# Few-shot Examples
EXAMPLE_INPUT_1 = """제목: 2022 홍천 그란폰도 (우중 메디오폰도 라이딩)
출처: https://suimi.tistory.com/230
------------------------------------------------------------

2022.8.25.
3년 전에 접수했는데 코로나로 연기되다 올해 다시 열리게 되어 주변 지인들과 다녀올 예정입니다.
홍천종합운동장에서 출발하여 공작고개-작은솔치재-행치령-하뱃재-부목재를 돌아 출발지로 복귀하는 총
122km 1,900m의 코스입니다.
적당한 업힐 3개와 라이딩 거리가 있기때문에 평소 투어라이딩 보다는 조금 난이도가 있으나 대회 분위기에서 오는 에너지와 풍부한 중간 보급점이 있기에 무난하게 재미난 라이딩이 가능하리라 생각됩니다.
<사진>
아래는 대회 코스파일입니다.
2022홍천그란폰도.gpx
0.39MB
2022.09.05.
비가 내리는 가운데 우여사의 컨디션도 난조를 보여 아쉽지만 그란폰도 코스를 포기하고 메디오폰도 코스를 탔습니다.
메디오폰도 코스도 그란폰도에서 행치령의 업힐만 빠지고 대부분의 업힐이 포함되기에 거리는 줄지만 획고는 많이 줄지 않는 재미있는 코스였습니다.
그란폰도 코스는 날씨 좋을때 투어라이딩으로 다시 다녀와야겠습니다.
<사진>
2022홍천메디오폰도.gpx
0.25MB
https://youtu.be/NybYBtHAHdE
<사진>
대회에 나가면 이렇게 고퀄 사진을 얻을 수 있죠.
<사진>
노감독도 찍혔네요.ㅎㅎ
<사진>
우여사 코스 대부분을 따라타고 더 크게 타는 열정 가득한 김선생님
<사진>
충청권 지부장을 자임하신 충주의 열성팬 김원중 선생님도 참가하셨네요.
공유하기
게시글 관리
우여사의 투어라이딩"""

EXAMPLE_OUTPUT_1 = """# 2022 홍천 그란폰도 (우중 메디오폰도 라이딩)

- **Source**: [https://suimi.tistory.com/230](https://suimi.tistory.com/230)
- **Youtube**: [https://youtu.be/NybYBtHAHdE](https://youtu.be/NybYBtHAHdE)
- **Tags**: #강원 #홍천 #그란폰도 #순환 #힐클라임

## Description
홍천종합운동장에서 출발하여 공작고개, 작은솔치재, 행치령, 하뱃재, 부목재를 돌아 출발지로 복귀하는 총 122km, 획득고도 1,900m의 순환 코스입니다.

메디오폰도 코스는 그란폰도에서 행치령 업힐이 제외되지만, 공작고개와 하뱃재 등 주요 업힐이 포함되어 있어 거리 대비 획득고도가 높은 도전적인 코스입니다.

## Supplies & Amenities
- **보급**: 대회 코스 특성상 중간 보급소가 설치되나, 투어 시에는 서석면 등 경유하는 면 소재지 편의점/식당을 이용해야 합니다.
- **주차/화장실**: 출발지인 홍천종합운동장 주차장을 이용할 수 있습니다.

---
## Database Info
- **Title**: 2022 홍천 그란폰도 (우중 메디오폰도 라이딩)
- **Status**: PUBLIC
- **Is Verified**: FALSE
- **Route Type**: Loop"""

EXAMPLE_INPUT_2 = """제목: 평창-2 (진부역-봉산리-아우라지-꽃벼루재-나전역-오대천)
출처: https://suimi.tistory.com/316
------------------------------------------------------------

예전부터 가보고 싶었던 두타산 계곡길을 다녀왔습니다. 진부역에서 출발해 순환코스로 82km 1,200m의 코스입니다.
로드뷰 상 비포장 구간이 약 4km가 있어서 로드로 갈 수 있을지 궁금했는데 직접 가보니 초보자만 아니라면 충분히 갈 수 있는 수준이었습니다.
가보고 느꼈지만 자덕이라면 길이 좀 안 좋고 힘들어도 꼭 와바야할 코스 중 하나라 생각합니다.
봉산리 계곡길을 벗어나면 이미 익숙하게 많이 다녔던 송천계곡길을 만납니다. 구절리역 바로 아래쪽에서 합류해서 아우라지까지 송천을 따라 달리다 아우라지에 들러 휴식을 갖고 갑니다.
아우라지는
우여사 라이딩에서 늘 하던대로 송천의 다리를 건너고 아우라지 처녀상을 지나 골지천 다리를 건너서 갑니다.
휴식 후에 라이더들 사이에서 인기 좋은 꽃벼루재 길을 이번에는 아우라지 방향에서 시작해서 나전역 방향으로 가봅니다.
초반 깔딱 업힐(순간경사도 18%) 약 300m 정도가 있지만 이 구간만 오르면 역시나 푸른 숲길을 여유롭게 달릴 수 있는 꽃벼루재 길이 이어집니다.
여유롭게 숲길 라이딩을 즐기고 하산하면 예전 정선선 나전역(폐역)을 카페로 만들고 주변도 예쁘게 꾸며놨으니 들러서 크림커피 한잔 하고 가시기 바랍니다.
나전역 이후부터는 평창-1 라이딩에서 달렸던 오대천따라 출발지로 복귀합니다.
이 길에는 터널이 서너개가 있는데 터널마다 옛길로 우회도로가 있으니 시간의 여유가 되시면 우회도로로 여유롭게 라이딩 하시고 터널을 통과해서 가는 것도 갓길이 넓어 위험하지 않습니다.
<사진>
실제 라이딩한 코스입니다.
평창82.gpx
0.13MB
https://youtu.be/R-fttxsiUA8"""

EXAMPLE_OUTPUT_2 = """# 평창-2 (진부역-봉산리-아우라지-꽃벼루재-나전역-오대천)

- **Source**: [https://suimi.tistory.com/316](https://suimi.tistory.com/316)
- **Youtube**: [https://youtu.be/R-fttxsiUA8](https://youtu.be/R-fttxsiUA8)
- **Tags**: #강원 #평창 #정선 #순환 #힐클라임 #계곡

## Description
진부역에서 출발하여 두타산 계곡길(봉산리), 송천계곡, 아우라지, 꽃벼루재, 나전역을 거쳐 오대천을 따라 복귀하는 82km, 획득고도 1,200m의 순환 코스입니다.

봉산리 계곡길에는 약 4km의 비포장 구간이 포함되어 있으나 로드 자전거로도 주행 가능합니다(초보자 주의). 아우라지 방향에서 진입하는 꽃벼루재는 초반 급경사 이후 평탄하고 아름다운 숲길이 이어집니다. 복귀길인 오대천 구간의 터널들은 대부분 우회도로(옛길)가 있어 안전하고 여유롭게 라이딩할 수 있습니다.

## Supplies & Amenities
- **보급**: 아우라지 근처에서 휴식이 가능하며, 코스 후반부의 나전역(폐역)이 카페로 운영되고 있어 커피와 함께 쉬어가기 좋습니다.
- **주차/화장실**: 출발지인 진부역을 이용할 수 있습니다.

---
## Database Info
- **Title**: 평창-2 (진부역-봉산리-아우라지-꽃벼루재-나전역-오대천)
- **Status**: PUBLIC
- **Is Verified**: FALSE
- **Route Type**: Loop"""

def generate_content(model, description_text):
    prompt = f"""You are an expert cycling course editor. Your task is to convert raw blog post text describing a cycling route into a structured Markdown file using the provided examples as a guide.

Rules:
1.  **Source & Youtube:** Extract source URL and Youtube link.
2.  **Tags:** Generate relevant tags (Region, City, Type, Feature).
3.  **Description:** Summarize the route. Remove dates, file attachment mentions, personal chat, and weather complaints. Focus on path, scenery, difficulty, and road conditions. Use a polite and professional tone ("~입니다").
4.  **Supplies & Amenities:** Extract or infer supply points (myeon office areas, convenience stores, cafes) and parking/restroom info.
5.  **Database Info:** Extract Title, Status(PUBLIC), Is Verified(FALSE), and Route Type(Loop/Point-to-Point).

Example 1:
Input:
{EXAMPLE_INPUT_1}

Output:
{EXAMPLE_OUTPUT_1}

Example 2:
Input:
{EXAMPLE_INPUT_2}

Output:
{EXAMPLE_OUTPUT_2}

Current Task:
Input:
{description_text}

Output:
"""
    response = model.generate_content(prompt)
    return response.text

def main():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        api_key = input("Enter your Gemini API Key: ").strip()
    
    if not api_key:
        print("API Key is required.")
        return

    genai.configure(api_key=api_key)
    
    # Updated to available model 'gemini-3.1-pro-preview' as requested
    model = genai.GenerativeModel(
        model_name="gemini-3.1-pro-preview",
        generation_config={
            "temperature": 0.2,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 8192,
        }
    )

    root_dir = "suimi_gpx"
    processed_count = 0
    
    print("Starting auto-generation of route_info_gemini_api.md files...")
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        if "description.txt" in filenames:
            desc_path = os.path.join(dirpath, "description.txt")
            md_path = os.path.join(dirpath, "route_info_gemini_api.md")
            
            # Skip if already exists (optional, but user asked to regenerate, so we overwrite)
            # To be safe, we can process all or specific ones. 
            # Given the request context "너무 고된데?", implies processing remaining or all.
            # Let's process all to ensure consistency.
            
            try:
                with open(desc_path, 'r', encoding='utf-8') as f:
                    description_text = f.read()
                
                print(f"[{processed_count+1}] Processing: {os.path.basename(dirpath)}")
                
                result = generate_content(model, description_text)
                
                with open(md_path, 'w', encoding='utf-8') as f:
                    f.write(result)
                
                processed_count += 1
                time.sleep(2) # Rate limiting buffer
                
            except Exception as e:
                print(f"Error processing {desc_path}: {e}")
                time.sleep(5)

    print(f"Completed! Processed {processed_count} files.")

if __name__ == "__main__":
    main()
