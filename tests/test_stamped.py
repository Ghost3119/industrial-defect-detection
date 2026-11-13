from collections import Counter
from types import SimpleNamespace

import numpy as np
import pytest
import torch

from backend.stamped_input import NAMES, square_frame
from stamped_classifier import StampedClassifier
from training.stamped import assign_splits


def test_prepare_keeps_transitive_views_and_all_edges_of_rectangular_frame():
    rows = [dict(id=str(i), category=NAMES[i % 3]) for i in range(60)]
    pairs = [dict(id1=4, id2=52), dict(id1=52, id2=55)]
    assign_splits(rows, pairs)
    first = [row["split"] for row in rows]
    assert rows[4]["group"] == rows[52]["group"] == rows[55]["group"]
    assert first[4] == first[52] == first[55]
    assert Counter(first) == {"train": 42, "val": 9, "holdout": 9}
    assign_splits(rows, pairs)
    assert first == [row["split"] for row in rows]
    frame = np.zeros((100, 200, 3), dtype=np.uint8)
    frame[:, [0, -1]] = 255
    square = square_frame(frame, 200)
    assert np.all(square[:50] == 114) and np.all(square[50:150, [0, -1]] == 255)


@pytest.mark.parametrize("scores,status", [
    ([0.05, 0.92, 0.03], "PENDIENTE"),
    ([0.43, 0.56, 0.01], "REVISAR"),
    ([0.02, 0.03, 0.95], "DEFECTO_PREDICHO"),
])
def test_classifier_outputs_inspection_states_without_boxes(monkeypatch, tmp_path, scores, status):
    names = dict(enumerate(NAMES))
    output = SimpleNamespace(names=names, probs=SimpleNamespace(data=torch.tensor(scores)))
    fake = SimpleNamespace(names=names, task="classify", to=lambda device: None, predict=lambda *a, **kw: [output])
    path = tmp_path / "model.pt"
    path.write_bytes(b"test")
    monkeypatch.setattr("stamped_classifier.YOLO", lambda _: fake)
    result = StampedClassifier(path).predict(np.zeros((16, 32, 3), np.uint8), 0.90, "cpu")
    assert result["status"] == status and result["defects"] == []
    assert set(result["classification"]["scores"]) == set(NAMES)
    assert result["classification"]["quality"] == "pendiente_de_validacion"
