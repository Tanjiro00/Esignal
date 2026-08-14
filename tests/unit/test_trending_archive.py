from __future__ import annotations

from datetime import UTC, datetime

from packages.backtest.trending_archive import load_us_trending_archive


def test_trending_archive_keeps_first_metadata_and_all_snapshots(tmp_path) -> None:
    source = tmp_path / "trending.csv"
    source.write_text(
        "video_id,title,publishedAt,channelId,channelTitle,categoryId,trending_date,"
        "tags,view_count,likes,dislikes,comment_count,thumbnail_link,comments_disabled,"
        "ratings_disabled,description\n"
        'one,"First AI title",2023-01-01T00:00:00Z,channel,Creator,28,'
        '2023-01-02T00:00:00Z,tags,100,1,0,1,url,False,False,"first description"\n'
        'one,"Future edited title",2023-01-01T00:00:00Z,channel,Creator,28,'
        '2023-01-03T00:00:00Z,tags,250,1,0,1,url,False,False,"future description"\n',
        encoding="utf-8",
    )

    videos = load_us_trending_archive(source)

    assert len(videos) == 1
    assert videos[0].title == "First AI title"
    assert videos[0].description == "first description"
    assert videos[0].published_at == datetime(2023, 1, 1, tzinfo=UTC)
    assert [row.views for row in videos[0].snapshots] == [100, 250]
