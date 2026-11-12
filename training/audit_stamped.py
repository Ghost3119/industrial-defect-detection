"""Read-only inventory, duplicate screening and review sheets for stamped parts."""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageOps

CLASSES = {"Ok": "ok", "Pieza falta de embutido y materia": "falta_embutido_material",
           "ruptura de material y deformación": "ruptura_deformacion"}


def fingerprint(gray):
    low = cv2.dct(cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype("float32"))[:8, :8].ravel()[1:]
    return int.from_bytes(np.packbits(low > np.median(low)).tobytes(), "big")


def table(path, rows, fields):
    with path.open("w", newline="", encoding="utf-8-sig") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def audit(root, out):
    if out.resolve().is_relative_to(root.resolve()):
        raise ValueError("El destino debe quedar fuera de los originales")
    out.mkdir(parents=True, exist_ok=False)
    records, errors, pairs, views = [], [], [], []
    groups = defaultdict(list)
    counts = {}
    for folder, category in CLASSES.items():
        files = sorted(p for p in (root / folder).rglob("*") if p.is_file())
        counts[category] = len(files)
        for path in files:
            relative = path.relative_to(root).as_posix()
            try:
                with Image.open(path) as image:
                    image.verify()
                with Image.open(path) as image:
                    fmt = image.format
                    exif = image.getexif()
                    rgb = ImageOps.exif_transpose(image).convert("RGB")
                    rgb.load()
                width, height = rgb.size
                thumb = np.asarray(rgb.resize((64, 64), Image.Resampling.LANCZOS).convert("L"))
                rotations = [np.ascontiguousarray(np.rot90(thumb, k)) for k in range(4)]
                row = dict(id=len(records)+1, category=category, path=relative, format=fmt,
                           width=width, height=height, brightness=round(float(thumb.mean()), 1),
                           contrast=round(float(thumb.std()), 1), exif_tags=len(exif),
                           sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                           pixels_sha256=hashlib.sha256(str(rgb.size).encode()+rgb.tobytes()).hexdigest())
                records.append(row)
                groups[category].append(row)
                views.append(([fingerprint(t) for t in rotations], rotations))
            except (OSError, ValueError, SyntaxError) as exc:
                errors.append(dict(path=relative, error=str(exc)))
    for i, (hashes, thumbs) in enumerate(views):
        for j in range(i):
            other_hashes, other_thumbs = views[j]
            best = min(range(4), key=lambda k: (hashes[k] ^ other_hashes[0]).bit_count())
            distance = (hashes[best] ^ other_hashes[0]).bit_count()
            exact = records[i]["pixels_sha256"] == records[j]["pixels_sha256"]
            if distance <= 10 or exact:
                mad = float(cv2.absdiff(thumbs[best], other_thumbs[0]).mean())
                pairs.append(dict(id1=j+1, id2=i+1, cross_class=records[i]["category"] != records[j]["category"],
                                  exact_pixels=exact, phash_distance=distance, rotation=best*90, gray_mad=round(mad, 2)))
    table(out/"inventory.csv", records, list(records[0]))
    table(out/"similar_pairs.csv", sorted(pairs, key=lambda p:(p["phash_distance"],p["gray_mad"])),
          ["id1","id2","cross_class","exact_pixels","phash_distance","rotation","gray_mad"])
    for category, rows in groups.items():
        sample = [rows[k] for k in np.linspace(0, len(rows)-1, min(20,len(rows)), dtype=int)]
        for suffix, subset, size, cols in [("sample",sample,195,5),("all",rows,105,10)]:
            sheet = Image.new("RGB",(size*cols,(size+20)*((len(subset)+cols-1)//cols)), "white")
            draw = ImageDraw.Draw(sheet)
            for n, r in enumerate(subset):
                x, y = n%cols*size,n//cols*(size+20)
                with Image.open(root/r["path"]) as im:
                    tile = ImageOps.contain(ImageOps.exif_transpose(im),(size,size))
                    sheet.paste(tile,(x+(size-tile.width)//2,y))
                draw.text((x+2,y+size), str(r["id"]), fill="black")
            sheet.save(out/f"{category}_{suffix}.jpg",quality=88)
    summary = dict(files=counts, decoded={c:len(v) for c,v in groups.items()}, errors=errors,
                   dimensions=dict(Counter(f"{r['width']}x{r['height']}" for r in records)),
                   formats=dict(Counter(r["format"] for r in records)),
                   extra_byte_copies=len(records)-len({r["sha256"] for r in records}),
                   extra_pixel_copies=len(records)-len({r["pixels_sha256"] for r in records}),
                   candidate_pairs=len(pairs), cross_class_pairs=sum(p["cross_class"] for p in pairs),
                   with_exif=sum(bool(r["exif_tags"]) for r in records))
    (out/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps(summary,ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root",type=Path)
    parser.add_argument("out",type=Path)
    args=parser.parse_args()
    audit(args.root,args.out)
