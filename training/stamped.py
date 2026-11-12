"""Experimental grouped photo split and YOLO11n-cls training. Run as a module."""
import argparse
import csv
import hashlib
import json
import random
import time
from collections import Counter, defaultdict
from pathlib import Path

import cv2
import numpy as np

from backend.stamped_input import NAMES, square_frame

DATA = Path("dataset/stamped-v1")
RUNS = Path("outputs/stamped-v1")


def csv_rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def assign_splits(records, pairs):
    parent = {int(r["id"]):int(r["id"]) for r in records}

    def root(i):
        while i != parent[i]:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for pair in pairs:
        parent[root(int(pair["id1"]))] = root(int(pair["id2"]))
    groups = defaultdict(list)
    totals = Counter(r["category"] for r in records)
    ranks = Counter()
    for row in records:
        label = row["category"]
        ranks[label] += 1
        row["sequence_fraction"] = ranks[label] / totals[label]
        groups[root(int(row["id"]))].append(row)
    rng = random.Random(42)
    # Prefer later positions within each WhatsApp sequence for holdout, then val.
    ordered = sorted(groups, key=lambda g:(np.mean([r["sequence_fraction"] for r in groups[g]]),rng.random()), reverse=True)
    assignment = {}
    for split in ("holdout", "val"):
        left = Counter({c:round(n*.15) for c,n in totals.items()})
        for g in ordered:
            counts = Counter(r["category"] for r in groups[g])
            if g not in assignment and all(n <= left[c] for c,n in counts.items()):
                assignment[g] = split
                left.subtract(counts)
    for row in records:
        group = root(int(row["id"]))
        row.update(group=group, split=assignment.get(group, "train"))


def prepare(source, audit, dest):
    if dest.resolve().is_relative_to(source.resolve()):
        raise ValueError("El destino debe quedar fuera de los originales")
    records = csv_rows(audit / "inventory.csv")
    totals = Counter(row["category"] for row in records)
    if totals != {"ok": 144, "falta_embutido_material": 200, "ruptura_deformacion": 200}:
        raise ValueError(f"Inventario inesperado: {totals}")
    assign_splits(records, csv_rows(audit / "similar_pairs.csv"))
    if dest.exists():
        raise FileExistsError(dest)
    dest.mkdir(parents=True)
    for row in records:
        split = row["split"]
        raw = (source/row["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError(f"Original changed since audit: {row['path']}")
        sub = Path("reserved") if split=="holdout" else Path("fit")/split
        output = sub/row["category"]/(row["id"]+".png")
        (dest/output).parent.mkdir(parents=True,exist_ok=True)
        frame = cv2.imdecode(np.frombuffer(raw,np.uint8),cv2.IMREAD_COLOR)
        if not cv2.imwrite(str(dest/output),square_frame(frame)):
            raise OSError(output)
        row["prepared"] = output.as_posix()
    (dest/"manifest.json").write_text(json.dumps(records,indent=2,ensure_ascii=False),encoding="utf-8")
    print(Counter((r["split"],r["category"]) for r in records),flush=True)


def train(data, runs, epochs, name, batch):
    import torch
    import ultralytics
    from ultralytics import YOLO
    if not (data / "manifest.json").is_file():
        raise ValueError("La preparación debe completar el manifiesto antes de entrenar")
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA 0 required")
    directory = runs.resolve()/name
    directory.mkdir(parents=True,exist_ok=False)
    model = YOLO("yolo11n-cls.pt")
    start = time.monotonic()
    model.train(data=str((data/"fit").resolve()),project=str(directory.parent),name=name,
                exist_ok=True,imgsz=224,epochs=epochs,batch=batch,patience=10,device=0,
                seed=42,deterministic=True,workers=0,amp=True,plots=True,
                scale=0.0,fliplr=0.0,flipud=0.0,auto_augment=None,erasing=0.0,
                hsv_h=0.0,hsv_s=0.04,hsv_v=0.10,mixup=0.0,cutmix=0.0)
    checkpoint = directory/"weights/best.pt"
    restored = YOLO(str(checkpoint))
    assert restored.task == "classify" and set(restored.names.values()) == set(NAMES)
    probe = next((data/"fit/val").rglob("*.png"))
    scores = restored.predict(str(probe),device=0,verbose=False)[0].probs.data
    assert scores.is_cuda and scores.numel()==3 and torch.isfinite(scores).all()
    info = dict(seconds=time.monotonic()-start,gpu=torch.cuda.get_device_name(0),
                peak_reserved_MiB=torch.cuda.max_memory_reserved(0)//2**20,torch=torch.__version__,
                ultralytics=ultralytics.__version__,manifest_sha256=hashlib.sha256((data/"manifest.json").read_bytes()).hexdigest(),
                initial_sha256=hashlib.sha256(Path("yolo11n-cls.pt").read_bytes()).hexdigest(),best_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest())
    (directory/"run.json").write_text(json.dumps(info,indent=2))


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action",choices=["prepare","train"])
    parser.add_argument("--source",type=Path,default=Path(r"C:\Users\picud\Downloads\Data set"))
    parser.add_argument("--audit",type=Path,default=Path("outputs/stamped-audit-20261112"))
    parser.add_argument("--data",type=Path,default=DATA)
    parser.add_argument("--runs",type=Path,default=RUNS)
    parser.add_argument("--epochs",type=int,default=50)
    parser.add_argument("--name",default="full")
    parser.add_argument("--batch",type=int,default=16)
    a=parser.parse_args()
    if a.action=="prepare": prepare(a.source,a.audit,a.data)
    else: train(a.data,a.runs,a.epochs,a.name,a.batch)
