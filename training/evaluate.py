"""Evaluate a frozen checkpoint on the reserved test split, with TP/FP/FN evidence."""
import argparse
from collections import Counter
import json
from pathlib import Path

import cv2
from training.prepare_public import sha256
from training.train import select_device, validate_dataset


def match_boxes(predictions, truth, threshold=0.5):
    """Confidence-ordered, class-aware one-to-one IoU matching for evidence only.

    Prediction rows: class, confidence, x1, y1, x2, y2. Truth rows: class, x1, y1, x2, y2.
    Ultralytics independently computes the official mAP using its own matcher.
    """
    matched, tp, fp = set(), [], []
    for index in sorted(range(len(predictions)), key=lambda i: -predictions[i][1]):
        cls, _, *box = predictions[index]
        candidates = []
        for j, (target_cls, *target) in enumerate(truth):
            if j in matched or cls != target_cls:
                continue
            x1, y1 = max(box[0], target[0]), max(box[1], target[1])
            x2, y2 = min(box[2], target[2]), min(box[3], target[3])
            intersection = max(0, x2-x1)*max(0, y2-y1)
            area = (box[2]-box[0])*(box[3]-box[1])+(target[2]-target[0])*(target[3]-target[1])
            iou = intersection / max(area-intersection, 1e-12)
            if iou >= threshold:
                candidates.append((iou, j))
        if candidates:
            matched.add(max(candidates)[1])
            tp.append(index)
        else:
            fp.append(index)
    return tp, fp, [i for i in range(len(truth)) if i not in matched]


def evaluate(data, weights, output, *, device="auto", imgsz=640, batch=4, conf=0.25, match_iou=0.5, examples=12):
    if not 0 <= conf <= 1 or not 0 < match_iou <= 1 or examples < 0 or batch < 1:
        raise ValueError("Invalid evaluation settings")
    data, weights, output = Path(data).resolve(), Path(weights).resolve(), Path(output).resolve()
    manifest_path = validate_dataset(data)
    manifest = json.loads(manifest_path.read_text())
    if output.exists():
        raise FileExistsError(output)
    import torch
    import ultralytics
    from ultralytics import YOLO
    selected = select_device(device, torch)
    model = YOLO(str(weights))
    if model.task != "detect" or list(model.names.values()) != manifest["names"]:
        raise ValueError("Checkpoint classes/order do not match dataset")
    experiment = weights.parent.parent / "experiment.json"
    if not experiment.is_file() or json.loads(experiment.read_text())["manifest_sha256"] != sha256(manifest_path):
        raise ValueError("Missing training provenance for this frozen test split; comparison would be invalid")
    output.mkdir(parents=True)
    metrics = model.val(data=str(data), split="test", imgsz=imgsz, batch=batch, device=selected,
                        conf=0.001, iou=0.7, plots=True, workers=0,
                        project=str(output), name="metrics", exist_ok=True)
    counts, saved, per_image = Counter(), Counter(), []
    for record in manifest["records"]:
        if record["split"] != "test":
            continue
        image_path = data.parent / record["prepared"]
        image = cv2.imread(str(image_path))
        height, width = image.shape[:2]
        truth = []
        for cls, x, y, w, h in record["boxes"]:
            truth.append([cls, (x-w/2)*width, (y-h/2)*height, (x+w/2)*width, (y+h/2)*height])
        result = model.predict(str(image_path), imgsz=imgsz, device=selected, conf=conf, iou=0.7, verbose=False)[0]
        predictions = [[int(c), float(s), *b] for c, s, b in zip(result.boxes.cls.cpu().tolist(),
                       result.boxes.conf.cpu().tolist(), result.boxes.xyxy.cpu().tolist())]
        tp, fp, fn = match_boxes(predictions, truth, match_iou)
        entry = dict(original=record["original"], sha256=record["sha256"], predictions=predictions,
                     truth=truth, tp=tp, fp=fp, fn=fn)
        per_image.append(entry)
        for category, indices in (("TP", tp), ("FP", fp), ("FN", fn)):
            counts[category] += len(indices)
            if not indices or saved[category] >= examples:
                continue
            canvas = image.copy()
            for row in truth:
                cls, *box = row
                x1, y1, x2, y2 = map(round, box)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 255, 0), 1)
                cv2.putText(canvas, f"GT {model.names[int(cls)]}", (x1, max(10, y1)), 0, .35, (0, 255, 0), 1)
            for cls, score, *box in predictions:
                x1, y1, x2, y2 = map(round, box)
                cv2.rectangle(canvas, (x1, y1), (x2, y2), (0, 0, 255), 1)
                cv2.putText(canvas, f"{model.names[cls]} {score:.2f}", (x1, max(10, y2)), 0, .35, (0, 0, 255), 1)
            folder = output / "examples" / category
            folder.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(folder / image_path.name), canvas)
            (folder / f"{image_path.stem}.json").write_text(json.dumps(entry, indent=2))
            saved[category] += 1
    report = dict(split="test", weights_sha256=sha256(weights), manifest_sha256=sha256(manifest_path),
                  precision=float(metrics.box.mp), recall=float(metrics.box.mr),
                  mAP50=float(metrics.box.map50), mAP50_95=float(metrics.box.map),
                  metric_conf=0.001, nms_iou=0.7, precision_recall_policy="Ultralytics max-F1 confidence",
                  evidence_conf=conf, evidence_match_iou=match_iou, evidence_counts=dict(counts),
                  saved_examples=dict(saved), imgsz=imgsz, batch=batch, device=selected,
                  ultralytics=ultralytics.__version__, torch=torch.__version__, names=manifest["names"],
                  limitations="Short-run public-dataset test only; no stamped-parts validation or baseline comparison")
    (output / "report.json").write_text(json.dumps(report, indent=2))
    (output / "per_image.json").write_text(json.dumps(per_image))
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=Path("dataset/cr7/data.yaml"))
    p.add_argument("--weights", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--conf", type=float, default=0.25)
    p.add_argument("--match-iou", type=float, default=0.5)
    p.add_argument("--examples", type=int, default=12)
    a = p.parse_args()
    evaluate(a.data, a.weights, a.output, device=a.device, imgsz=a.imgsz, batch=a.batch,
             conf=a.conf, match_iou=a.match_iou, examples=a.examples)
