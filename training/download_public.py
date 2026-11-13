"""Download the authors' pinned CR7-DET V1 release (CC BY 4.0)."""
import argparse
import hashlib
import json
from pathlib import Path
from urllib.request import urlopen
from zipfile import ZipFile

RECORD = "https://zenodo.org/api/records/14263276"
FILE = "CR7-DET-main.zip"
MD5 = "adb0f1fd14a30cac7d1b2a16961cc8be"
SHA256 = "34500cc56ae4eadf7696b6197b504ed18c25349bc3c0564490ab63d95c3c3201"


def download(destination: Path):
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite {destination}")
    with urlopen(RECORD, timeout=60) as response:
        metadata = json.load(response)
    if metadata["metadata"]["license"]["id"] != "cc-by-4.0":
        raise ValueError("Release license changed; review before downloading")
    entry = next(f for f in metadata["files"] if f["key"] == FILE)
    if entry["checksum"] != f"md5:{MD5}":
        raise ValueError("Release checksum changed")
    destination.parent.mkdir(parents=True, exist_ok=True)
    archive = destination.parent / FILE
    if not archive.exists():
        partial = archive.with_suffix(".zip.partial")
        with urlopen(entry["links"]["self"], timeout=120) as response, partial.open("xb") as out:
            while chunk := response.read(1024 * 1024):
                out.write(chunk)
        if hashlib.md5(partial.read_bytes()).hexdigest() != MD5:
            raise ValueError(f"Checksum mismatch; inspect {partial}")
        partial.rename(archive)
    payload = archive.read_bytes()
    if hashlib.md5(payload).hexdigest() != MD5:
        raise ValueError("Archive checksum mismatch")
    if hashlib.sha256(payload).hexdigest() != SHA256:
        raise ValueError("Archive SHA-256 mismatch")
    with ZipFile(archive) as zipped:
        root = destination.resolve()
        for info in zipped.infolist():
            if not (root / info.filename).resolve().is_relative_to(root):
                raise ValueError("Unsafe ZIP path")
        zipped.extractall(destination)
    receipt = {"record": RECORD, "doi": metadata["metadata"]["doi"],
               "license": "CC-BY-4.0", "creators": metadata["metadata"]["creators"],
               "archive_sha256": hashlib.sha256(payload).hexdigest(), "metadata": metadata}
    (destination / "source.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in receipt.items() if k != "metadata"}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dataset/cr7-raw"))
    download(parser.parse_args().output)
