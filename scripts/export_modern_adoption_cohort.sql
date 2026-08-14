SELECT json_build_object(
        'video_id', video.youtube_video_id,
        'channel_id', channel.youtube_channel_id,
        'title', video.title,
        'description', left(coalesce(video.description, ''), 1000),
        'tags', json_build_array(),
        'category', coalesce(video.category_id, ''),
        'upload_date', to_char(
            video.published_at AT TIME ZONE 'UTC',
            'YYYY-MM-DD"T"HH24:MI:SS"Z"'
        )
    )::text
    FROM youtube_videos AS video
    JOIN youtube_channels AS channel ON channel.id = video.channel_id
    WHERE video.published_at >= make_date(2026, 1, 1)
      AND video.published_at < make_date(2026, 8, 14)
      AND channel.default_language LIKE 'en%'
ORDER BY video.published_at, video.youtube_video_id;
