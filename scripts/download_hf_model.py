from __future__ import annotations

import argparse
import os
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download a Hugging Face model serially to a local directory."
    )
    parser.add_argument("repo_id", help="Hugging Face model repository, e.g. intfloat/multilingual-e5-large")
    parser.add_argument("local_dir", type=Path, help="Destination directory")
    parser.add_argument("--max-workers", type=int, default=1)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.max_workers < 1:
        raise SystemExit("--max-workers must be at least 1")

    # Must be set before importing huggingface_hub.
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "300")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "60")

    try:
        from huggingface_hub import snapshot_download
    except ImportError as exc:
        raise SystemExit(
            "huggingface_hub is not installed. Run: py -m pip install -U huggingface_hub"
        ) from exc

    destination = args.local_dir.resolve()
    destination.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {args.repo_id} to {destination} with {args.max_workers} worker(s)")
    snapshot_download(
        repo_id=args.repo_id,
        local_dir=destination,
        max_workers=args.max_workers,
    )
    print(f"Model is ready at {destination}")


if __name__ == "__main__":
    main()
