"""Compila/ejecuta el .ino real con dobles de Arduino; no accede a USB."""
import glob
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent


def compiler():
    for name in ("g++", "clang++", "cl"):
        if path := shutil.which(name):
            return path, os.environ.copy(), name == "cl"
    if os.name == "nt":
        # Usa solamente el entorno de compilación del VS ya instalado.
        pattern = str(Path(os.environ["ProgramFiles"]) / "Microsoft Visual Studio/*/*/VC/Auxiliary/Build/vcvars64.bat")
        for batch in sorted(glob.glob(pattern), reverse=True):
            result = subprocess.run(
                f'cmd /d /s /c ""{batch}" >nul && set"',
                capture_output=True, text=True,
            )
            if result.returncode:
                continue
            env = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line and not line.startswith("="))
            if path := shutil.which("cl", path=env.get("Path", env.get("PATH"))):
                return path, env, True
    raise SystemExit("Instala un compilador C++17: MSVC (C++ Build Tools), g++ o clang++.")


def main():
    cxx, env, msvc = compiler()
    with tempfile.TemporaryDirectory(prefix="conveyor-tests-") as tmp:
        for esp32, mode, led, confirmed in (
            *((True, mode, 0, 0) for mode in range(5)),
            (True, 4, 1, 0), (True, 4, 0, 1),
            *((False, mode, 0, 0) for mode in range(4)),
        ):
            defines = [f"DRIVE_MODE={mode}", f"BYJ48_LED_SIMULATION={led}", f"BYJ48_HARDWARE_CONFIRMED={confirmed}"]
            if esp32:
                defines.append("ESP32=1")
            exe = Path(tmp) / ("controller.exe" if os.name == "nt" else "controller")
            if msvc:
                args = [cxx, "/nologo", "/std:c++17", "/EHsc", "/W4", "/utf-8", f"/I{HERE}", *[f"/D{x}" for x in defines], str(HERE / "controller_test.cpp"), f"/Fe:{exe}"]
            else:
                args = [cxx, "-std=c++17", "-Wall", "-Wextra", f"-I{HERE}", *[f"-D{x}" for x in defines], str(HERE / "controller_test.cpp"), "-o", str(exe)]
            subprocess.run(args, env=env, cwd=tmp, check=True)
            subprocess.run([str(exe)], env=env, check=True)
    print("11 configuraciones verificadas; sin hardware.")


if __name__ == "__main__":
    main()
