from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from inference.pi.runtime_utils import (
    describe_checkpoint_file,
    repo_relative,
    resolve_checkpoint_path,
    resolve_repo_path,
    write_inference_record,
)
from training.modeling import build_eval_transform, build_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single-image TrashformerPro classification inference pass.")
    parser.add_argument("--image", type=Path, required=True, help="Path to the captured image.")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=None,
        help="Path to a .pt checkpoint from training. Defaults to models/best.pt, then runtime/models/best.pt.",
    )
    parser.add_argument("--device", type=str, default="auto", help="auto, cuda, mps, or cpu")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument(
        "--confirmed-label",
        type=str,
        default="",
        help="Optional human-confirmed label to store alongside the prediction record.",
    )
    parser.add_argument("--notes", type=str, default="", help="Optional notes to store with the prediction record.")
    parser.add_argument(
        "--no-record",
        action="store_true",
        help="Skip writing runtime/inference_records metadata for this inference.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON instead of plain text.")
    return parser.parse_args()


def resolve_device(device_name: str) -> torch.device:
    if device_name == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    return torch.device(device_name)


def predict_image(
    image_path: Path,
    checkpoint_path: Path | None,
    device_name: str = "auto",
    top_k: int = 4,
) -> dict[str, object]:
    image_path = resolve_repo_path(image_path)
    checkpoint_path = resolve_checkpoint_path(checkpoint_path)
    checkpoint_file_info = describe_checkpoint_file(checkpoint_path)
    device = resolve_device(device_name)

    checkpoint = torch.load(checkpoint_path, map_location=device)
    class_names = checkpoint["class_names"]
    model_name = checkpoint["model_name"]
    img_size = int(checkpoint.get("img_size", 224))

    model = build_model(model_name, len(class_names), pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    image = Image.open(image_path).convert("RGB")
    transform = build_eval_transform(img_size)
    input_tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(input_tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu()

    top_k = min(top_k, len(class_names))
    top_values, top_indices = torch.topk(probabilities, k=top_k)
    results = [
        {
            "class_name": class_names[index],
            "confidence": float(value),
        }
        for value, index in zip(top_values.tolist(), top_indices.tolist())
    ]

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "image": repo_relative(image_path),
        **checkpoint_file_info,
        "device": str(device),
        "model_name": model_name,
        "img_size": img_size,
        "class_names": class_names,
        "checkpoint_epoch": checkpoint.get("epoch"),
        "checkpoint_metrics": checkpoint.get("metrics", {}),
        "predictions": results,
    }


def format_prediction_report(payload: dict[str, object], record_paths: dict[str, str] | None = None) -> str:
    predictions = payload["predictions"]
    assert isinstance(predictions, list)

    lines = [
        f"Image: {payload['image']}",
        f"Checkpoint: {payload['checkpoint']} [{str(payload['checkpoint_sha256'])[:12]}]",
        f"Predicted class: {predictions[0]['class_name']} ({predictions[0]['confidence']:.4f})",
        "Top predictions:",
    ]
    for item in predictions:
        lines.append(f"  {item['class_name']}: {item['confidence']:.4f}")

    if record_paths is not None:
        lines.append(f"Record JSON: {record_paths['json']}")
        lines.append(f"Record CSV: {record_paths['csv']}")

    return "\n".join(lines)


def main() -> None:
    args = parse_args()
    payload = predict_image(args.image, args.checkpoint, device_name=args.device, top_k=args.top_k)

    record_paths: dict[str, str] | None = None
    if not args.no_record:
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
        if record_paths is not None:
            output_payload["record_paths"] = record_paths
        print(json.dumps(output_payload, indent=2))
        return

    print(format_prediction_report(payload, record_paths=record_paths))


if __name__ == "__main__":
    main()
