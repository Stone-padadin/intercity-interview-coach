"""Capture private device logs and report observations, without claiming acceptance."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import time

ROOT = Path(__file__).resolve().parents[2]


def summarize(text):
    calibration = []
    for line in text.splitlines():
        if "CCAL frame=" in line:
            fields = dict(re.findall(r"(\w+)=(-?\d+)", line))
            calibration.append({key: int(value) for key, value in fields.items()})
    statuses = re.findall(r"status online=(\d+) phase=(\d+) visual=(\d+) pose=(\d+) led_enabled=(\d+)", text)
    return {
        "runtime_starts": text.count("runtime started;"),
        "status_reports": len(statuses),
        "last_status": dict(zip(("online", "phase", "visual", "pose", "led_enabled"), map(int, statuses[-1]))) if statuses else None,
        "pose_results": len(re.findall(r"CPOSE frame=", text)),
        "calibration_results": len(calibration),
        "max_calibration_samples": max((x.get("samples", 0) for x in calibration), default=0),
        "ready_results": sum(x.get("state") == 2 for x in calibration),
        "valid_neutral": sum(x.get("state") == 2 and x.get("valid") == 1 and x.get("stable") == 1 for x in calibration),
        "valid_deviation": sum(x.get("state") == 2 and x.get("valid") == 1 and x.get("stable") == 2 for x in calibration),
        "invalid_results": sum(x.get("valid") != 1 for x in calibration),
        "mic_packets": len(re.findall(r"mic \d+ bytes", text)),
        "offline_wakes": text.count("wakeup ignored, cloud=0"),
        "camera_init_failures": text.count("camera early init failed"),
        "panics": len(re.findall(r"Guru Meditation|assert failed|abort\(", text)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True)
    parser.add_argument("--seconds", type=int, default=40)
    parser.add_argument("--calibrate", action="store_true", help="Explicitly replace the neutral baseline; sit still with head/shoulders visible")
    args = parser.parse_args()
    if not 5 <= args.seconds <= 300:
        parser.error("--seconds must be between 5 and 300")
    import serial
    folder = ROOT / ".local/device-checks" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    folder.mkdir(parents=True)
    # Opening the UART must not intentionally reset the board or erase calibration.
    device = serial.Serial(port=None, baudrate=115200, timeout=0.1)
    device.dtr = False
    device.rts = False
    device.port = args.port
    with device:
        device.write(b"posecal\r\n" if args.calibrate else b"b status\r\n")
        start = time.monotonic()
        data = bytearray()
        while time.monotonic() - start < args.seconds:
            data.extend(device.read(max(1, device.in_waiting)))
    (folder / "serial-private.log").write_bytes(data)
    result = summarize(data.decode("utf-8", errors="replace"))
    (folder / "summary.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("Private capture saved locally; do not upload raw logs. Counts are observations, not end-to-end acceptance.")


if __name__ == "__main__":
    main()
