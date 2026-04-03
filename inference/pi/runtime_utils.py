from __future__ import annotations

import csv
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = REPO_ROOT / "runtime"
CAPTURES_DIR = RUNTIME_ROOT / "captures"
INFERENCE_RECORDS_DIR = RUNTIME_ROOT / "inference_records"
INFERENCE_JSON_DIR = INFERENCE_RECORDS_DIR / "json"

CSV_FIELDNAMES = [
    "record_id",
    "timestamp_utc",
    "image_path",
    "predicted_class",
    "predicted_confidence",
    "checkpoint_path",
    "model_name",
    "device",
    "confirmed_label",
    "notes",
    "top_predictions_json",
]


def ensure_runtime_dirs() -> None:
    for path in (CAPTURES_DIR, INFERENCE_RECORDS_DIR, INFERENCE_JSON_DIR, RUNTIME_ROOT / "models"):
        path.mkdir(parents=True, exist_ok=True)


def repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def capture_image(
    prefix: str = "capture",
    output_path: Path | None = None,
    camera_args: list[str] | None = None,
) -> Path:
    ensure_runtime_dirs()

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = CAPTURES_DIR / f"{prefix}_{timestamp}.jpg"
    else:
        output_path = resolve_repo_path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "rpicam-still",
        "--nopreview",
        "-o",
        str(output_path),
    ]
    if camera_args:
        command.extend(camera_args)

    subprocess.run(command, check=True)
    return output_path


def write_inference_record(
    payload: dict[str, Any],
    confirmed_label: str = "",
    notes: str = "",
) -> tuple[Path, Path]:
    ensure_runtime_dirs()

    timestamp = payload.get("timestamp_utc", datetime.now(timezone.utc).isoformat())
    record_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ")

    record = dict(payload)
    record["record_id"] = record_id
    record["confirmed_label"] = confirmed_label
    record["notes"] = notes

    json_path = INFERENCE_JSON_DIR / f"{record_id}.json"
    json_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

    csv_path = INFERENCE_RECORDS_DIR / "predictions.csv"
    row = {
        "record_id": record_id,
        "timestamp_utc": timestamp,
        "image_path": payload["image"],
        "predicted_class": payload["predictions"][0]["class_name"],
        "predicted_confidence": f"{payload['predictions'][0]['confidence']:.6f}",
        "checkpoint_path": payload["checkpoint"],
        "model_name": payload["model_name"],
        "device": payload["device"],
        "confirmed_label": confirmed_label,
        "notes": notes,
        "top_predictions_json": json.dumps(payload["predictions"]),
    }

    file_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return csv_path, json_path
