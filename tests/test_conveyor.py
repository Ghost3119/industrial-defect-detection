from concurrent.futures import ThreadPoolExecutor
from queue import Empty, Queue
from threading import Event
from time import monotonic, sleep

import pytest
from conveyor import ConveyorError, ConveyorSession


class FakeSerial:
    def __init__(self):
        self.commands = []
        self.replies = Queue()
        self.closed = False
        self.failed = False
        self.reject_run = False

    def reset_input_buffer(self):
        pass

    def write(self, data):
        if self.failed:
            raise OSError("USB disconnected")
        for command in data.decode().strip().splitlines():
            self.commands.append((monotonic(), command))
            self.replies.put(b"ERR HARDWARE UNCONFIRMED\n" if self.reject_run and command == "RUN"
                             else ("OK " + command.split()[0] + "\n").encode())

    def readline(self):
        if self.failed:
            raise OSError("USB disconnected")
        try:
            return self.replies.get(timeout=0.05)
        except Empty:
            return b""

    def close(self):
        self.closed = True


def connected(confirmed=False):
    port = FakeSerial()
    session = ConveyorSession(hardware_confirmed=confirmed, serial_factory=lambda *a, **k: port, boot_wait=0)
    session.connect("TEST")
    return session, port


def wait_for(predicate, timeout=3):
    end = monotonic() + timeout
    while not predicate():
        if monotonic() >= end:
            raise AssertionError("Timeout")
        sleep(0.01)


def test_connect_never_runs_and_motion_is_blocked_without_confirmation():
    session, port = connected()
    try:
        assert [c for _, c in port.commands] == ["STOP", "PING"]
        with pytest.raises(ConveyorError, match="bloqueado"):
            session.run()
        assert not session.status()["running"]
        assert not any(c == "RUN" for _, c in port.commands)
    finally:
        session.disconnect()
    assert port.closed


def test_heartbeat_does_not_depend_on_inference_and_stop_is_acknowledged():
    session, port = connected(True)
    try:
        session.run(25)
        assert session.status()["running"]
        # Models a busy camera/inference thread; the serial thread keeps running.
        Event().wait(1.2)
        pings = [at for at, c in port.commands if c == "PING"]
        assert len(pings) >= 3
        assert max(b - a for a, b in zip(pings, pings[1:])) < 1
        session.stop()
        assert not session.status()["running"]
        assert [c for _, c in port.commands].count("RUN") == 1
    finally:
        session.disconnect()


def test_lost_link_closes_port_without_automatic_restart():
    session, port = connected(True)
    session.run()
    port.failed = True
    wait_for(lambda: not session.status()["connected"])
    assert "USB disconnected" in session.status()["error"]
    assert not session.status()["running"] and port.closed
    assert [c for _, c in port.commands].count("RUN") == 1
    session.disconnect()


def test_firmware_rejection_does_not_report_motor_running():
    session, port = connected(True)
    port.reject_run = True
    with pytest.raises(ConveyorError, match="HARDWARE UNCONFIRMED"):
        session.run()
    wait_for(lambda: not session.status()["connected"])
    assert not session.status()["running"]
    session.disconnect()


def test_stalled_camera_stops_motor_despite_continuing_serial_heartbeat():
    session, port = connected(True)
    try:
        session.touch_frame()
        session.run(camera_required=True)
        wait_for(lambda: not session.status()["running"])
        assert session.status()["connected"]
        assert "cámara" in session.status()["error"]
        assert [c for _, c in port.commands].count("STOP") >= 2
    finally:
        session.disconnect()


def test_stop_cancels_concurrent_start_before_run_can_execute():
    session, port = connected(True)
    entered, release = Event(), Event()
    write = port.write

    def blocked(data):
        if data.startswith(b"SPEED"):
            entered.set()
            release.wait(1)
        write(data)
    port.write = blocked
    try:
        with ThreadPoolExecutor() as pool:
            starting = pool.submit(session.run)
            assert entered.wait(1)
            stopping = pool.submit(session.stop)
            wait_for(lambda: session._motion_epoch > 0)
            release.set()
            with pytest.raises(ConveyorError):
                starting.result(timeout=2)
            stopping.result(timeout=2)
        assert not any(c == "RUN" for _, c in port.commands)
    finally:
        release.set()
        session.disconnect()
