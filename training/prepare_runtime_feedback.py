from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.utils import read_manifest, write_manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build combined fine-tuning manifests from manually confirmed Pi runtime predictions."
    )
    parser.add_argument(
        "--predictions-csv",
        type=Path,
        default=Path("runtime/inference_records/predictions.csv"),
        help="Prediction log with confirmed_label values filled in.",
    )
    parser.add_argument(
        "--base-train-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/train.csv"),
    )
    parser.add_argument(
        "--base-val-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/val.csv"),
    )
    parser.add_argument(
        "--base-test-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/test.csv"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("datasets/manifests/four_class/runtime_feedback"),
        help="Directory where feedback-only and combined manifests will be written.",
    )
    parser.add_argument("--feedback-variant", type=str, default="runtime_feedback")
    parser.add_argument("--feedback-train-ratio", type=float, default=0.8)
    parser.add_argument("--feedback-val-ratio", type=float, default=0.2)
    parser.add_argument("--feedback-test-ratio", type=float, default=0.0)
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args()


def resolve_repo_path(path: Path) -> Path:
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def to_repo_relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(resolved)


def read_predictions_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def feedback_split_counts(
    total: int,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
) -> tuple[int, int, int]:
    ratio_total = train_ratio + val_ratio + test_ratio
    if abs(ratio_total - 1.0) > 1e-9:
        raise ValueError("feedback train/val/test ratios must sum to 1.0")

    val_count = int(total * val_ratio)
    test_count = int(total * test_ratio)
    train_count = total - val_count - test_count
    return train_count, val_count, test_count


def choose_latest_confirmed_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[str, int]]:
    latest_by_image: dict[str, dict[str, str]] = {}
    stats = {
        "total_rows": len(rows),
        "rows_without_confirmed_label": 0,
        "duplicate_confirmed_rows": 0,
    }

    for row in rows:
        confirmed_label = row.get("confirmed_label", "").strip()
        if not confirmed_label:
            stats["rows_without_confirmed_label"] += 1
            continue

        image_path = row.get("image_path", "").strip()
        if not image_path:
            continue

        if image_path in latest_by_image:
            stats["duplicate_confirmed_rows"] += 1
        latest_by_image[image_path] = row

    return list(latest_by_image.values()), stats


def build_feedback_rows(
    confirmed_rows: list[dict[str, str]],
    *,
    allowed_classes: set[str],
    feedback_variant: str,
) -> tuple[list[dict[str, str]], list[str]]:
    feedback_rows: list[dict[str, str]] = []
    missing_images: list[str] = []

    for row in confirmed_rows:
        confirmed_label = row["confirmed_label"].strip()
        if confirmed_label not in allowed_classes:
            raise ValueError(
                f"Unsupported confirmed_label '{confirmed_label}' for image {row.get('image_path', '')}. "
                f"Expected one of: {sorted(allowed_classes)}"
            )

        image_path = row["image_path"].strip()
        resolved_image = resolve_repo_path(Path(image_path))
        if not resolved_image.exists():
            missing_images.append(image_path)
            continue

        predicted_class = row.get("predicted_class", "").strip()
        feedback_rows.append(
            {
                "filepath": to_repo_relative(resolved_image),
                "source_class": predicted_class or confirmed_label,
                "target_class": confirmed_label,
                "split": "",
                "variant": feedback_variant,
            }
        )

    return feedback_rows, missing_images


def stratified_feedback_split(
    feedback_rows: list[dict[str, str]],
    *,
    train_ratio: float,
    val_ratio: float,
    test_ratio: float,
    seed: int,
) -> dict[str, list[dict[str, str]]]:
    rows_by_split: dict[str, list[dict[str, str]]] = {"train": [], "val": [], "test": []}
    rows_by_class: dict[str, list[dict[str, str]]] = defaultdict(list)
    rng = random.Random(seed)

    for row in feedback_rows:
        rows_by_class[row["target_class"]].append(dict(row))

    for class_rows in rows_by_class.values():
        shuffled = list(class_rows)
        rng.shuffle(shuffled)
        train_count, val_count, test_count = feedback_split_counts(
            len(shuffled),
            train_ratio,
            val_ratio,
            test_ratio,
        )
        split_map = {
            "train": shuffled[:train_count],
            "val": shuffled[train_count : train_count + val_count],
            "test": shuffled[train_count + val_count : train_count + val_count + test_count],
        }
        for split_name, split_rows in split_map.items():
            for row in split_rows:
                row["split"] = split_name
                rows_by_split[split_name].append(row)

    return rows_by_split


