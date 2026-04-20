from __future__ import annotations

import csv
import hashlib
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
DEFAULT_CHECKPOINT_CANDIDATES = (
    Path("models/best.pt"),
    Path("runtime/models/best.pt"),
)
DEFAULT_CAMERA_TIMEOUT_MS = 1000

CSV_FIELDNAMES = [
    "record_id",
    "timestamp_utc",
    "image_path",
    "predicted_class",
    "predicted_confidence",
    "checkpoint_path",
    "checkpoint_sha256",
    "checkpoint_epoch",
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


def resolve_checkpoint_path(path: Path | None = None) -> Path:
    if path is not None:
        resolved = resolve_repo_path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"Checkpoint does not exist: {resolved}")
        return resolved

    for candidate in DEFAULT_CHECKPOINT_CANDIDATES:
        resolved = REPO_ROOT / candidate
        if resolved.exists():
            return resolved

    searched = ", ".join(str(candidate) for candidate in DEFAULT_CHECKPOINT_CANDIDATES)
    raise FileNotFoundError(f"No checkpoint found. Looked for: {searched}")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe_checkpoint_file(path: Path | None = None) -> dict[str, Any]:
    resolved = resolve_checkpoint_path(path)
    stat = resolved.stat()
    return {
        "checkpoint": repo_relative(resolved),
        "checkpoint_sha256": file_sha256(resolved),
        "checkpoint_size_bytes": stat.st_size,
        "checkpoint_modified_utc": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
    }


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
    normalized_args = list(camera_args or [])
    if "--timeout" not in normalized_args:
        normalized_args.extend(["--timeout", str(DEFAULT_CAMERA_TIMEOUT_MS)])
    if normalized_args:
        command.extend(normalized_args)

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
        "checkpoint_sha256": payload.get("checkpoint_sha256", ""),
        "checkpoint_epoch": payload.get("checkpoint_epoch", ""),
        "model_name": payload["model_name"],
        "device": payload["device"],
        "confirmed_label": confirmed_label,
        "notes": notes,
        "top_predictions_json": json.dumps(payload["predictions"]),
    }

    if csv_path.exists():
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            existing_fieldnames = reader.fieldnames or []
            if existing_fieldnames != CSV_FIELDNAMES:
                existing_rows = list(reader)
                normalized_rows = [
                    {
                        fieldname: existing_row.get(fieldname, "")
                        for fieldname in CSV_FIELDNAMES
                    }
                    for existing_row in existing_rows
                ]
                with csv_path.open("w", encoding="utf-8", newline="") as rewrite_handle:
                    writer = csv.DictWriter(rewrite_handle, fieldnames=CSV_FIELDNAMES)
                    writer.writeheader()
                    for normalized_row in normalized_rows:
                        writer.writerow(normalized_row)

    file_exists = csv_path.exists()
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)

    return csv_path, json_path
