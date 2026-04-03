from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_utils import capture_image, repo_relative


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture and save a Raspberry Pi camera image for TrashformerPro.")
    parser.add_argument("--prefix", type=str, default="capture", help="Filename prefix for the saved image.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit output path. Defaults to runtime/captures/<prefix>_<timestamp>.jpg.",
    )
    parser.add_argument(
        "--camera-arg",
        action="append",
        default=[],
        help="Extra argument passed directly to rpicam-still. Repeat this flag for multiple arguments.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    image_path = capture_image(prefix=args.prefix, output_path=args.output, camera_args=args.camera_arg)
    print(f"Saved image: {repo_relative(image_path)}")


if __name__ == "__main__":
    main()
