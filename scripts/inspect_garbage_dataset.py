from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.utils import collect_images_by_class, invert_class_mapping, load_class_mapping


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect Garbage V2 counts without accidentally triple-counting resized variants."
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("data/raw/garbage_v2"),
        help="Dataset root that contains original/standardized_* variant folders.",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default="standardized_256",
        help="Single variant to inspect. Use one of original, standardized_256, standardized_384.",
    )
    parser.add_argument(
        "--mapping",
        type=Path,
        default=Path("datasets/mappings/four_class_map.yaml"),
        help="Four-class mapping file used to report collapsed counts.",
    )
    return parser.parse_args()


def print_counter(title: str, counts: Counter[str]) -> None:
    print(f"\n{title}")
    for class_name, count in sorted(counts.items()):
        print(f"{class_name}: {count}")


def main() -> None:
    args = parse_args()
    variant_root = args.root / args.variant
    images_by_class = collect_images_by_class(variant_root)

    source_counts = Counter({class_name: len(paths) for class_name, paths in images_by_class.items()})
    total_images = sum(source_counts.values())

    print(f"Inspecting variant: {args.variant}")
    print(f"Variant root: {variant_root}")
    print(f"Total images found: {total_images}")
    print_counter("Images by source folder:", source_counts)

    mapping = load_class_mapping(args.mapping)
    inverse_mapping = invert_class_mapping(mapping)

    unmapped_classes = sorted(set(source_counts) - set(inverse_mapping))
    if unmapped_classes:
        print("\nUnmapped classes detected:")
        for class_name in unmapped_classes:
            print(f"{class_name}: {source_counts[class_name]}")
    else:
        collapsed_counts: Counter[str] = Counter()
        for source_class, count in source_counts.items():
            collapsed_counts[inverse_mapping[source_class]] += count
        print_counter("Images by four-class target:", collapsed_counts)

    sibling_variants = sorted(path for path in args.root.iterdir() if path.is_dir())
    if sibling_variants:
        print("\nAvailable variant folders:")
        for sibling in sibling_variants:
            sibling_total = sum(len(paths) for paths in collect_images_by_class(sibling).values())
            suffix = " <- selected" if sibling.name == args.variant else ""
            print(f"{sibling.name}: {sibling_total}{suffix}")

    print(
        "\nNote: the Kaggle download contains three parallel image variants. "
        "Inspecting the dataset root recursively will count the same examples three times."
    )


if __name__ == "__main__":
    main()
