"""Validate originals and create a deterministic, duplicate-grouped YOLO split."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import shutil
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import yaml

NEU_CLASSES = ("crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches")


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_boxes(lines, names):
    boxes = []
    for line in lines:
        values = list(map(float, line.split()))
        if len(values) != 5 or not all(math.isfinite(v) for v in values):
            raise ValueError(f"Invalid YOLO annotation: {line}")
        cls, x, y, w, h = values
        if cls != int(cls) or not 0 <= cls < len(names) or w <= 0 or h <= 0:
            raise ValueError(f"Invalid class/size: {line}")
        if min(x-w/2, y-h/2) < -1e-5 or max(x+w/2, y+h/2) > 1+1e-5:
            raise ValueError(f"Box outside image: {line}")
        box = [int(cls), x, y, w, h]
        if box in boxes:
            raise ValueError("Duplicate bounding box")
        boxes.append(box)
    return boxes


def read_voc(path, image_size, names, convention):
    root = ET.parse(path).getroot()
    width, height = image_size
    if (int(root.findtext("size/width")), int(root.findtext("size/height"))) != image_size:
        raise ValueError(f"XML/image size mismatch: {path}")
    lines = []
    for obj in root.findall("object"):
        name = obj.findtext("name").strip()
        if name not in names:
            raise ValueError(f"Unknown class {name}")
        x1, y1, x2, y2 = [float(obj.findtext(f"bndbox/{k}")) for k in ("xmin", "ymin", "xmax", "ymax")]
        if convention == "voc-inclusive":
            if min(x1, y1) < 1:
                raise ValueError("VOC inclusive coordinates must start at 1; review convention")
            x1 -= 1
            y1 -= 1
        lines.append(f"{names.index(name)} {(x1+x2)/2/width} {(y1+y2)/2/height} {(x2-x1)/width} {(y2-y1)/height}")
    return validate_boxes(lines, names)


def prepare(raw, output, names, *, seed=42, val=0.15, test=0.15,
            annotation_format="yolo", convention="voc-inclusive", near_distance=2, source=None):
    raw, output = Path(raw).resolve(), Path(output).resolve()
    if output.exists() or output.is_relative_to(raw):
        raise ValueError("Output must be a new directory outside raw originals")
    if not 0 < val < 1 or not 0 < test < 1 or val+test >= 1 or not names or len(set(names)) != len(names):
        raise ValueError("Invalid split fractions or class names")
    suffix = ".txt" if annotation_format == "yolo" else ".xml"
    annotations = {}
    for path in sorted(raw.rglob(f"*{suffix}")):
        if path.stem in annotations:
            raise ValueError(f"Ambiguous annotation stem: {path.stem}")
        annotations[path.stem] = path
    records, seen_stems = [], set()
    used = set()
    for path in sorted(raw.rglob("*")):
        if path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
            continue
        if path.stem in seen_stems:
            raise ValueError(f"Ambiguous image stem: {path.stem}")
        seen_stems.add(path.stem)
        if path.stem not in annotations:
            raise ValueError(f"Missing annotation: {path}")
        ann = annotations[path.stem]
        used.add(ann)
        with Image.open(path) as original:
            original.load()
            image = original.convert("RGB")
            pixels = hashlib.sha256(str(image.size).encode()+image.tobytes()).hexdigest()
            small = np.asarray(image.convert("L").resize((9, 8)), dtype=np.int16)
            dhash = int.from_bytes(np.packbits(small[:, 1:] > small[:, :-1]).tobytes(), "big")
            boxes = (validate_boxes(ann.read_text().splitlines(), names) if annotation_format == "yolo"
                     else read_voc(ann, image.size, names, convention))
            size = image.size
        if not boxes:
            raise ValueError(f"Unexpected empty annotation: {ann}; explicitly review negative samples")
        records.append(dict(original=path.relative_to(raw).as_posix(), annotation=ann.relative_to(raw).as_posix(),
                            sha256=sha256(path), annotation_sha256=sha256(ann), pixels_sha256=pixels,
                            dhash=dhash, size=size, boxes=boxes))
        if len(records) % 500 == 0:
            print(f"Validated {len(records)} image/annotation pairs", flush=True)
    # Ignore documentation TXT, but never silently ignore orphan label files.
    orphans = [p for p in set(annotations.values())-used if p.parent.name.lower() in {"label", "labels", "annotations"}]
    if orphans:
        raise ValueError(f"Orphan annotations: {orphans[:3]}")
    counts = Counter(int(b[0]) for r in records for b in r["boxes"])
    if set(counts) != set(range(len(names))):
        raise ValueError(f"Expected every class, found {dict(counts)}")
    parent = list(range(len(records)))
    print(f"Grouping {len(records)} originals by pixels/dHash", flush=True)

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, left in enumerate(records):
        for j in range(i):
            right = records[j]
            if left["pixels_sha256"] == right["pixels_sha256"] or (left["dhash"] ^ right["dhash"]).bit_count() <= near_distance:
                parent[find(i)] = find(j)
    groups = defaultdict(list)
    for i, record in enumerate(records):
        groups[find(i)].append(record)
    strata = defaultdict(list)
    for group in groups.values():
        signature = tuple(sorted({b[0] for r in group for b in r["boxes"]}))
        strata[signature].append(group)
    rng = random.Random(seed)
    rare_strata = []
    for signature, pool in sorted(strata.items()):
        rng.shuffle(pool)
        if len(pool) < 3:
            # A rare multi-label combination cannot be split independently.
            # Keep it in training; require class coverage across all splits below.
            rare_strata.append(dict(classes=signature, groups=len(pool)))
            nval, ntest = 0, 0
        else:
            nval, ntest = max(1, round(len(pool)*val)), max(1, round(len(pool)*test))
        if nval+ntest >= len(pool):
            raise ValueError("Insufficient training groups")
        for index, group in enumerate(pool):
            split = "val" if index < nval else "test" if index < nval+ntest else "train"
            for record in group:
                record.update(split=split, group=group[0]["pixels_sha256"])
    for split in ("train", "val", "test"):
        if {b[0] for r in records if r["split"] == split for b in r["boxes"]} != set(range(len(names))):
            raise ValueError(f"Missing classes in {split}")
    output.mkdir(parents=True)
    for record in records:
        split = record["split"]
        original = raw / record["original"]
        relative = Path("images") / split / original.name
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, target)
        label = output / "labels" / split / f"{original.stem}.txt"
        label.parent.mkdir(parents=True, exist_ok=True)
        label.write_text("\n".join(" ".join(map(str, b)) for b in record["boxes"])+"\n", encoding="utf-8")
        record["prepared"] = relative.as_posix()
    manifest = dict(seed=seed, fractions=dict(val=val, test=test), names=list(names),
                    annotation_format=annotation_format, box_convention=convention,
                    near_duplicate_hamming=near_distance, source=source,
                    rare_strata_train_only=rare_strata,
                    counts=dict(Counter(r["split"] for r in records)),
                    objects_by_class={names[k]: v for k, v in counts.items()}, records=records)
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "data.yaml").write_text(yaml.safe_dump(dict(path=output.as_posix(), train="images/train",
        val="images/val", test="images/test", names=list(names)), sort_keys=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in manifest.items() if k != "records"}, indent=2))
    return manifest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--raw", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--classes", nargs="+", default=list(NEU_CLASSES))
    p.add_argument("--format", choices=["yolo", "voc"], default="yolo")
    p.add_argument("--box-convention", choices=["voc-inclusive", "zero-exclusive"], default="voc-inclusive")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--val", type=float, default=0.15)
    p.add_argument("--test", type=float, default=0.15)
    p.add_argument("--near-distance", type=int, default=2)
    p.add_argument("--source", type=Path, required=True, help="Download receipt or reviewed provenance JSON")
    a = p.parse_args()
    prepare(a.raw, a.output, a.classes, seed=a.seed, val=a.val, test=a.test, annotation_format=a.format,
            convention=a.box_convention, near_distance=a.near_distance,
            source=json.loads(a.source.read_text(encoding="utf-8")))
