from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.modeling import build_eval_transform, build_model


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a single-image TrashformerPro classification inference pass.")
    parser.add_argument("--image", type=Path, required=True, help="Path to the captured image.")
    parser.add_argument("--checkpoint", type=Path, required=True, help="Path to a .pt checkpoint from training.")
    parser.add_argument("--device", type=str, default="auto", help="auto, cuda, mps, or cpu")
    parser.add_argument("--top-k", type=int, default=4)
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


def main() -> None:
    args = parse_args()
    device = resolve_device(args.device)

    checkpoint = torch.load(args.checkpoint, map_location=device)
    class_names = checkpoint["class_names"]
    model_name = checkpoint["model_name"]
    img_size = int(checkpoint.get("img_size", 224))

    model = build_model(model_name, len(class_names), pretrained=False)
    model.load_state_dict(checkpoint["model_state"])
    model.to(device)
    model.eval()

    image = Image.open(args.image).convert("RGB")
    transform = build_eval_transform(img_size)
    input_tensor = transform(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(input_tensor)
        probabilities = torch.softmax(logits, dim=1)[0].cpu()

    top_k = min(args.top_k, len(class_names))
    top_values, top_indices = torch.topk(probabilities, k=top_k)
    results = [
        {
            "class_name": class_names[index],
            "confidence": float(value),
        }
        for value, index in zip(top_values.tolist(), top_indices.tolist())
    ]

    if args.json:
        print(json.dumps({"image": str(args.image), "predictions": results}, indent=2))
        return

    print(f"Image: {args.image}")
    print(f"Predicted class: {results[0]['class_name']} ({results[0]['confidence']:.4f})")
    print("Top predictions:")
    for item in results:
        print(f"  {item['class_name']}: {item['confidence']:.4f}")


if __name__ == "__main__":
    main()
