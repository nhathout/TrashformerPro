from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_class_mapping(path: Path) -> dict[str, list[str]]:
    """Parse the simple YAML mapping used in this repo without extra dependencies."""
    mapping: dict[str, list[str]] = {}
    current_target: str | None = None

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        if not raw_line.startswith(" ") and line.endswith(":"):
            current_target = line[:-1].strip()
            mapping[current_target] = []
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            if current_target is None:
                raise ValueError(f"Malformed mapping file {path}: list item before a target class.")
            mapping[current_target].append(stripped[2:].strip())
            continue

        raise ValueError(f"Unsupported mapping line in {path}: {raw_line}")

    duplicates: dict[str, str] = {}
    for target_class, source_classes in mapping.items():
        for source_class in source_classes:
            if source_class in duplicates:
                previous_target = duplicates[source_class]
                raise ValueError(
                    f"Source class '{source_class}' is assigned to both "
                    f"'{previous_target}' and '{target_class}'."
                )
            duplicates[source_class] = target_class

    return mapping


def invert_class_mapping(mapping: dict[str, list[str]]) -> dict[str, str]:
    return {
        source_class: target_class
        for target_class, source_classes in mapping.items()
        for source_class in source_classes
    }


def collect_images_by_class(root: Path) -> dict[str, list[Path]]:
    if not root.exists():
        raise FileNotFoundError(f"Dataset root does not exist: {root}")

    images_by_class: dict[str, list[Path]] = {}
    for class_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        images = sorted(
            path
            for path in class_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        )
        if images:
            images_by_class[class_dir.name] = images
    return images_by_class


def split_counts(total: int, train_ratio: float, val_ratio: float, test_ratio: float) -> tuple[int, int, int]:
    if abs((train_ratio + val_ratio + test_ratio) - 1.0) > 1e-9:
        raise ValueError("Train, validation, and test ratios must sum to 1.0.")

    train_count = int(total * train_ratio)
    val_count = int(total * val_ratio)
    test_count = total - train_count - val_count
    return train_count, val_count, test_count


def to_repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(repo_root()))


def read_manifest(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_manifest(path: Path, rows: Iterable[dict[str, str]]) -> None:
    fieldnames = ["filepath", "source_class", "target_class", "split", "variant"]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
