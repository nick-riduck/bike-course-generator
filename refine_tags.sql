-- 1. Garbage Data Deletion
DELETE FROM route_tags WHERE tag_id IN (SELECT id FROM tags WHERE slug IN ('1', '2', '3', '12', '123', '1231', 'test', 'sd', '123fad', 'ㅇ', '편도', '왕복'));
DELETE FROM tags WHERE slug IN ('1', '2', '3', '12', '123', '1231', 'test', 'sd', '123fad', 'ㅇ', '편도', '왕복');

-- 2. Tag Merging Function
CREATE OR REPLACE FUNCTION merge_tags(target_slug TEXT, source_slugs TEXT[]) RETURNS VOID AS $$
DECLARE
    target_id INT;
    source_id INT;
    s_slug TEXT;
BEGIN
    -- Get Target ID
    SELECT id INTO target_id FROM tags WHERE slug = target_slug;
    
    IF target_id IS NULL THEN
        RAISE NOTICE 'Target tag % not found, skipping merges for this target.', target_slug;
        RETURN;
    END IF;

    FOREACH s_slug IN ARRAY source_slugs
    LOOP
        SELECT id INTO source_id FROM tags WHERE slug = s_slug;
        
        IF source_id IS NOT NULL THEN
            -- Move route associations to target
            INSERT INTO route_tags (route_id, tag_id)
            SELECT route_id, target_id
            FROM route_tags
            WHERE tag_id = source_id
            ON CONFLICT DO NOTHING;
            
            -- Remove associations from source
            DELETE FROM route_tags WHERE tag_id = source_id;
            
            -- Delete source tag
            DELETE FROM tags WHERE id = source_id;
            
            RAISE NOTICE 'Merged % into %', s_slug, target_slug;
        ELSE
            RAISE NOTICE 'Source tag % not found.', s_slug;
        END IF;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- 3. Execute Merges
SELECT merge_tags('해안도로', ARRAY['해안', '해안길', '바다', '바닷길', '오션뷰']);
SELECT merge_tags('섬라이딩', ARRAY['섬투어', '섬']);
SELECT merge_tags('호수', ARRAY['호반', '호반길']);
SELECT merge_tags('강변', ARRAY['강변길']);
SELECT merge_tags('관광', ARRAY['관광라이딩', '관광지']);
SELECT merge_tags('투어', ARRAY['투어라이딩']);
SELECT merge_tags('초보가능', ARRAY['초보추천', '초보자추천', '초급', '입문']);
SELECT merge_tags('벚꽃', ARRAY['벚꽃길']);
SELECT merge_tags('꽃구경', ARRAY['꽃길']);
SELECT merge_tags('힐클라임', ARRAY['업힐', '헤어핀']);
SELECT merge_tags('삼척', ARRAY['어라운드삼척']);
SELECT merge_tags('메타세쿼이아길', ARRAY['메타세콰이어길', '메타세쿼이아']);

-- 4. Clean up function
DROP FUNCTION merge_tags;
