"""Evaluate the frozen stamped classifier once on the grouped photographic holdout."""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from ultralytics import YOLO

from backend.stamped_input import NAMES, REVIEW_THRESHOLD
from training.stamped import DATA, RUNS


def evaluate(data, run, destination):
    manifest = data / "manifest.json"
    weights = run / "weights/best.pt"
    metadata = json.loads((run / "run.json").read_text())
    for path, key in [(manifest, "manifest_sha256"), (weights, "best_sha256")]:
        if hashlib.sha256(path.read_bytes()).hexdigest() != metadata[key]:
            raise ValueError(f"Hash incorrecto: {path}")
    records = json.loads(manifest.read_text(encoding="utf-8"))
    held = [r for r in records if r["split"] == "holdout"]
    fitted_groups = {r["group"] for r in records if r["split"] != "holdout"}
    if any(r["group"] in fitted_groups for r in held) or not held:
        raise ValueError("Reserva inválida")
    model = YOLO(str(weights))
    if set(model.names.values()) != set(NAMES):
        raise ValueError("Clases inesperadas")
    destination.mkdir(parents=True, exist_ok=False)
    matrix = np.zeros((3, 3), dtype=int)
    predictions = []
    gallery = []
    for record in held:
        path = data / record["prepared"]
        result = model.predict(str(path), imgsz=224, device=0, verbose=False)[0]
        scores = dict(zip(result.names.values(), result.probs.data.tolist()))
        predicted = max(scores, key=scores.get)
        actual = record["category"]
        matrix[NAMES.index(actual), NAMES.index(predicted)] += 1
        prediction = dict(id=record["id"], original=record["path"], actual=actual,
                          predicted=predicted, revisar=scores[predicted] < REVIEW_THRESHOLD, **scores)
        predictions.append(prediction)
        if actual != predicted:
            gallery.append(f'<figure><img src="{path.resolve().as_uri()}"><figcaption>'
                           f'{html.escape(record["path"])} · {actual} → {predicted} '
                           f'({scores[predicted]:.1%})</figcaption></figure>')
    with (destination / "predictions.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=predictions[0].keys())
        writer.writeheader()
        writer.writerows(predictions)
    metrics = {}
    for i, name in enumerate(NAMES):
        tp = int(matrix[i, i])
        support, predicted = int(matrix[i].sum()), int(matrix[:, i].sum())
        metrics[name] = dict(support=support, precision=tp/max(1, predicted), recall=tp/max(1, support),
                             f1=2*tp/max(1, support+predicted), fp=predicted-tp, fn=support-tp)
    report = dict(scope="Fotografías reservadas de piezas conocidas; posible fuga de identidad física.",
                  best_sha256=metadata["best_sha256"], manifest_sha256=metadata["manifest_sha256"],
                  accuracy=float(matrix.trace()/matrix.sum()), classes=NAMES, per_class=metrics,
                  confusion=matrix.tolist(), defect_as_ok=[p for p in predictions if p["actual"] != "ok" and p["predicted"] == "ok"],
                  provisional_threshold=REVIEW_THRESHOLD, revisar=sum(p["revisar"] for p in predictions))
    (destination / "metrics.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (destination / "errores.html").write_text('<!doctype html><meta charset="utf-8"><title>Errores</title>'
        '<h1>Errores en las fotografías reservadas</h1>' + ("".join(gallery) or "<p>Ninguna clasificación incorrecta.</p>"), encoding="utf-8")
    fig, ax = plt.subplots(figsize=(7, 5), layout="constrained")
    ax.imshow(matrix, cmap="Blues", vmin=0)
    labels = ["Falta de embutido\ny material", "OK", "Ruptura y\ndeformación"]
    ax.set(xticks=range(3), yticks=range(3), xticklabels=labels, yticklabels=labels,
           xlabel="Categoría predicha", ylabel="Categoría registrada", title=f"Reserva exploratoria · {len(held)} fotografías")
    for (i, j), value in np.ndenumerate(matrix):
        ax.text(j, i, str(value), ha="center", va="center", color="white" if value > matrix.max()/2 else "black")
    fig.savefig(destination / "confusion.png", dpi=160)
    plt.close(fig)
    print(json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=DATA)
    parser.add_argument("--run", type=Path, default=RUNS / "full")
    parser.add_argument("--output", type=Path, default=RUNS / "evaluation")
    args = parser.parse_args()
    evaluate(args.data, args.run, args.output)
