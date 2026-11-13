"""Whole-frame stamped-part classification; all quality decisions need validation."""
import base64
import hashlib
from threading import Lock
from time import perf_counter

import cv2
from ultralytics import YOLO

from runtime import resolve_device, synchronize
from stamped_input import NAMES, square_frame


class StampedClassifier:
    def __init__(self, path):
        self.model = YOLO(str(path))
        if self.model.task != "classify" or set(self.model.names.values()) != set(NAMES):
            raise ValueError("Pesos incompatibles con las tres clases de estampado")
        self.signature = hashlib.sha256(path.read_bytes()).hexdigest()
        self.lock = Lock()
        self.device = None

    def predict(self, frame, conf, device):
        selected = resolve_device(device)
        with self.lock:
            if self.device != selected:
                self.model.to(selected)
                self.device = selected
            synchronize(selected)
            start = perf_counter()
            output = self.model.predict(square_frame(frame), imgsz=224, device=selected, verbose=False)[0]
            scores = {output.names[i]: float(p) for i,p in enumerate(output.probs.data.cpu().tolist())}
            synchronize(selected)
            elapsed = (perf_counter()-start)*1000
        predicted = max(scores,key=scores.get)
        status = "PENDIENTE" if predicted == "ok" else "DEFECTO_PREDICHO"
        if scores[predicted] < conf:
            status = "REVISAR"
        success, image = cv2.imencode(".jpg",frame)
        if not success:
            raise RuntimeError("No se pudo codificar la imagen")
        encoded = base64.b64encode(image).decode("ascii")
        processing_ms = (perf_counter() - start) * 1000
        return dict(status=status,defects_found=0,defects=[],severity=None,
                    annotated_image=encoded,
                    classification=dict(model="YOLO11n-cls estampadas",weights_sha256=self.signature,
                                        predicted=predicted,confidence=scores[predicted],scores=scores,
                                        review_threshold=conf,quality="pendiente_de_validacion"),
                    inference_device=selected,inference_ms=round(elapsed,2),processing_ms=round(processing_ms,2),
                    processing_fps=round(1000/max(processing_ms,.001),2))
