"""Prueba USB optativa, únicamente con LED/sin motor. Nunca se ejecuta al compilar."""
import argparse
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", required=True, help="Ejemplo: COM5")
    parser.add_argument("--led-only", action="store_true", required=True,
                        help="Declara que el motor está desconectado y hay LED o simulación")
    args = parser.parse_args()
    import serial  # pip install pyserial; no es dependencia de las pruebas nativas

    with serial.Serial(args.port, 115200, timeout=0.5, write_timeout=0.5) as port:
        time.sleep(2)  # apertura USB puede reiniciar el ESP32; es una prueba del host
        port.reset_input_buffer()

        def command(text, expected):
            port.write((text + "\n").encode("ascii"))
            reply = port.readline().decode("ascii", errors="replace").strip()
            if reply != expected:
                raise AssertionError(f"{text!r}: {reply!r}, esperado {expected!r}")
            print(f"{text!r} -> {reply}")

        try:
            command("STOP", "OK STOP")
            command("PING", "OK PING")
            command("SPEED 1", "OK SPEED")
            command("DIR F", "OK DIR")
            command("ALARM", "OK ALARM")
            command("QUIET", "OK QUIET")
            command("RUN", "OK RUN")
            command("DIR R", "ERR DIR RUNNING")
            # Invalidar continuamente durante >2000 ms debe terminar la marcha.
            started = time.monotonic()
            while time.monotonic() - started < 2.3:
                command("SPEED 10abc", "ERR SPEED")
                time.sleep(0.1)
            command("DIR R", "OK DIR")  # confirma estado detenido sin nuevo comando
            command("RUN", "OK RUN")
            for _ in range(6):
                time.sleep(0.4)
                command("PING", "OK PING")
            command("DIR F", "ERR DIR RUNNING")
            command("STOP", "OK STOP")
            command("DIR F", "OK DIR")
            command("xxxxxxxxxxxxxxxxxRUN", "ERR")
            command("DIR R", "OK DIR")  # el sufijo RUN nunca arrancó
            command("RUN", "OK RUN")
            time.sleep(2.3)  # equivale a ausencia de host; no desconecta físicamente USB
            command("DIR F", "OK DIR")
            print("PASS USB serial; verificar visualmente LED apagados después del paro.")
        finally:
            port.write(b"STOP\nQUIET\n")
            port.flush()


if __name__ == "__main__":
    main()
