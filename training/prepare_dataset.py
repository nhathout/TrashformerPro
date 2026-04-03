from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.utils import (
    collect_images_by_class,
    invert_class_mapping,
    load_class_mapping,
    split_counts,
    to_repo_relative,
    write_manifest,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create reproducible train/val/test manifests for the four-class TrashformerPro task."
    )
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path("data/raw/garbage_v2"),
        help="Dataset root that contains original/standardized_* variant folders.",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default="standardized_256",
        help="Single dataset variant to use for model development.",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("datasets/mappings/four_class_map.yaml"),
        help="Mapping file that collapses Garbage V2 source classes into four TrashformerPro targets.",
    )
    parser.add_argument("--train-ratio", type=float, default=0.70)
    parser.add_argument("--val-ratio", type=float, default=0.15)
    parser.add_argument("--test-ratio", type=float, default=0.15)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Manifest output directory. Defaults to datasets/manifests/four_class/<variant>.",
    )
    return parser.parse_args()


def count_by_field(rows: list[dict[str, str]], field_name: str) -> dict[str, int]:
    counts = Counter(row[field_name] for row in rows)
    return dict(sorted(counts.items()))


def main() -> None:
    args = parse_args()

    output_dir = args.output_dir or Path("datasets/manifests/four_class") / args.variant
    variant_root = args.source_root / args.variant

    mapping = load_class_mapping(args.mapping)
    inverse_mapping = invert_class_mapping(mapping)
    images_by_class = collect_images_by_class(variant_root)

    discovered_source_classes = set(images_by_class)
    mapped_source_classes = set(inverse_mapping)
    missing_mapping = sorted(discovered_source_classes - mapped_source_classes)
    if missing_mapping:
        raise SystemExit(
            "The mapping file is missing source classes: " + ", ".join(missing_mapping)
        )

    unused_mapping = sorted(mapped_source_classes - discovered_source_classes)
    if unused_mapping:
        print("Warning: mapped classes not present in this variant:", ", ".join(unused_mapping))

    rng = random.Random(args.seed)
    rows_by_split: dict[str, list[dict[str, str]]] = {"train": [], "val": [], "test": []}

    for source_class, image_paths in sorted(images_by_class.items()):
        shuffled = list(image_paths)
        rng.shuffle(shuffled)

        train_count, val_count, test_count = split_counts(
            len(shuffled),
            args.train_ratio,
            args.val_ratio,
            args.test_ratio,
        )
        split_boundaries = {
            "train": shuffled[:train_count],
            "val": shuffled[train_count : train_count + val_count],
            "test": shuffled[train_count + val_count : train_count + val_count + test_count],
        }
        target_class = inverse_mapping[source_class]

        for split_name, split_paths in split_boundaries.items():
            for image_path in split_paths:
                rows_by_split[split_name].append(
                    {
                        "filepath": to_repo_relative(image_path),
                        "source_class": source_class,
                        "target_class": target_class,
                        "split": split_name,
                        "variant": args.variant,
                    }
                )

    for split_name, rows in rows_by_split.items():
        rows.sort(key=lambda row: (row["target_class"], row["source_class"], row["filepath"]))
        write_manifest(output_dir / f"{split_name}.csv", rows)

    all_rows = rows_by_split["train"] + rows_by_split["val"] + rows_by_split["test"]
    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "variant": args.variant,
        "source_root": str(args.source_root),
        "mapping_path": str(args.mapping),
        "seed": args.seed,
        "ratios": {
            "train": args.train_ratio,
            "val": args.val_ratio,
            "test": args.test_ratio,
        },
        "target_classes": sorted({row["target_class"] for row in all_rows}),
        "overall_source_counts": count_by_field(all_rows, "source_class"),
        "overall_target_counts": count_by_field(all_rows, "target_class"),
        "split_counts": {split: len(rows) for split, rows in rows_by_split.items()},
        "split_target_counts": {
            split: count_by_field(rows, "target_class") for split, rows in rows_by_split.items()
        },
        "split_source_counts": {
            split: count_by_field(rows, "source_class") for split, rows in rows_by_split.items()
        },
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote manifests to: {output_dir}")
    print("Split sizes:")
    for split_name, split_rows in rows_by_split.items():
        print(f"  {split_name}: {len(split_rows)}")
    print("Collapsed target counts:")
    for class_name, count in summary["overall_target_counts"].items():
        print(f"  {class_name}: {count}")


if __name__ == "__main__":
    main()
