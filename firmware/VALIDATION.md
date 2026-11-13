# Verificación de esta adaptación

Se trabajó únicamente en `firmware/`. No se cargó firmware a hardware, no se
abrió un puerto USB, no se movió un motor y no se hizo merge.

## Procedencia

Se copió y adaptó el archivo proporcionado, conservando los modos y funciones
originales (`applyOutput`, `setBelt`, `updateRamp`, `updateBuzzer`,
`handleCommand`, `setup`, `loop`). El original en Descargas no se modificó.
SHA256 del original:

```text
faf034b65d45dc4e3c5891aa7b6a71e6232730263b390fcf3e2aa5d5c6c89774
```

Los cambios comunes de seguridad son: validación completa del número SPEED,
watchdog renovado sólo por comandos aceptados, descarte de marcos corruptos
hasta LF, presupuesto de recepción, RUN idempotente y nivel de relé detenido
precargado antes de configurar su GPIO como salida. La configuración de pin PWM
ahora usa PWM_PIN explícitamente. La rampa específica de 28BYJ48 no modifica las
salidas ni las constantes de los modos originales.

## Resultados ejecutados sin hardware

| Comprobación | Resultado |
| --- | --- |
| `python firmware/tests/run_tests.py` | 11 configuraciones pasan con MSVC C++17 |
| ESP32: relé, servo, PWM analógico, STEP/DIR | Compilan y enlazan |
| ESP32: 28BYJ48 bloqueado | Compila y enlaza |
| ESP32: 28BYJ48 con LED, HARDWARE_CONFIRMED=0 | Compila y enlaza |
| Wokwi CLI 0.29.1: `lint firmware/wokwi` | Sin errores; 1 aviso informativo del catálogo sobre documentación de la placa |
| `diagram.json`, `wiring.svg` | Sintaxis JSON/XML válida |
| Scripts Python de prueba | Compilan con `py_compile` |

Compilación real con **Arduino CLI 1.6.0**, **arduino-esp32 3.3.12**,
`esp32:esp32:esp32`, y **ESP32Servo 3.2.1** sólo para modo 1. Se utilizaron
los paquetes oficiales con comprobación SHA256 y herramientas aisladas bajo
`outputs/firmware-tools/` (ignoradas por Git). Se acortaron temporalmente rutas
de Windows para el compilador; el mapeo se retiró al terminar. El firmware no
necesita ese ajuste en una instalación habitual de Arduino con rutas cortas.

| Variante | Flash utilizada (bytes) | Variables globales (bytes) |
| --- | ---: | ---: |
| 28BYJ48 bloqueado | 274116 | 22180 |
| 28BYJ48 LED | 274372 | 22180 |
| Relé | 274016 | 22172 |
| Servo | 284215 | 22544 |
| PWM analógico | 282591 | 22360 |
| STEP/DIR | 283503 | 22368 |

No hubo advertencias del sketch en la compilación ESP32 con `--warnings all`.
La librería ESP32Servo emite una advertencia por una variable TAG sin usar.
MSVC emite advertencias de conversiones numéricas del código original y de
comparaciones con bool en los dobles; las once ejecuciones finalizan correctamente.
Las pruebas nativas incluyen las ramas no ESP32 de los modos 0–3, pero no se
compiló una imagen AVR real.

Los binarios locales quedan en `firmware/build/{locked,relay,servo,analog,stepdir}`
y `firmware/wokwi/build` para LED, ignorados por Git. Nunca usar la variante LED
con un motor conectado. Los logs de esta sesión están en
`outputs/firmware-tools/{native-tests,compile-*,wokwi-lint,wokwi-run}.log`.

## Pendiente de validación externa

- **Wokwi en ejecución:** se intentó iniciar el montaje LED; la CLI informa
  ausencia de `WOKWI_CLI_TOKEN`. No se ejecutó la simulación ni se obtuvo VCD.
  La carpeta y los binarios están preparados para VS Code o el editor web;
  seguir [la guía de simulación](wokwi/README.md).
- **USB serial real:** el script optativo está preparado y se comprobó su
  sintaxis; no se ejecutó sobre una placa. Las pruebas de comandos ejecutadas
  usan el sketch con Serial simulado, sin comprobar drivers USB ni latencias
  físicas. La ausencia de heartbeat se prueba con reloj controlado.
- **Motor y alimentación:** el usuario confirmó el modelo 28BYJ-48, pero falta
  confirmar voltaje nominal del ejemplar, ULN2003 y fuente. No se habilitó
  movimiento físico. Falta evaluar también niveles lógicos, consumo,
  temperatura, par, transmisión, carga y seguridad al liberar bobinas.

Las pruebas sin hardware no demuestran capacidad de arrastre ni reemplazan la
verificación eléctrica/mecánica previa al uso. Consultar [la guía USB y cableado](README.md).
