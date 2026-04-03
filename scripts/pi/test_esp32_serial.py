#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.pi.hardware_config import DEFAULT_SERIAL_BAUD


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify that an ESP32 dev board is reachable from the Pi over USB serial.")
    parser.add_argument("--port", type=str, default="auto", help="Serial port path, or `auto` to scan common USB serial ports.")
    parser.add_argument("--baud", type=int, default=DEFAULT_SERIAL_BAUD, help="Baud rate for the ESP32 serial console.")
    parser.add_argument("--timeout", type=float, default=5.0, help="Read timeout in seconds.")
    parser.add_argument("--list", action="store_true", help="Only list candidate serial ports and exit.")
    parser.add_argument(
        "--monitor-seconds",
        type=float,
        default=4.0,
        help="How long to watch for extra ESP32 output after the handshake.",
    )
    return parser.parse_args()


def import_serial():
    try:
        import serial  # type: ignore
        from serial.tools import list_ports  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "pyserial is not installed for this Python interpreter. "
            "On the Pi, run `bash scripts/pi/setup_pi.sh` first."
        ) from exc
    return serial, list_ports


def candidate_ports(list_ports_module) -> list[str]:
    ports = []
    by_id_dir = Path("/dev/serial/by-id")
    if by_id_dir.exists():
        ports.extend(sorted(str(path.resolve()) for path in by_id_dir.iterdir()))

    for port in list_ports_module.comports():
        if port.device not in ports:
            ports.append(port.device)

    preferred = [port for port in ports if "ttyUSB" in port or "ttyACM" in port]
    remainder = [port for port in ports if port not in preferred]
    return preferred + remainder


def resolve_port(port_arg: str, list_ports_module) -> str:
    if port_arg != "auto":
        return port_arg

    ports = candidate_ports(list_ports_module)
    if not ports:
        raise SystemExit(
            "No serial ports found. Connect the ESP32 to the Raspberry Pi over USB and try again."
        )
    return ports[0]


def main() -> None:
    args = parse_args()
    serial, list_ports_module = import_serial()
    ports = candidate_ports(list_ports_module)

    if args.list:
        if not ports:
            print("No candidate serial ports found.")
            return
        print("Candidate serial ports:")
        for port in ports:
            print(f"  {port}")
        return

    port = resolve_port(args.port, list_ports_module)
    print(f"Opening {port} at {args.baud} baud")

    with serial.Serial(port, args.baud, timeout=0.25) as connection:
        # Many ESP32 dev boards reset when the serial port opens.
        time.sleep(2.0)
        connection.reset_input_buffer()
        connection.write(b"ping\n")
        connection.flush()

        deadline = time.time() + args.timeout
        saw_pong = False
        while time.time() < deadline:
            raw_line = connection.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            print(f"[ESP32] {line}")
            if line.lower() == "pong":
                saw_pong = True
                break

        if not saw_pong:
            raise SystemExit(
                "Did not receive `pong` from the ESP32. Make sure the test firmware is flashed and the baud rate matches."
            )

        print("Handshake success. Monitoring additional serial output...")
        monitor_deadline = time.time() + args.monitor_seconds
        while time.time() < monitor_deadline:
            raw_line = connection.readline()
            if not raw_line:
                continue
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line:
                print(f"[ESP32] {line}")

    print("ESP32 serial test complete.")


if __name__ == "__main__":
    main()
