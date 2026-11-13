# Controlador de banda — Acero Cifrado

Adaptación incremental de `conveyor_controller.ino`, proporcionado desde
`Downloads/banda/industrial-defect-detection-master/firmware/conveyor_controller/`.
Se conservan las funciones y los modos originales (0–3), el puerto 115200 y los
siete comandos. No hay cambios en YOLO, backend ni frontend. El original de
Descargas permanece intacto. Esta incorporación no integra todavía el firmware con la aplicación.

## Estado de hardware y bloqueo

**ULN2003, versión de voltaje del motor y fuente pendientes de confirmación.
No conectar ni probar el motor en esta fase.** El modo predeterminado es
`DRIVE_28BYJ48` (4), pero `BYJ48_HARDWARE_CONFIRMED=0` y
`BYJ48_LED_SIMULATION=0`: `RUN` responde `ERR HARDWARE UNCONFIRMED` y los cuatro
GPIO permanecen en LOW. Compilar/cargar no ejecuta ninguna secuencia automática.

Para LED o Wokwi, habilitar **solamente** `BYJ48_LED_SIMULATION=1` en una
compilación separada, siempre sin motor conectado. Esta opción habilita GPIO
reales si el binario se carga a una placa; no detecta si hay un motor conectado.
No sustituye la confirmación del hardware. No activar `BYJ48_HARDWARE_CONFIRMED`
hasta verificar físicamente:

- Motor unipolar de cinco hilos **28BYJ-48 nominal de 5 V**: hay variantes; leer
  etiqueta y ficha del ejemplar, comprobar resistencia de bobinas y conector.
- Módulo ULN2003, orden de IN1–IN4, retorno GND y diodos de protección/COM a +5 V.
  Verificar que sus entradas trabajan con lógica de 3.3 V a la corriente requerida;
  no suponer compatibilidad de todo módulo o clon por su nombre comercial.
- Fuente regulada de 5 V, polaridad, corriente suficiente para dos bobinas
  energizadas, caída del Darlington y margen; dimensionar con la resistencia y
  consumo medidos del motor/módulo real, sin fijar un consumo universal.
- Mecanismo capaz de quedar seguro **sin par de retención**: STOP, watchdog y
  arranque liberan las bobinas. Si la carga puede retroceder o caer, se necesita
  un freno/retención mecánica antes de habilitar movimiento. El paro eléctrico
  no garantiza detención mecánica instantánea. No se implementa retención activa.

El 28BYJ-48 no queda validado por software para arrastrar la banda con carga;
evaluar par, transmisión y temperatura posteriormente. Usar paro físico que corte
la potencia del motor. Desconectar USB no implica necesariamente quitar la fuente
del motor: si el ESP32 sigue alimentado, el watchdog para a los 2000 ms; si pierde
alimentación, resistencias externas de pull-down evitan entradas flotantes.

## Cableado propuesto, todavía sin autorizar prueba física

![Esquema de señales, potencia y tierra común](wiring.svg)

| ESP32 DevKit (GPIO, no número físico) | ULN2003 |
| --- | --- |
| GPIO18 | IN1 |
| GPIO19 | IN2 |
| GPIO21 | IN3 |
| GPIO22 | IN4 |
| GND | GND y negativo de la fuente de motor |

Conectar el motor al conector de cinco hilos del módulo, tras comprobar su
orden. En un ULN2003A suelto: entradas 1B–4B = pines 1–4; salidas 1C–4C =
16–13; emisor común = pin 8 (GND); COM = pin 9 (+5 V para los diodos).
El común positivo de las bobinas va a +5 V. **COM no es GND**. El pin rotulado
VCC/+ del módulo suele conectar el común del motor y COM; verificar el esquema
del módulo real antes de alimentar. No cablear por colores sin verificar.

Alimentar el ESP32 por USB. La fuente externa de 5 V alimentará **únicamente el
ULN2003/motor**, con negativo unido a GND del ESP32. No unir ese +5 V al pin
5V/VIN del DevKit mientras esté alimentado por USB. No alimentar el motor desde
3V3, GPIO ni desde el regulador del ESP32. No aplicar 5 V a los GPIO.
Añadir pull-down externos de 10 kΩ de cada IN a GND si el módulo no garantiza
estado bajo durante reset/desconexión; no sustituyen el firmware. Usar cableado
corto, masa común firme y desacoplo junto al módulo según su ficha; comprobar
rieles partidos de la protoboard. No montar conexiones con alimentación presente.

## Secuencia y velocidad

La tabla del sketch corresponde a IN1 IN2 IN3 IN4:

```text
F: 1000 → 1100 → 0100 → 0110 → 0010 → 0011 → 0001 → 1001 → ...
R: recorre la misma tabla en sentido inverso.
STOP / watchdog / arranque: 0000.
```

