import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image
import pytest

from training.prepare_public import prepare, read_voc, validate_boxes, NEU_CLASSES
from training.train import parse_args, select_device, validate_dataset
from training.evaluate import match_boxes


def make_raw(root):
    root.mkdir()
    rng = np.random.default_rng(12)
    for cls in range(2):
        for index in range(8):
            name = f"{cls}_{index}"
            Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(root / f"{name}.png")
            (root / f"{name}.txt").write_text(f"{cls} 0.5 0.5 0.5 0.5\n")
    # Pixel-identical duplicate with different encoding/file identity.
    Image.open(root / "0_0.png").save(root / "duplicate.bmp")
    (root / "duplicate.txt").write_text("0 0.5 0.5 0.5 0.5\n")
    return root


def test_reproducible_grouped_split_and_integrity(tmp_path):
    raw = make_raw(tmp_path / "raw")
    first = prepare(raw, tmp_path / "a", ["a", "b"], source={"license": "fixture"})
    second = prepare(raw, tmp_path / "b", ["a", "b"], source={"license": "fixture"})
    assert first == second
    duplicates = [r for r in first["records"] if Path(r["original"]).stem in {"0_0", "duplicate"}]
    assert len({r["split"] for r in duplicates}) == 1
    validate_dataset(tmp_path / "a/data.yaml")
    with pytest.raises(ValueError, match="new directory"):
        prepare(raw, tmp_path / "a", ["a", "b"])
    image = tmp_path / "a" / first["records"][0]["prepared"]
    image.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="Image changed"):
        validate_dataset(tmp_path / "a/data.yaml")


@pytest.mark.parametrize("line", ["0 nan .5 .1 .1", "2 .5 .5 .1 .1", "0 .9 .5 .5 .1", "0 .5 .5 0 .1", "0.5 .5 .5 .1 .1"])
def test_bad_annotations_rejected(line):
    with pytest.raises(ValueError):
        validate_boxes([line], ["a", "b"])


def test_missing_annotations_and_classes_rejected(tmp_path):
    raw = make_raw(tmp_path / "raw")
    (raw / "0_0.txt").unlink()
    with pytest.raises(ValueError, match="Missing annotation"):
        prepare(raw, tmp_path / "a", ["a", "b"])
    (raw / "0_0.txt").write_text("0 .5 .5 .5 .5")
    with pytest.raises(ValueError, match="every class"):
        prepare(raw, tmp_path / "a", ["a", "b", "c"])


def test_voc_six_classes_and_convention(tmp_path):
    xml = tmp_path / "boxes.xml"
    objects = "".join(f"<object><name>{name}</name><bndbox><xmin>1</xmin><ymin>1</ymin><xmax>20</xmax><ymax>10</ymax></bndbox></object>" for name in NEU_CLASSES)
    xml.write_text(f"<annotation><size><width>20</width><height>10</height></size>{objects}</annotation>")
    boxes = read_voc(xml, (20, 10), NEU_CLASSES, "voc-inclusive")
    assert [b[0] for b in boxes] == list(range(6))
    assert boxes[0][1:] == [.5, .5, 1, 1]
    with pytest.raises(ValueError, match="size mismatch"):
        read_voc(xml, (40, 10), NEU_CLASSES, "voc-inclusive")


def test_training_defaults_and_device_selection():
    args = parse_args([])
    assert (args.model, args.imgsz, args.batch, args.device) == ("yolo11n.pt", 640, 4, "auto")
    assert args.project.name == "public-training"
    fake = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: True))
    assert select_device("auto", fake) == 0
    assert select_device("cpu", fake) == "cpu"
    fake.cuda.is_available = lambda: False
    with pytest.raises(RuntimeError, match="unavailable"):
        select_device("cuda", fake)
    assert select_device("auto", fake) == "cpu"


@pytest.mark.parametrize("argv", [["--epochs", "0"], ["--batch", "0"], ["--imgsz", "639"], ["--fraction", "2"], ["--name", "../escape"]])
def test_training_invalid_configuration(argv):
    with pytest.raises(SystemExit):
        parse_args(argv)


def test_evidence_matching_is_one_to_one_class_aware():
    predictions = [[0, .9, 0, 0, 10, 10], [0, .8, 0, 0, 10, 10], [1, .7, 20, 20, 30, 30]]
    truth = [[0, 0, 0, 10, 10], [0, 20, 20, 30, 30]]
    assert match_boxes(predictions, truth) == ([0], [1, 2], [1])


