"""Pinned official YOLO11n initialization weights (Ultralytics AGPL-3.0)."""
import hashlib
from pathlib import Path
from urllib.request import urlopen

URL = "https://github.com/ultralytics/assets/releases/download/v8.4.0/yolo11n.pt"
SHA256 = "0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1"


def download(destination=Path("yolo11n.pt")):
    destination = Path(destination)
    if destination.exists():
        payload = destination.read_bytes()
    else:
        with urlopen(URL, timeout=120) as response:
            payload = response.read()
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("Official initialization weights checksum mismatch; no file overwritten")
    if not destination.exists():
        with destination.open("xb") as out:
            out.write(payload)
    return destination


if __name__ == "__main__":
    print(download().resolve(), SHA256)
