"""Train YOLO11n in an isolated run; never replace the active model.

Run from the repository root with python -m training.train.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import subprocess
import time

import yaml

from training.prepare_public import sha256

ROOT = Path(__file__).resolve().parents[1]


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--data", type=Path, default=ROOT / "dataset/cr7/data.yaml")
    p.add_argument("--model", default="yolo11n.pt")
    p.add_argument("--epochs", type=int, default=80)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=4, help="Conservative 6 GB default; -1 enables AutoBatch")
    p.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    p.add_argument("--project", type=Path, default=ROOT / "outputs/public-training")
    p.add_argument("--name", default="cr7-yolo11n")
    p.add_argument("--resume", type=Path, help="Interrupted run weights/last.pt; restores original epoch target")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--workers", type=int, default=0)
    p.add_argument("--patience", type=int, default=20)
    p.add_argument("--fraction", type=float, default=1.0, help="Training fraction for smoke; validation stays complete")
    a = p.parse_args(argv)
    if a.epochs < 1 or a.imgsz < 32 or a.imgsz % 32 or a.batch == 0 or a.batch < -1 or not 0 < a.fraction <= 1:
        p.error("Positive epochs, imgsz multiple of 32, batch -1 or positive, fraction in (0,1] required")
    if a.workers < 0 or a.patience < 0 or Path(a.name).name != a.name or a.name in {".", ".."}:
        p.error("Invalid workers, patience or run name")
    return a


def validate_dataset(data):
    data = Path(data).resolve()
    config = yaml.safe_load(data.read_text(encoding="utf-8"))
    if "download" in config:
        raise ValueError("Automatic dataset downloads forbidden; prepare a reviewed local release")
    manifest_path = data.parent / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if config["names"] != manifest["names"] or Path(config["path"]).resolve() != data.parent:
        raise ValueError("Data YAML does not match manifest")
    if not manifest.get("source"):
        raise ValueError("Missing provenance receipt")
    groups = {}
    for record in manifest["records"]:
        split = record["split"]
        if groups.setdefault(record["group"], split) != split:
            raise ValueError("Duplicate group crosses splits")

    def verify_record(record):
        split = record["split"]
        relative = Path(record["prepared"])
        image = (data.parent / relative).resolve()
        if not image.is_relative_to(data.parent) or relative.parts[:2] != ("images", split):
            raise ValueError("Invalid manifest path")
        if sha256(image) != record["sha256"]:
            raise ValueError(f"Image changed since preparation: {image}")
        label = data.parent / "labels" / split / (image.stem + ".txt")
        expected = "\n".join(" ".join(map(str, b)) for b in record["boxes"])+"\n"
        if label.read_text(encoding="utf-8") != expected:
            raise ValueError(f"Labels changed since preparation: {label}")
    # Hash independent local files concurrently: Windows per-file latency can
    # dominate this check. Every result is consumed, so any failure aborts.
    with ThreadPoolExecutor(max_workers=8) as pool:
        for index, _ in enumerate(pool.map(verify_record, manifest["records"]), 1):
            if index % 1000 == 0:
                print(f"Integrity verified: {index} prepared images/labels", flush=True)
    for split in ("train", "val", "test"):
        expected = {r["prepared"] for r in manifest["records"] if r["split"] == split}
        actual = {p.relative_to(data.parent).as_posix() for p in (data.parent / "images" / split).iterdir() if p.is_file()}
        if not expected or actual != expected or config[split] != f"images/{split}":
            raise ValueError(f"Unexpected files or missing split: {split}")
    return manifest_path


def select_device(requested, torch):
    if requested == "cpu":
        return "cpu"
    if torch.cuda.is_available():
        return 0
    if requested == "cuda":
        raise RuntimeError("CUDA requested but unavailable")
    print("CUDA unavailable: explicitly reporting CPU fallback")
    return "cpu"


def main(argv=None):
    args = parse_args(argv)
    manifest_path = validate_dataset(args.data)
    import torch
    import ultralytics
    from ultralytics import YOLO
    device = select_device(args.device, torch)
    if args.resume:
        if not args.resume.is_file():
            raise FileNotFoundError(args.resume)
        run = args.resume.resolve().parent.parent
        prior = json.loads((run / "experiment.json").read_text())
        if prior["manifest_sha256"] != sha256(manifest_path):
            raise ValueError("Cannot resume with a different dataset manifest")
        if Path(prior["data"]).resolve() != args.data.resolve():
            raise ValueError("Resume requires the original data path stored in the checkpoint")
        model = YOLO(str(args.resume))
    else:
        run = args.project.resolve() / args.name
        if run.exists():
            raise FileExistsError(f"Run already exists: {run}; choose another name or --resume")
        if args.model == "yolo11n.pt":
            from training.download_weights import download
            download()
        model = YOLO(args.model)
        run.mkdir(parents=True)
    info = dict(arguments={k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()},
                manifest_sha256=sha256(manifest_path), data=str(args.data.resolve()),
                torch=torch.__version__, ultralytics=ultralytics.__version__, cuda_runtime=torch.version.cuda,
                device=device, gpu=torch.cuda.get_device_name(device) if device != "cpu" else None,
                vram_mb=round(torch.cuda.get_device_properties(device).total_memory/1024**2) if device != "cpu" else None,
                initial_weights_sha256=sha256(args.resume or Path(args.model)) if Path(args.resume or args.model).is_file() else None,
                git_commit=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                training_source_sha256={p.name: sha256(p) for p in sorted((ROOT / "training").glob("*.py"))},
                git_dirty=bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)))
    filename = "resume-experiment.json" if args.resume else "experiment.json"
    (run / filename).write_text(json.dumps(info, indent=2), encoding="utf-8")
    if device != "cpu":
        torch.cuda.reset_peak_memory_stats(device)
    start = time.perf_counter()
    if args.resume:
        model.train(resume=True, device=device, workers=args.workers)
    else:
        model.train(data=str(args.data.resolve()), epochs=args.epochs, imgsz=args.imgsz, batch=args.batch,
                    device=device, project=str(run.parent), name=run.name, exist_ok=True,
                    seed=args.seed, deterministic=True, workers=args.workers, patience=args.patience,
                    fraction=args.fraction, cache=False, amp=device != "cpu", plots=True, save=True,
                    save_period=1)
    if device != "cpu":
        torch.cuda.synchronize(device)
    info.update(elapsed_seconds=time.perf_counter()-start,
                peak_allocated_mb=round(torch.cuda.max_memory_allocated(device)/1024**2) if device != "cpu" else None,
                peak_reserved_mb=round(torch.cuda.max_memory_reserved(device)/1024**2) if device != "cpu" else None,
                best_weights=str(Path(model.trainer.save_dir) / "weights/best.pt"))
    (run / filename).write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(json.dumps(info, indent=2))


if __name__ == "__main__":
    main()
