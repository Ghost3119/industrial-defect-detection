# Inspección automática y ESP32 en simultáneo

La app puede guardar inspecciones sin pulsar **Capturar e inspeccionar**.
El ESP32 conserva el firmware que ya tiene: la app se comunica mediante
`RUN`, `STOP`, `PING` y `SPEED`, a 115200 baudios. No se carga firmware desde la app.

## Empezar a detectar sin botón de captura

1. Reinicia el backend después de actualizar el código. El frontend de producción
   ya se compiló en esta sesión; para reconstruirlo: `cd frontend; npm run build`.
2. Abre la app en la computadora del servidor. En **Parámetros de captura**, deja
   **Registro de inspecciones → Automático por intervalo** (predeterminado).
3. Ajusta **Intervalo de inspección (segundos)**, de 0.5 a 3600; inicial: 2 segundos.
   Selecciona detector o clasificador, cámara y CPU/GPU como antes.
4. Pulsa **Iniciar cámara** una vez. Cada intervalo guarda el resultado, un JPEG
   original y otro anotado, actualiza **Última inspección**, historial y monitor.
   No hace falta pulsar Capturar. **Detener** finaliza la sesión del servidor.

Se registra el fotograma recién analizado usando el mismo resultado de inferencia,
sin ejecutar el modelo otra vez para cada registro automático. Si el procesamiento
es más lento que el intervalo, se omiten intervalos pendientes; no se acumulan
capturas en una cola ni se intenta recuperarlas en ráfaga. El tiempo real entre
registros puede ser mayor que el intervalo por inferencia y escritura a disco.

**Los registros representan muestras temporales, no piezas únicas.** La misma
pieza estacionaria y un encuadre vacío pueden generar registros repetidos. Este
cambio no incorpora sensor, seguimiento ni validación de presencia. Para pruebas
por pieza con protocolo controlado, elegir **Captura manual**. Los resultados del
clasificador de estampado conservan su carácter provisional y umbral de revisión.
Las fotos y la base crecen mientras la sesión automática esté activa.

En **Este dispositivo**, al iniciar la cámara se activa el análisis periódico y,
en modo automático, los fotogramas se envían para registrar. Detener o desmarcar
**Inspección automática activa** cancela nuevas solicitudes. La banda vinculada
está disponible con la cámara del servidor, que sigue ejecutándose aunque se
recargue o cierre la pestaña. Cerrar la pestaña no detiene esa sesión: usar Detener.

## Conectar el ESP32 sin cambiar su programa

Dependencia del backend, incluida en requirements.txt e instalada en esta sesión:

```powershell
.\.venv\Scripts\python.exe -m pip install "pyserial>=3.5,<4"
.\iniciar.ps1
```

Si el servidor anterior sigue abierto, detenerlo con Ctrl+C en su terminal antes
de iniciar la nueva versión. Mantener la selección de pesos/dispositivo utilizada
previamente. La actualización no cambia pesos, entrenamiento ni clases.

1. Conectar el ESP32 por USB de datos. Cerrar Monitor Serial/Plotter de Arduino:
   el puerto COM debe tener un solo propietario.
2. Abrir **ESP32 y banda**, pulsar **Buscar ESP32**, elegir el puerto y
   **Conectar ESP32**. En esta computadora se enumeró un adaptador
   `USB-Enhanced-SERIAL CH9102 (COM5)`; confirmar que corresponde a la placa
   desconectando/reconectando USB antes de elegirlo, sin movimiento del motor.
3. La conexión espera el reinicio USB, envía STOP y comprueba PING. No envía RUN.
   Abrir la app o iniciar el backend tampoco conecta ni arranca automáticamente.
4. Puede iniciarse la inspección automática sin banda vinculada mientras el
   ESP32 permanece conectado, detenido y atendido por su propio hilo serial.

La app admite solamente puertos locales enumerados, no direcciones serial por red.
La sesión está diseñada para **un proceso del backend**, sin varios workers y sin
otro programa accediendo simultáneamente al mismo COM.

Si aparece **Not Found** en el panel serial mientras Arduino sí enumera COM5,
comprobar que el backend sea la versión actual: `/conveyor/ports` y
`/conveyor/status` deben responder 200. El lanzador verifica esas rutas y el
campo de intervalo antes de reutilizar una instancia, porque un proceso Python
antiguo también puede servir el HTML recién compilado desde el disco.
La interfaz enumera los puertos al cargar; **Buscar ESP32** actualiza la lista.
El proxy de desarrollo incluye `/conveyor`.

