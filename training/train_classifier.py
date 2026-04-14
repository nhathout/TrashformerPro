from __future__ import annotations

import argparse
import csv
import json
import platform
import random
import socket
import subprocess
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import torch
import torchvision
from PIL import Image
from torch import nn
from torch.optim import AdamW
from torch.utils.data import DataLoader, Dataset

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from training.modeling import AVAILABLE_MODELS, build_eval_transform, build_model, build_train_transform
from training.utils import read_manifest, repo_root

REPO_ROOT = repo_root()


class ManifestDataset(Dataset):
    def __init__(
        self,
        rows: list[dict[str, str]],
        class_names: list[str],
        transform,
    ) -> None:
        self.rows = rows
        self.class_names = class_names
        self.class_to_index = {name: index for index, name in enumerate(class_names)}
        self.transform = transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        row = self.rows[index]
        image_path = REPO_ROOT / row["filepath"]
        image = Image.open(image_path).convert("RGB")
        label = self.class_to_index[row["target_class"]]
        return self.transform(image), label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train a four-class TrashformerPro image classifier.")
    parser.add_argument(
        "--train-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/train.csv"),
    )
    parser.add_argument(
        "--val-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/val.csv"),
    )
    parser.add_argument(
        "--test-manifest",
        type=Path,
        default=Path("datasets/manifests/four_class/standardized_256/test.csv"),
    )
    parser.add_argument("--model", choices=AVAILABLE_MODELS, default="mobilenet_v3_large")
    parser.add_argument("--epochs", type=int, default=15)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--learning-rate", type=float, default=3e-4)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument("--img-size", type=int, default=224)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--label-smoothing", type=float, default=0.1)
    parser.add_argument("--patience", type=int, default=5)
    parser.add_argument("--device", type=str, default="auto", help="auto, cuda, mps, or cpu")
    parser.add_argument("--no-pretrained", action="store_true")
    parser.add_argument(
        "--init-checkpoint",
        type=Path,
        default=None,
        help="Optional existing TrashformerPro checkpoint to load before training for fine-tuning.",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("training/runs"))
    parser.add_argument("--run-name", type=str, default=None)
    return parser.parse_args()


def set_seed(seed: int) -> None:
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)


def resolve_device(device_name: str) -> torch.device:
    if device_name == "auto":
        if torch.cuda.is_available():
            return torch.device("cuda")
        if torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    return torch.device(device_name)


def build_class_weights(train_rows: list[dict[str, str]], class_names: list[str], device: torch.device) -> torch.Tensor:
    counts = Counter(row["target_class"] for row in train_rows)
    total = len(train_rows)
    weights = [total / (len(class_names) * counts[class_name]) for class_name in class_names]
    return torch.tensor(weights, dtype=torch.float32, device=device)


def run_epoch(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    device: torch.device,
    optimizer: AdamW | None,
) -> dict[str, float]:
    training = optimizer is not None
    if training:
        model.train()
    else:
        model.eval()

    total_loss = 0.0
    total_correct = 0
    total_examples = 0

    for inputs, labels in loader:
        inputs = inputs.to(device)
        labels = labels.to(device)

        if training:
            optimizer.zero_grad(set_to_none=True)

        with torch.set_grad_enabled(training):
            logits = model(inputs)
            loss = criterion(logits, labels)
            if training:
                loss.backward()
                optimizer.step()

        predictions = logits.argmax(dim=1)
        batch_size = labels.size(0)
        total_loss += loss.item() * batch_size
        total_correct += (predictions == labels).sum().item()
        total_examples += batch_size

    return {
        "loss": total_loss / max(total_examples, 1),
        "accuracy": total_correct / max(total_examples, 1),
    }


def evaluate_with_confusion_matrix(
    model: nn.Module,
    loader: DataLoader,
    criterion: nn.Module,
    class_names: list[str],
    device: torch.device,
) -> tuple[dict[str, float], list[list[int]]]:
    model.eval()
    matrix = [[0 for _ in class_names] for _ in class_names]
    total_loss = 0.0
    total_examples = 0

    with torch.no_grad():
        for inputs, labels in loader:
            inputs = inputs.to(device)
            labels = labels.to(device)

            logits = model(inputs)
            loss = criterion(logits, labels)
            predictions = logits.argmax(dim=1)

            batch_size = labels.size(0)
            total_loss += loss.item() * batch_size
            total_examples += batch_size

            for true_label, predicted_label in zip(labels.tolist(), predictions.tolist()):
                matrix[true_label][predicted_label] += 1

    metrics = classification_metrics(matrix, class_names)
    metrics["loss"] = total_loss / max(total_examples, 1)
    return metrics, matrix


