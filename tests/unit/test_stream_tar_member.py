from __future__ import annotations

import io
import tarfile

from scripts.stream_tar_member import stream_tar_member


def test_stream_tar_member_finds_member_by_basename(tmp_path) -> None:
    archive = tmp_path / "fixture.tar.bz2"
    payload = b"header\nvalue\n"
    with tarfile.open(archive, mode="w:bz2") as bundle:
        member = tarfile.TarInfo("nested/most_popular.csv")
        member.size = len(payload)
        bundle.addfile(member, io.BytesIO(payload))
    destination = io.BytesIO()

    stream_tar_member(archive, "most_popular.csv", destination)

    assert destination.getvalue() == payload
