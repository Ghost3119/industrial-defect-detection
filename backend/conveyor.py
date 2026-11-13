"""Single owner of the ESP32 serial port; heartbeat independent of inference."""
from concurrent.futures import Future, TimeoutError
from queue import Empty, PriorityQueue
from threading import Event, Lock, RLock, Thread
from time import monotonic
import itertools


class ConveyorError(RuntimeError):
    pass


def serial_ports():
    try:
        from serial.tools.list_ports import comports
    except ImportError:
        return []
    # Prefer USB bridges over Bluetooth virtual COM ports in the selector.
    return [{"port": p.device, "description": p.description}
            for p in sorted(comports(), key=lambda p: (p.vid is None, p.device))]


class ConveyorSession:
    def __init__(self, *, hardware_confirmed=False, serial_factory=None, boot_wait=2.0):
        self.hardware_confirmed = hardware_confirmed
        self.serial_factory = serial_factory
        self.boot_wait = boot_wait
        self._lifecycle = RLock()
        self._lock = Lock()
        self._stop = Event()
        self._thread = None
        self._queue = PriorityQueue(maxsize=16)
        self._sequence = itertools.count()
        self._motion_epoch = 0
        self._camera_frame_at = None
        self._camera_required = False
        self._state = {"connected": False, "running": False, "port": None, "error": None}

    def status(self):
        with self._lock:
            return {**self._state, "hardware_confirmed": self.hardware_confirmed}

    def _update(self, **values):
        with self._lock:
            self._state.update(values)

    def connect(self, port):
        with self._lifecycle:
            if self._thread and self._thread.is_alive():
                raise ConveyorError("Desconecta el ESP32 antes de cambiar de puerto.")
            self._queue = PriorityQueue(maxsize=16)
            self._stop.clear()
            self._update(connected=False, running=False, port=port, error=None)
            ready = Future()
            self._thread = Thread(target=self._run, args=(port, ready), daemon=True)
            self._thread.start()
            try:
                ready.result(timeout=self.boot_wait + 3)
            except Exception as exc:
                self._stop.set()
                self._thread.join(timeout=2)
                raise ConveyorError(str(exc) or "El ESP32 no respondió.") from exc
            return self.status()

    @staticmethod
    def _exchange(port, command):
        port.write((command + "\n").encode("ascii"))
        expected = "OK " + command.split()[0]
        deadline = monotonic() + 0.7
        while monotonic() < deadline:
            reply = port.readline().decode("ascii", errors="replace").strip()
            if reply == expected:
                return
            if reply.startswith("ERR"):
                raise ConveyorError(f"ESP32: {reply}")
        raise ConveyorError(f"ESP32 sin respuesta a {command.split()[0]}.")

    def _run(self, name, ready):
        port = None
        try:
            factory = self.serial_factory
            if factory is None:
                try:
                    from serial import Serial
                except ImportError as exc:
                    raise ConveyorError("Instala pyserial en el entorno del backend.") from exc
                factory = Serial
            port = factory(name, 115200, timeout=0.1, write_timeout=0.2)
            if self._stop.wait(self.boot_wait):
                raise ConveyorError("Conexión cancelada.")
            port.reset_input_buffer()
            self._exchange(port, "STOP")
            self._exchange(port, "PING")
            self._update(connected=True)
            ready.set_result(True)
            heartbeat = monotonic() + 0.5
            while not self._stop.is_set():
                with self._lock:
                    stale = (self._state["running"] and self._camera_required and
                             (self._camera_frame_at is None or monotonic() - self._camera_frame_at >= 2))
                if stale:
                    self._exchange(port, "STOP")
                    self._update(running=False, error="Banda detenida: la cámara dejó de entregar resultados durante 2 s.")
                if monotonic() >= heartbeat:
                    self._exchange(port, "PING")
                    heartbeat = monotonic() + 0.5
                try:
                    _, _, command, reply, epoch = self._queue.get(timeout=0.05)
                except Empty:
                    continue
                if not reply.set_running_or_notify_cancel():
                    continue
                try:
                    if command == "RUN":
                        with self._lock:
                            if epoch != self._motion_epoch:
                                raise ConveyorError("Arranque cancelado por STOP.")
                    self._exchange(port, command)
                    if command in ("RUN", "STOP"):
                        self._update(running=command == "RUN")
                    reply.set_result(True)
                except Exception as exc:
                    reply.set_exception(ConveyorError(str(exc)))
                    raise
        except Exception as exc:
            self._update(error=str(exc))
            if not ready.done():
                ready.set_exception(ConveyorError(str(exc)))
        finally:
            if port is not None:
                try:
                    port.write(b"STOP\n")
                except Exception:
                    pass  # The firmware watchdog remains the fallback after a lost link.
                try:
                    port.close()
                except Exception:
                    pass
            self._update(connected=False, running=False)
            while not self._queue.empty():
                _, _, _, reply, _ = self._queue.get_nowait()
                if not reply.done():
                    reply.set_exception(ConveyorError("Conexión serial cerrada."))

    def _command(self, command, epoch=None):
        if not self.status()["connected"]:
            raise ConveyorError("Conecta primero el ESP32 por USB serial.")
        reply = Future()
        self._queue.put_nowait((0 if command == "STOP" else 1, next(self._sequence), command, reply, epoch))
        try:
            reply.result(timeout=1.5)
        except TimeoutError as exc:
            reply.cancel()
            self._stop.set()  # A timed-out RUN must not remain pending for later execution.
            raise ConveyorError("Tiempo de espera serial agotado; conexión detenida.") from exc

    def require_motion(self):
        if not self.hardware_confirmed:
            raise ConveyorError("Movimiento bloqueado: confirma ULN2003, motor de 5 V, fuente y mecanismo antes de habilitarlo.")
        if not self.status()["connected"]:
            raise ConveyorError("Conecta primero el ESP32 por USB serial.")

    def touch_frame(self):
        with self._lock:
            self._camera_frame_at = monotonic()

    def run(self, speed=25, *, camera_required=False):
        with self._lifecycle:
            self.require_motion()
            with self._lock:
                epoch = self._motion_epoch
                self._camera_required = camera_required
            if not 1 <= speed <= 100:
                raise ConveyorError("Velocidad fuera de 1–100.")
            self._command(f"SPEED {speed}")
            self._command("RUN", epoch=epoch)

    def stop(self):
        with self._lock:
            self._motion_epoch += 1
            self._camera_required = False
        if self.status()["connected"]:
            self._command("STOP")

    def disconnect(self):
        with self._lifecycle:
            try:
                self.stop()
            finally:
                self._stop.set()
                if self._thread:
                    self._thread.join(timeout=2)
            return self.status()
