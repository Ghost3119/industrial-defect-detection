# Cuatro fases con LED en Wokwi

No hay motor ni ULN2003 en este montaje. Las resistencias de 1 kΩ limitan la
corriente de cada LED. GPIO18/19/21/22 también llegan a D0/D1/D2/D3 del analizador.
El sketch empieza detenido; no hay escenarios que envíen RUN automáticamente.

## Wokwi para VS Code

Desde la raíz del repositorio (Arduino CLI y core ESP32 3.x):

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 --build-property "compiler.cpp.extra_flags=-DBYJ48_LED_SIMULATION=1" --output-dir firmware/wokwi/build firmware/conveyor_controller
```

Abrir **firmware/wokwi como carpeta de trabajo** en VS Code e iniciar
`Wokwi: Start Simulator`. Así los paths de wokwi.toml corresponden a su raíz.
La extensión/CLI puede requerir licencia o token de Wokwi; no se incluye ninguno.

## Wokwi web (sin herramientas locales)

1. Crear proyecto [ESP32](https://wokwi.com/projects/new/esp32).
2. Reemplazar `sketch.ino` con el contenido de
   `../conveyor_controller/conveyor_controller.ino` y cambiar únicamente el valor
   predeterminado de `BYJ48_LED_SIMULATION` a `1`; dejar HARDWARE_CONFIRMED en 0.
3. Reemplazar `diagram.json` con el archivo de esta carpeta. No necesita librerías.
4. Iniciar simulación: los cuatro LED deben permanecer apagados hasta RUN.

En terminal serial, enviar líneas terminadas con LF:

```text
PING          -> OK PING
SPEED 1       -> OK SPEED
DIR F         -> OK DIR
RUN           -> OK RUN
PING          -> OK PING    (repetir antes de 2000 ms; recomendado cada 500 ms)
DIR R         -> ERR DIR RUNNING
STOP          -> OK STOP
DIR R         -> OK DIR
RUN           -> OK RUN
STOP          -> OK STOP
```

Después de RUN, dejar de enviar comandos por >2000 ms: los LED deben apagarse.
Repetir enviando `SPEED 10abc` frecuentemente: esos errores tampoco mantienen
la marcha. `DIR F` debe responder OK tras vencer. Enviar una línea
`xxxxxxxxxxxxxxxxxRUN`: debe responder ERR y conservar reposo.

Para inspección temporal, iniciar captura del analizador y exportar VCD según
la interfaz de Wokwi. D0…D3 deben mostrar `1000,1100,0100,0110,0010,0011,0001,1001`
en F y el recorrido contrario en R. A régimen, SPEED 1 da 25 ms entre fases;
SPEED 100 da 2.5 ms. La rampa inicial y la bajada de SPEED son graduales.
A 40 SPS la vista LED puede ser difícil de seguir: comprobar VCD o pausar
la simulación. STOP debe llevar D0…D3 a 0000 sin esperar la rampa.

La simulación preparada comprueba señales; no modela torque, corriente,
calentamiento, diodos, niveles de entrada del módulo ni pérdidas de pasos.
