from __future__ import annotations

import argparse
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO


def stream_tar_member(
    archive: Path,
    member_name: str,
    destination: BinaryIO,
) -> None:
    with tarfile.open(archive, mode="r|bz2") as bundle:
        for member in bundle:
            if member.isfile() and PurePosixPath(member.name).name == member_name:
                source = bundle.extractfile(member)
                if source is None:
                    raise OSError(f"cannot open tar member: {member.name}")
                with source:
                    shutil.copyfileobj(source, destination, length=1024 * 1024)
                return
    raise FileNotFoundError(f"tar member not found: {member_name}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--member", required=True)
    args = parser.parse_args()
    stream_tar_member(args.archive, args.member, sys.stdout.buffer)


if __name__ == "__main__":
    main()