def classification_metrics(matrix: list[list[int]], class_names: list[str]) -> dict[str, object]:
    total = sum(sum(row) for row in matrix)
    correct = sum(matrix[index][index] for index in range(len(class_names)))

    per_class = []
    f1_values = []
    precision_values = []
    recall_values = []

    for index, class_name in enumerate(class_names):
        true_positives = matrix[index][index]
        false_positives = sum(matrix[row][index] for row in range(len(class_names)) if row != index)
        false_negatives = sum(matrix[index][column] for column in range(len(class_names)) if column != index)
        support = sum(matrix[index])

        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0.0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0.0
        f1_score = (
            2 * precision * recall / (precision + recall)
            if (precision + recall)
            else 0.0
        )

        per_class.append(
            {
                "class_name": class_name,
                "support": support,
                "precision": precision,
                "recall": recall,
                "f1": f1_score,
            }
        )
        precision_values.append(precision)
        recall_values.append(recall)
        f1_values.append(f1_score)

    return {
        "accuracy": correct / max(total, 1),
        "macro_precision": sum(precision_values) / max(len(precision_values), 1),
        "macro_recall": sum(recall_values) / max(len(recall_values), 1),
        "macro_f1": sum(f1_values) / max(len(f1_values), 1),
        "per_class": per_class,
    }


def save_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def get_git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    return completed.stdout.strip() or None


def collect_environment_info(device: torch.device) -> dict[str, object]:
    info: dict[str, object] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "torch_version": torch.__version__,
        "torchvision_version": torchvision.__version__,
        "git_commit": get_git_commit(),
        "selected_device": str(device),
        "cuda_available": torch.cuda.is_available(),
        "cuda_runtime_version": torch.version.cuda,
        "mps_available": torch.backends.mps.is_available(),
        "cudnn_enabled": torch.backends.cudnn.enabled,
        "cudnn_version": torch.backends.cudnn.version(),
    }

    if device.type == "cuda" and torch.cuda.is_available():
        current_index = torch.cuda.current_device()
        info["cuda_device_count"] = torch.cuda.device_count()
        info["cuda_device_name"] = torch.cuda.get_device_name(current_index)
        info["cuda_device_capability"] = list(torch.cuda.get_device_capability(current_index))

    return info


def save_checkpoint(
    path: Path,
    model: nn.Module,
    *,
    model_name: str,
    class_names: list[str],
    img_size: int,
    epoch: int,
    metrics: dict[str, float],
    pretrained: bool,
) -> None:
    torch.save(
        {
            "model_state": model.state_dict(),
            "model_name": model_name,
            "class_names": class_names,
            "img_size": img_size,
            "epoch": epoch,
            "metrics": metrics,
            "pretrained": pretrained,
        },
        path,
    )


def load_initial_checkpoint(
    path: Path,
    *,
    model: nn.Module,
    expected_model_name: str,
    expected_class_names: list[str],
) -> dict[str, object]:
    checkpoint_path = path if path.is_absolute() else REPO_ROOT / path
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Initial checkpoint does not exist: {checkpoint_path}")

    payload = torch.load(checkpoint_path, map_location="cpu")
    checkpoint_model_name = payload["model_name"]
    checkpoint_class_names = list(payload["class_names"])

    if checkpoint_model_name != expected_model_name:
        raise ValueError(
            f"Initial checkpoint model mismatch: expected {expected_model_name}, got {checkpoint_model_name}."
        )

    if checkpoint_class_names != expected_class_names:
        raise ValueError(
            "Initial checkpoint classes do not match the current manifests: "
            f"expected {expected_class_names}, got {checkpoint_class_names}."
        )

    model.load_state_dict(payload["model_state"])
    resolved_path = checkpoint_path.resolve()
    try:
        display_path = str(resolved_path.relative_to(REPO_ROOT.resolve()))
    except ValueError:
        display_path = str(resolved_path)
    return {
        "path": display_path,
        "epoch": payload.get("epoch"),
        "metrics": payload.get("metrics", {}),
    }