def main() -> None:
    args = parse_args()
    ratio_total = args.feedback_train_ratio + args.feedback_val_ratio + args.feedback_test_ratio
    if abs(ratio_total - 1.0) > 1e-9:
        raise SystemExit("feedback train/val/test ratios must sum to 1.0")

    predictions_csv = resolve_repo_path(args.predictions_csv)
    if not predictions_csv.exists():
        raise SystemExit(f"Predictions CSV does not exist: {predictions_csv}")

    base_train_manifest = resolve_repo_path(args.base_train_manifest)
    base_val_manifest = resolve_repo_path(args.base_val_manifest)
    base_test_manifest = resolve_repo_path(args.base_test_manifest)

    base_train_rows = read_manifest(base_train_manifest)
    base_val_rows = read_manifest(base_val_manifest)
    base_test_rows = read_manifest(base_test_manifest) if base_test_manifest.exists() else []
    allowed_classes = {row["target_class"] for row in base_train_rows}

    prediction_rows = read_predictions_csv(predictions_csv)
    confirmed_rows, selection_stats = choose_latest_confirmed_rows(prediction_rows)
    if not confirmed_rows:
        raise SystemExit(
            "No confirmed_label values were found in runtime/inference_records/predictions.csv. "
            "Fill in that column for the samples you want to use in fine-tuning."
        )

    feedback_rows, missing_images = build_feedback_rows(
        confirmed_rows,
        allowed_classes=allowed_classes,
        feedback_variant=args.feedback_variant,
    )
    if not feedback_rows:
        raise SystemExit("Confirmed rows were found, but none pointed to images that still exist on disk.")

    feedback_rows_by_split = stratified_feedback_split(
        feedback_rows,
        train_ratio=args.feedback_train_ratio,
        val_ratio=args.feedback_val_ratio,
        test_ratio=args.feedback_test_ratio,
        seed=args.seed,
    )

    output_dir = resolve_repo_path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    feedback_all_rows = (
        feedback_rows_by_split["train"] + feedback_rows_by_split["val"] + feedback_rows_by_split["test"]
    )
    feedback_train_path = output_dir / "feedback_train.csv"
    feedback_val_path = output_dir / "feedback_val.csv"
    feedback_test_path = output_dir / "feedback_test.csv"
    feedback_all_path = output_dir / "feedback_all.csv"
    combined_train_path = output_dir / "train.csv"
    combined_val_path = output_dir / "val.csv"
    combined_test_path = output_dir / "test.csv"

    write_manifest(feedback_train_path, feedback_rows_by_split["train"])
    write_manifest(feedback_val_path, feedback_rows_by_split["val"])
    write_manifest(feedback_test_path, feedback_rows_by_split["test"])
    write_manifest(feedback_all_path, feedback_all_rows)
    write_manifest(combined_train_path, base_train_rows + feedback_rows_by_split["train"])
    write_manifest(combined_val_path, base_val_rows + feedback_rows_by_split["val"])
    write_manifest(combined_test_path, base_test_rows + feedback_rows_by_split["test"])

    feedback_class_counts = Counter(row["target_class"] for row in feedback_all_rows)
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "predictions_csv": to_repo_relative(predictions_csv),
        "base_manifests": {
            "train": to_repo_relative(base_train_manifest),
            "val": to_repo_relative(base_val_manifest),
            "test": to_repo_relative(base_test_manifest),
        },
        "output_files": {
            "feedback_train": to_repo_relative(feedback_train_path),
            "feedback_val": to_repo_relative(feedback_val_path),
            "feedback_test": to_repo_relative(feedback_test_path),
            "feedback_all": to_repo_relative(feedback_all_path),
            "combined_train": to_repo_relative(combined_train_path),
            "combined_val": to_repo_relative(combined_val_path),
            "combined_test": to_repo_relative(combined_test_path),
        },
        "selection_stats": selection_stats,
        "feedback_examples_total": len(feedback_all_rows),
        "feedback_examples_by_class": dict(sorted(feedback_class_counts.items())),
        "feedback_examples_by_split": {
            split_name: len(split_rows)
            for split_name, split_rows in feedback_rows_by_split.items()
        },
        "combined_examples_by_split": {
            "train": len(base_train_rows) + len(feedback_rows_by_split["train"]),
            "val": len(base_val_rows) + len(feedback_rows_by_split["val"]),
            "test": len(base_test_rows) + len(feedback_rows_by_split["test"]),
        },
        "missing_images_count": len(missing_images),
        "missing_images": missing_images,
        "seed": args.seed,
    }

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Prepared runtime feedback manifests in: {to_repo_relative(output_dir)}")
    print(f"Feedback examples: {len(feedback_all_rows)}")
    for class_name, count in sorted(feedback_class_counts.items()):
        print(f"  {class_name}: {count}")
    print(f"Summary: {to_repo_relative(summary_path)}")


if __name__ == "__main__":
    main()