def test_detector_accepts_explicit_alternate_profile(tmp_path, monkeypatch):
    import sys
    from unittest.mock import Mock
    import detector
    from backend.config import DATASET_PROFILES
    weights = tmp_path / "experimental.pt"
    weights.write_bytes(b"fixture")
    names = DATASET_PROFILES["cr7-det"]
    monkeypatch.setattr(detector, "DEFECT_CLASSES", names)
    model = SimpleNamespace(task="detect", names=dict(enumerate(names)))
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Mock(return_value=model)))
    assert detector.DefectDetector(weights).class_names == model.names


def test_training_isolated_and_resume_checks_provenance(tmp_path, monkeypatch):
    import sys
    from unittest.mock import Mock
    from training.train import main
    raw = make_raw(tmp_path / "raw")
    prepare(raw, tmp_path / "prepared", ["a", "b"], source={"license": "fixture"})
    weights = tmp_path / "active.pt"
    weights.write_bytes(b"preserve active weights")
    run = tmp_path / "runs" / "experiment"
    fake = SimpleNamespace(train=Mock(), trainer=SimpleNamespace(save_dir=run))
    monkeypatch.setitem(sys.modules, "ultralytics", SimpleNamespace(YOLO=Mock(return_value=fake), __version__="fixture"))
    argv = ["--data", str(tmp_path / "prepared/data.yaml"), "--device", "cpu",
            "--model", str(weights), "--project", str(run.parent), "--name", run.name, "--epochs", "2"]
    main(argv)
    assert weights.read_bytes() == b"preserve active weights"
    kwargs = fake.train.call_args.kwargs
    assert kwargs["epochs"] == 2 and kwargs["imgsz"] == 640 and kwargs["batch"] == 4
    assert kwargs["project"] == str(run.parent)
    assert "test" not in kwargs
    assert json.loads((run / "experiment.json").read_text())["device"] == "cpu"
    with pytest.raises(FileExistsError):
        main(argv)
    (run / "weights").mkdir()
    last = run / "weights/last.pt"
    last.write_bytes(b"checkpoint")
    main(argv + ["--resume", str(last)])
    assert fake.train.call_args.kwargs == dict(resume=True, device="cpu", workers=0)
    prior = json.loads((run / "experiment.json").read_text())
    prior["manifest_sha256"] = "different"
    (run / "experiment.json").write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="different dataset"):
        main(argv + ["--resume", str(last)])


def test_downloaders_fail_closed_on_license_and_hash(tmp_path, monkeypatch):
    import io
    from training import download_public, download_weights
    metadata = {"metadata": {"license": {"id": "unknown"}}}
    monkeypatch.setattr(download_public, "urlopen", lambda *a, **kw: io.BytesIO(json.dumps(metadata).encode()))
    with pytest.raises(ValueError, match="license changed"):
        download_public.download(tmp_path / "source")
    assert not (tmp_path / "source").exists()
    weights = tmp_path / "weights.pt"
    weights.write_bytes(b"do not replace")
    with pytest.raises(ValueError, match="checksum mismatch"):
        download_weights.download(weights)
    assert weights.read_bytes() == b"do not replace"


def test_rare_multilabel_strata_stay_in_train(tmp_path):
    raw = make_raw(tmp_path / "raw")
    rng = np.random.default_rng(71)
    Image.fromarray(rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)).save(raw / "rare.png")
    (raw / "rare.txt").write_text("0 .3 .3 .2 .2\n1 .7 .7 .2 .2\n")
    manifest = prepare(raw, tmp_path / "prepared", ["a", "b"], source={"license": "fixture"})
    rare = next(r for r in manifest["records"] if r["original"] == "rare.png")
    assert rare["split"] == "train"
    assert manifest["rare_strata_train_only"] == [dict(classes=(0, 1), groups=1)]


def test_cross_split_group_and_label_tampering_rejected(tmp_path):
    raw = make_raw(tmp_path / "raw")
    prepare(raw, tmp_path / "prepared", ["a", "b"], source={"license": "fixture"})
    path = tmp_path / "prepared/manifest.json"
    manifest = json.loads(path.read_text())
    first = manifest["records"][0]
    other = next(r for r in manifest["records"] if r["split"] != first["split"])
    original_group = other["group"]
    other["group"] = first["group"]
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="crosses splits"):
        validate_dataset(path.with_name("data.yaml"))
    other["group"] = original_group
    path.write_text(json.dumps(manifest))
    label = tmp_path / "prepared/labels" / first["split"] / (Path(first["original"]).stem + ".txt")
    label.write_text("0 .5 .5 .1 .1")
    with pytest.raises(ValueError, match="Labels changed"):
        validate_dataset(path.with_name("data.yaml"))