La primera fase después de encender es `1000`; tras STOP se conserva el índice y
se reanuda con la fase adyacente según DIR. Sin energización puede variar la
posición mecánica: el controlador no conoce posición absoluta ni detecta pérdidas
de pasos. F/R son convenciones; confirmar posteriormente el sentido de la banda.

`SPEED 1` → 40 y `SPEED 100` → 400 **medios pasos por segundo** (SPS),
interpolación lineal `MIN + (MAX-MIN)*(n-1)/99`. No son RPM del eje ni los 5000 Hz
del modo STEP_DIR. Ajustes del nuevo modo:

| Constante | Inicial | Uso |
| --- | --- | --- |
| `BYJ48_MIN_SPS` | 40 | Objetivo mínimo, pendiente de validar con carga |
| `BYJ48_MAX_SPS` | 400 | Objetivo máximo inicial conservador, no garantía bajo carga |
| `BYJ48_ACCEL_SPS2` | 200 | Rampa de subida/bajada, en medios pasos/s² |

La rampa parte de 0; durante el arranque puede estar por debajo de MIN. Llegar a
400 SPS toma aproximadamente 2 s, por lo que se debe enviar heartbeat incluso
durante la rampa. `SPEED` cambia el objetivo con aceleración/desaceleración;
`STOP` y el watchdog interrumpen la rampa y ponen los cuatro GPIO en LOW en esa
iteración. Se usa `micros()`, a lo sumo una fase por vuelta, sin `delay()` ni
recuperación de pasos en ráfaga si el loop se retrasa. No se cambia DIR en marcha.
Los otros modos conservan `ACCEL_MS` y su comportamiento de reducción inmediata.

## Protocolo USB serial

115200 baudios, 8N1, una línea ASCII terminada en LF (`\n`); CRLF también sirve.
Se conserva normalización de mayúsculas y espacios al inicio/final.

| Comando | Respuesta aceptada | Efecto |
| --- | --- | --- |
| `RUN` | `OK RUN` | Arranca sólo bajo habilitación del modo; repetido no reinicia la rampa |
| `STOP` | `OK STOP` | Paro eléctrico inmediato y liberación de bobinas |
| `PING` | `OK PING` | Heartbeat sin iniciar movimiento |
| `SPEED 1` … `SPEED 100` | `OK SPEED` | Fija velocidad objetivo; no arranca |
| `DIR F` / `DIR R` | `OK DIR` | Sólo detenido; en marcha `ERR DIR RUNNING` |
| `ALARM` | `OK ALARM` | Activa patrón del buzzer, no arranca |
| `QUIET` | `OK QUIET` | Silencia buzzer, no afecta el motor |

Errores de número: `ERR SPEED`; desconocidos/marcos corruptos: `ERR`; hardware
sin confirmar: `ERR HARDWARE UNCONFIRMED`. No se añadieron comandos nuevos.
El buzzer original sigue asignado a GPIO33; puede configurarse `BUZZER_PIN=-1`
si no existe. ALARM sigue activo tras STOP hasta QUIET, igual que el original.

El watchdog de **2000 ms** sólo se renueva al aceptar un comando completo.
`ERR`, líneas vacías, `SPEED 10abc`, `DIR` rechazado, fragmentos sin LF y basura
no lo renuevan. Enviar `PING` cada 500 ms mientras se desee mantener RUN.
ALARM/QUIET y otros comandos válidos también lo renuevan por compatibilidad.
Al vencer, se para antes de procesar un PING tardío; sólo un RUN explícito puede
arrancar de nuevo. Las líneas mayores de 16 caracteres o con controles se
descartan **hasta LF**, incluyendo cualquier sufijo RUN/PING. La recepción tiene
presupuesto por vuelta para que un flujo continuo no impida atender el watchdog.
Este protocolo no autentica al emisor y no sustituye un circuito de seguridad.

## Compilar y cargar por USB

