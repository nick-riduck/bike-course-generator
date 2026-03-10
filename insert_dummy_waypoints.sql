INSERT INTO waypoints (name, description, type, location, etc) VALUES
('양재시민의숲', '양재 시민의 숲 입니다.', '{park}', ST_SetSRID(ST_MakePoint(127.038516, 37.469725), 4326), '{"tour_count": 4, "has_images": false, "has_tips": false}'::jsonb),
('광나루 자전거공원 인증센터', '광나루 인증센터', '{parking}', ST_SetSRID(ST_MakePoint(127.120215, 37.546545), 4326), '{"tour_count": 20, "has_images": true, "has_tips": false}'::jsonb),
('수위가 낮을 때 강 건너기', '강 건너기', '{river}', ST_SetSRID(ST_MakePoint(127.21873, 37.548813), 4326), '{"tour_count": 17, "has_images": true, "has_tips": true}'::jsonb),
('한강철교', '한강 철교 아래', '{bridge}', ST_SetSRID(ST_MakePoint(127.318107, 37.550531), 4326), '{"tour_count": 19, "has_images": true, "has_tips": true}'::jsonb),
('풍납동 자전거 도로', '자전거 도로 구간', '{other}', ST_SetSRID(ST_MakePoint(127.100316, 37.522852), 4326), '{"tour_count": 27, "has_images": true, "has_tips": true}'::jsonb);