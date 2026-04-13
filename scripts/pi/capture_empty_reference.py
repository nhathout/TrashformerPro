#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_utils import capture_image, repo_relative

DEFAULT_REFERENCE_PATH = Path("runtime/calibration/empty_plate.jpg")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture the empty-plate reference image used by the full TrashformerPro Pi runner."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REFERENCE_PATH,
        help="Where to save the empty reference image.",
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
    image_path = capture_image(
        prefix="empty_plate",
        output_path=args.output,
        camera_args=args.camera_arg,
    )
    print(f"Saved empty reference image: {repo_relative(image_path)}")
    print("Use this while the plate is empty and the lighting is in its normal operating state.")


if __name__ == "__main__":
    main()