Arduino IDE 2: instalar **esp32 by Espressif Systems**, core 3.x, usando la
[URL estable oficial](https://espressif.github.io/arduino-esp32/package_esp32_index.json)
en preferencias. Abrir `conveyor_controller/conveyor_controller.ino`, elegir
**ESP32 Dev Module** (ESP32 clásico, no C3/S3) y el puerto COM detectado. El modo
28BYJ48 no necesita librerías externas. Sólo el modo servo necesita ESP32Servo.
Para LED, editar `#define BYJ48_LED_SIMULATION 0` a `1` en una copia o usar las
opciones CLI siguientes; conservar HARDWARE_CONFIRMED en 0.

Alternativa PowerShell, desde la raíz del repositorio, con Arduino CLI en PATH:

```powershell
arduino-cli core update-index --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
arduino-cli core install esp32:esp32 --additional-urls https://espressif.github.io/arduino-esp32/package_esp32_index.json
# Compilación predeterminada BLOQUEADA (sin movimiento):
arduino-cli compile --fqbn esp32:esp32:esp32 --output-dir firmware/build/locked firmware/conveyor_controller
arduino-cli board list
# Sustituir COM5 por el puerto real. Motor desconectado:
arduino-cli upload --fqbn esp32:esp32:esp32 --port COM5 --input-dir firmware/build/locked firmware/conveyor_controller
arduino-cli monitor --port COM5 --config baudrate=115200
```

En el monitor con LF enviar `PING`, `STOP`, `SPEED 1`, `DIR F`, `ALARM`, `QUIET`.
En el binario bloqueado, `RUN` debe devolver `ERR HARDWARE UNCONFIRMED` y las
cuatro salidas deben seguir apagadas. Abrir el puerto puede reiniciar el ESP32;
no debe provocar movimiento. Si la carga falla por bootloader, mantener BOOT
al iniciar la conexión y soltarlo cuando comience la escritura. Cerrar el monitor
antes de cargar o de ejecutar el script de pruebas, porque ocupa el puerto.

Para probar **sólo cuatro LED, motor desconectado**, conectar cada GPIO mediante
resistencia de 1 kΩ al ánodo de su LED y cátodo a GND, y compilar separadamente:

```powershell
arduino-cli compile --fqbn esp32:esp32:esp32 --build-property "compiler.cpp.extra_flags=-DBYJ48_LED_SIMULATION=1" --output-dir firmware/build/led firmware/conveyor_controller
arduino-cli upload --fqbn esp32:esp32:esp32 --port COM5 --input-dir firmware/build/led firmware/conveyor_controller
python -m pip install pyserial
python firmware/tests/serial_led_test.py --port COM5 --led-only
```

El script **envía RUN** y requiere declarar `--led-only`; no detecta el hardware.
No ejecutarlo con motor. Prueba respuestas, STOP, DIR, basura, heartbeats y
vencimiento usando DIR como comprobación del reposo. Verificar que las cuatro
salidas LED se apagan al parar. Para observar a mano: `SPEED 1`, `DIR F`, `RUN`,
PING cada 500 ms; después `SPEED 100`, `SPEED 1`, `STOP`, `DIR R`, `RUN` con PING.
Para comprobar desconexión, interrumpir heartbeats sin retirar alimentación de
la placa y comprobar apagado antes de 2 s más la latencia de una vuelta del loop.
No hay script de prueba automática de motor ni se autoriza esa fase todavía.

Para elegir modos anteriores, cambiar `DRIVE_MODE` o compilar con
`--build-property "compiler.cpp.extra_flags=-DDRIVE_MODE=0"` (0 relé, 1 servo,
2 PWM, 3 STEP_DIR). Para modo 1: `arduino-cli lib install ESP32Servo`.
El bloqueo de confirmación afecta únicamente al modo 4; los modos 0–3 conservan
su control de potencia y deben cargarse sólo con sus cargas desconectadas.

## Pruebas sin placa y Wokwi

```powershell
python firmware/tests/run_tests.py
```

Requiere compilador C++17: MSVC con herramientas C++, g++ o clang++. Compila el
**sketch real**, no una traducción en Python, con dobles de Arduino. Ejecuta once
configuraciones: ESP32 modos 0–4, modo 4 LED, modo 4 confirmado **sólo en memoria**,
y ramas no ESP32 de los cuatro modos originales. Comprueba arranque sin salida,
comandos y errores, overflow del parser, heartbeat inválido/válido, STOP durante
rampas, secuencia de fases F/R, tasas extremas, aceleración/desaceleración, ausencia
de ráfagas, rollover de ambos relojes y regresión de salidas de los modos 0–3.
Los dobles no prueban periféricos reales, niveles eléctricos ni carga mecánica.

La carpeta [wokwi](wokwi/README.md) contiene cuatro LED, resistencias y analizador
lógico para las cuatro señales. No requiere ULN2003 ni motor. Preparar una
simulación no constituye validación eléctrica o mecánica del montaje.
Consultar [resultados y límites de la verificación](VALIDATION.md): los cinco
modos compilaron para ESP32 y las once configuraciones nativas pasaron. El
diagrama Wokwi se validó sin errores, pero no se ejecutó la simulación por falta
de token, ni las pruebas USB o de motor físico.

## Fuentes técnicas

- [Espressif: instalación Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/installing.html).
- [Espressif: alimentación DevKitC V4](https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32/esp32-devkitc/user_guide.html): usar una sola entrada de alimentación para la placa.
- [TI: ficha ULN2003A](https://www.ti.com/lit/ds/symlink/uln2003a.pdf): entradas, colectores, emisor común y diodos con COM a la alimentación de la carga.
- [Arduino CLI](https://docs.arduino.cc/arduino-cli/installation/).
- [Wokwi: configuración](https://docs.wokwi.com/vscode/project-config) y [analizador lógico](https://docs.wokwi.com/parts/wokwi-logic-analyzer).

Las velocidades son una elección inicial de ingeniería pendiente de validar, no
un valor certificado por la ficha del ejemplar de motor (todavía no identificada).
