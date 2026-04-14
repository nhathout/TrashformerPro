from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.classify_image import format_prediction_report, predict_image
from inference.pi.runtime_utils import capture_image, repo_relative, write_inference_record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Capture a fresh Raspberry Pi image, classify it, and archive both the image and prediction."
    )
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Path to a .pt checkpoint from training. Defaults to models/best.pt, then runtime/models/best.pt.",
    )
    parser.add_argument("--device", type=str, default="auto", help="auto, cuda, mps, or cpu")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument(
        "--capture-prefix",
        type=str,
        default="capture",
        help="Filename prefix for the saved camera image.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional explicit output path for the captured image.",
    )
    parser.add_argument(
        "--camera-arg",
        action="append",
        default=[],
        help="Extra argument passed directly to rpicam-still. Repeat this flag for multiple arguments.",
    )
    parser.add_argument(
        "--confirmed-label",
        type=str,
        default="",
        help="Optional human-confirmed label to store alongside the prediction record.",
    )
    parser.add_argument("--notes", type=str, default="", help="Optional notes to store with the prediction record.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of plain text.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    image_path = capture_image(
        prefix=args.capture_prefix,
        output_path=args.output,
        camera_args=args.camera_arg,
    )
    payload = predict_image(image_path, args.checkpoint, device_name=args.device, top_k=args.top_k)

    csv_path, json_path = write_inference_record(
        payload,
        confirmed_label=args.confirmed_label,
        notes=args.notes,
    )
    record_paths = {
        "csv": repo_relative(csv_path),
        "json": repo_relative(json_path),
    }

    if args.json:
        output_payload = dict(payload)
        output_payload["record_paths"] = record_paths
        print(json.dumps(output_payload, indent=2))
        return

    print(format_prediction_report(payload, record_paths=record_paths))


if __name__ == "__main__":
    main()
