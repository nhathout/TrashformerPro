from __future__ import annotations

import argparse
import json
import platform
import socket
import subprocess
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether the current Python environment is ready for TrashformerPro training."
    )
    parser.add_argument(
        "--expect-device",
        choices=("any", "cuda", "mps", "cpu"),
        default="any",
        help="Fail if the preferred device is not available.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print environment information as JSON.",
    )
    return parser.parse_args()


def maybe_run_command(command: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None

    return completed.stdout.strip() or None


def main() -> None:
    args = parse_args()

    try:
        import torch
        import torchvision
        from PIL import Image
    except ImportError as exc:
        print(f"Environment check failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    selected_device = "cpu"
    if torch.cuda.is_available():
        selected_device = "cuda"
    elif torch.backends.mps.is_available():
        selected_device = "mps"

    info: dict[str, object] = {
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "hostname": socket.gethostname(),
        "torch_version": torch.__version__,
        "torchvision_version": torchvision.__version__,
        "pillow_version": Image.__version__,
        "cuda_available": torch.cuda.is_available(),
        "cuda_runtime_version": torch.version.cuda,
        "mps_available": torch.backends.mps.is_available(),
        "selected_device": selected_device,
        "git_commit": maybe_run_command(["git", "rev-parse", "HEAD"]),
    }

    if torch.cuda.is_available():
        info["cuda_device_count"] = torch.cuda.device_count()
        devices = []
        for index in range(torch.cuda.device_count()):
            devices.append(
                {
                    "index": index,
                    "name": torch.cuda.get_device_name(index),
                    "capability": list(torch.cuda.get_device_capability(index)),
                }
            )
        info["cuda_devices"] = devices

    nvidia_smi = maybe_run_command(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
    if nvidia_smi is not None:
        info["nvidia_smi"] = nvidia_smi.splitlines()

    if args.json:
        print(json.dumps(info, indent=2))
    else:
        for key, value in info.items():
            print(f"{key}: {value}")

    if args.expect_device != "any" and selected_device != args.expect_device:
        print(
            f"Expected device '{args.expect_device}' but detected '{selected_device}'.",
            file=sys.stderr,
        )
        raise SystemExit(2)


if __name__ == "__main__":
    main()