En la sesión de corrección de puertos quedó operativa una instancia actualizada
en **http://127.0.0.1:8001**, conservando la anterior de 8000. Para reutilizar la
actualizada: `.\iniciar.ps1 -Puerto 8001`. Se verificó en el navegador real que
COM5 aparece seleccionado sin errores, sin abrir el puerto serial. La revisión
automática rechazó reiniciar el proceso de 8000 con `blocked by policy`; no se
intentó terminarlo mediante otra herramienta. Validación: 7 pruebas enfocadas
del frontend, 2 del lanzador, compilación, rechazo de la API antigua y
reutilización correcta de la API actualizada.

## Movimiento sincronizado: pendiente de confirmar hardware

El modelo 28BYJ-48 está confirmado. **Todavía falta confirmar el voltaje del
ejemplar, ULN2003, fuente de 5 V y seguridad del mecanismo al liberar bobinas.**
Las pruebas de esta fase no abren el puerto físico ni ejecutan movimiento.
El control de movimiento de la app está bloqueado por defecto, además del bloqueo
del firmware. No anular esos bloqueos para probar el motor pendiente de confirmar.

Después de completar esa confirmación y disponer de firmware que autorice el
hardware real, la configuración explícita del servidor es
`ACERO_CONVEYOR_HARDWARE_CONFIRMED=1`. Ese ajuste no se activa en esta sesión.
Abrir la app mediante **localhost** en la PC conectada a la placa; el servidor
rechaza iniciar movimiento desde clientes remotos.

Con hardware ya autorizado, conectar el ESP32, seleccionar una velocidad 1–100 %,
marcar **Mover la banda durante la inspección del servidor** y después iniciar
la cámara. La app espera el primer resultado válido antes de enviar SPEED y RUN.
No modifica DIR ni implementa rechazo mecánico automático por defecto encontrado.
El porcentaje conserva el significado del DRIVE_MODE configurado en el firmware.

- Un único hilo serial mantiene PING cada 500 ms, separado del hilo OpenCV/YOLO.
  No se manda RUN repetidamente ni hay reconexión o rearranque automático.
- Detener la cámara, fallar su lectura/inferencia/registro o cerrar el backend
  intenta enviar STOP. Se intenta detener la banda antes de esperar a una lectura
  de cámara bloqueada. **Detener banda e inspección** cancela también la sesión
  vinculada, para impedir que un inicio pendiente vuelva a moverla.
- Si no hay resultados nuevos de cámara durante 2 s, se ordena STOP aunque
  continúen los latidos. La banda no vuelve a arrancar al recuperarse la imagen.
- Si el USB o el backend fallan, no se envían más latidos; permanece el watchdog
  de 2000 ms del firmware. La app muestra el error y no informa marcha confirmada.
- Si el firmware rechaza RUN con `ERR HARDWARE UNCONFIRMED`, se conserva el
  rechazo; la app no lo omite. El paro eléctrico no sustituye un paro físico ni
  asegura que la mecánica se detenga instantáneamente.

## API y validación

`POST /camera/start` conserva el comportamiento manual para clientes existentes
que no envían campos nuevos. La interfaz selecciona automáticamente 2 s.

```json
{
  "source_type": "camera", "camera_index": 0, "device": "auto",
  "auto_interval_s": 2, "use_conveyor": false, "conveyor_speed": 25
}
```

`auto_interval_s=0` significa manual. Estado y último registro están en
`GET /camera/status`; los registros nuevos también se difunden por el WebSocket
existente. Rutas serial: `GET /conveyor/status`, `GET /conveyor/ports`,
`POST /conveyor/connect` con `{"port":"COM5"}`, `POST /conveyor/disconnect`
y `POST /conveyor/stop`. No existe endpoint genérico para mandar comandos arbitrarios.

Pruebas enfocadas:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_camera_session.py tests/test_conveyor.py tests/test_api.py tests/test_runtime.py -q
cd frontend
npm test
npm run build
npm run test:e2e
```

Las pruebas seriales usan un doble del puerto, nunca COM5. Comprueban STOP/PING
al conectar, bloqueo de RUN, heartbeat independiente, desconexión, rechazo del
firmware, cámara estancada y STOP concurrente con un arranque pendiente. Las
pruebas de cámara verifican registro automático, imágenes, difusión, limpieza
ante fallo, ausencia de inferencia duplicada y conservación del modo manual.
Las pruebas de interfaz con fixtures no demuestran precisión del modelo ni
compatibilidad eléctrica del montaje; queda pendiente la prueba física autorizada.

Resultados de esta sesión: 59 pruebas enfocadas del backend aprobadas; 18 pruebas
generales del frontend y 2 pruebas enfocadas del panel serial aprobadas. Los
14 casos de navegador existentes pasaron; tras corregir el selector de la prueba,
pasaron también los dos nuevos casos automáticos en escritorio y móvil. Se
comprobaron visualmente las capturas de escritorio/móvil y se compiló el frontend de producción.
Los logs están en `outputs/automatic-*.log`. No se ejecutó inferencia nueva con
motor físico; la enumeración de COM5 fue de sólo lectura.