def main() -> None:
    args = parse_args()
    set_seed(args.seed)

    device = resolve_device(args.device)
    loading_existing_checkpoint = args.init_checkpoint is not None
    pretrained = (not args.no_pretrained) and not loading_existing_checkpoint

    train_rows = read_manifest(args.train_manifest)
    val_rows = read_manifest(args.val_manifest)
    test_rows = read_manifest(args.test_manifest) if args.test_manifest.exists() else []

    class_names = sorted({row["target_class"] for row in train_rows})
    train_dataset = ManifestDataset(train_rows, class_names, build_train_transform(args.img_size))
    val_dataset = ManifestDataset(val_rows, class_names, build_eval_transform(args.img_size))
    test_dataset = ManifestDataset(test_rows, class_names, build_eval_transform(args.img_size)) if test_rows else None

    pin_memory = device.type == "cuda"
    train_loader = DataLoader(
        train_dataset,
        batch_size=args.batch_size,
        shuffle=True,
        num_workers=args.workers,
        pin_memory=pin_memory,
    )
    val_loader = DataLoader(
        val_dataset,
        batch_size=args.batch_size,
        shuffle=False,
        num_workers=args.workers,
        pin_memory=pin_memory,
    )
    test_loader = (
        DataLoader(
            test_dataset,
            batch_size=args.batch_size,
            shuffle=False,
            num_workers=args.workers,
            pin_memory=pin_memory,
        )
        if test_dataset is not None
        else None
    )

    model = build_model(args.model, len(class_names), pretrained=pretrained).to(device)
    init_checkpoint_info: dict[str, object] | None = None
    if args.init_checkpoint is not None:
        init_checkpoint_info = load_initial_checkpoint(
            args.init_checkpoint,
            model=model,
            expected_model_name=args.model,
            expected_class_names=class_names,
        )

    class_weights = build_class_weights(train_rows, class_names, device)
    criterion = nn.CrossEntropyLoss(weight=class_weights, label_smoothing=args.label_smoothing)
    optimizer = AdamW(model.parameters(), lr=args.learning_rate, weight_decay=args.weight_decay)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_name = args.run_name or f"{timestamp}_{args.model}"
    run_dir = args.output_dir / run_name
    run_dir.mkdir(parents=True, exist_ok=True)

    config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "pretrained": pretrained,
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "weight_decay": args.weight_decay,
        "img_size": args.img_size,
        "workers": args.workers,
        "seed": args.seed,
        "label_smoothing": args.label_smoothing,
        "patience": args.patience,
        "device": str(device),
        "train_manifest": str(args.train_manifest),
        "val_manifest": str(args.val_manifest),
        "test_manifest": str(args.test_manifest),
        "class_names": class_names,
        "class_weights": class_weights.detach().cpu().tolist(),
        "train_examples": len(train_rows),
        "val_examples": len(val_rows),
        "test_examples": len(test_rows),
        "init_checkpoint": init_checkpoint_info,
        "environment": collect_environment_info(device),
    }
    save_json(run_dir / "config.json", config)

    history_path = run_dir / "history.csv"
    with history_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["epoch", "train_loss", "train_accuracy", "val_loss", "val_accuracy"],
        )
        writer.writeheader()

    best_val_accuracy = -1.0
    best_epoch = -1
    epochs_without_improvement = 0
    started_at = time.time()

    for epoch in range(1, args.epochs + 1):
        train_metrics = run_epoch(model, train_loader, criterion, device, optimizer)
        val_metrics = run_epoch(model, val_loader, criterion, device, optimizer=None)

        history_row = {
            "epoch": epoch,
            "train_loss": train_metrics["loss"],
            "train_accuracy": train_metrics["accuracy"],
            "val_loss": val_metrics["loss"],
            "val_accuracy": val_metrics["accuracy"],
        }
        with history_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=["epoch", "train_loss", "train_accuracy", "val_loss", "val_accuracy"],
            )
            writer.writerow(history_row)

        print(
            f"Epoch {epoch:02d}/{args.epochs} | "
            f"train loss {train_metrics['loss']:.4f} | train acc {train_metrics['accuracy']:.4f} | "
            f"val loss {val_metrics['loss']:.4f} | val acc {val_metrics['accuracy']:.4f}"
        )

        if val_metrics["accuracy"] > best_val_accuracy:
            best_val_accuracy = val_metrics["accuracy"]
            best_epoch = epoch
            epochs_without_improvement = 0
            save_checkpoint(
                run_dir / "best.pt",
                model,
                model_name=args.model,
                class_names=class_names,
                img_size=args.img_size,
                epoch=epoch,
                metrics=val_metrics,
                pretrained=pretrained,
            )
        else:
            epochs_without_improvement += 1

        save_checkpoint(
            run_dir / "last.pt",
            model,
            model_name=args.model,
            class_names=class_names,
            img_size=args.img_size,
            epoch=epoch,
            metrics=val_metrics,
            pretrained=pretrained,
        )

        if epochs_without_improvement >= args.patience:
            print(f"Early stopping triggered after {epoch} epochs.")
            break

    best_payload = torch.load(run_dir / "best.pt", map_location=device)
    model.load_state_dict(best_payload["model_state"])

    summary = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "best_epoch": best_epoch,
        "best_val_accuracy": best_val_accuracy,
        "epochs_completed": epoch,
        "training_time_seconds": time.time() - started_at,
    }

    if test_loader is not None:
        test_metrics, confusion_matrix = evaluate_with_confusion_matrix(
            model,
            test_loader,
            criterion,
            class_names,
            device,
        )
        save_json(run_dir / "test_metrics.json", test_metrics)
        save_json(
            run_dir / "test_confusion_matrix.json",
            {"class_names": class_names, "matrix": confusion_matrix},
        )
        summary["test_accuracy"] = test_metrics["accuracy"]
        summary["test_macro_f1"] = test_metrics["macro_f1"]

    save_json(run_dir / "summary.json", summary)
    print(f"Saved training artifacts to: {run_dir}")


if __name__ == "__main__":
    main()
