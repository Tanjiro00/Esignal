COPY (
WITH active AS (
  SELECT c.id, c.youtube_channel_id, c.title, c.description, c.subscriber_count
  FROM youtube_channels c
  JOIN panel_membership p ON p.channel_id = c.id AND p.left_at IS NULL
),
vids AS (
  SELECT v.channel_id, count(*) AS videos_90d
  FROM youtube_videos v
  WHERE v.published_at >= now() - interval '90 days'
  GROUP BY v.channel_id
),
recent AS (
  SELECT v.channel_id, max(v.published_at) AS last_upload_at
  FROM youtube_videos v GROUP BY v.channel_id
),
comm AS (
  SELECT v.channel_id, count(*) AS comments_30d
  FROM youtube_comments cm
  JOIN youtube_videos v ON v.id = cm.video_id
  WHERE cm.published_at >= now() - interval '30 days'
  GROUP BY v.channel_id
),
-- Contact details live in video descriptions far more often than in the
-- channel blurb, so the search text is the channel description plus the most
-- recent uploads.
vdesc AS (
  SELECT channel_id, string_agg(description, ' ') AS text
  FROM (
    SELECT v.channel_id, left(coalesce(v.description, ''), 1200) AS description,
           row_number() OVER (PARTITION BY v.channel_id ORDER BY v.published_at DESC) AS rn
    FROM youtube_videos v
  ) ranked
  WHERE rn <= 5
  GROUP BY channel_id
)
SELECT a.title,
       a.subscriber_count,
       coalesce(vd.videos_90d, 0),
       coalesce(cm.comments_30d, 0),
       'https://www.youtube.com/channel/' || a.youtube_channel_id,
       to_char(r.last_upload_at, 'YYYY-MM-DD'),
       replace(replace(coalesce(a.description, '') || ' ' || coalesce(vt.text, ''), E'\n', ' '), E'\r', ' ')
FROM active a
LEFT JOIN vids vd ON vd.channel_id = a.id
LEFT JOIN recent r ON r.channel_id = a.id
LEFT JOIN comm cm ON cm.channel_id = a.id
LEFT JOIN vdesc vt ON vt.channel_id = a.id
WHERE a.subscriber_count BETWEEN 10000 AND 300000
  AND coalesce(vd.videos_90d, 0) >= 6
ORDER BY coalesce(cm.comments_30d, 0) DESC, a.subscriber_count DESC
) TO STDOUT WITH CSV HEADER;
