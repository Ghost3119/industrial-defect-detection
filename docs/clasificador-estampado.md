# Clasificación experimental de piezas estampadas

## Demostración en la estación

1. Desde la raíz, ejecuta `.\iniciar.ps1 -Dispositivo cuda` y abre `http://127.0.0.1:8000`. Si ya atendía una instancia anterior, detenla en su terminal con Ctrl+C antes de iniciar esta versión.
2. En **Inspección en vivo → Parámetros de captura → Modelo de inspección**, elige **Clasificador de piezas estampadas**. En **Dispositivo de inferencia**, selecciona **GPU · CUDA**. Deja el umbral provisional en 90 % para poder comparar las capturas de la demostración.
3. Pulsa **Buscar cámaras**, elige la webcam y pulsa **Iniciar cámara**. Centra la pieza completa, espera a que se estabilice la imagen y pulsa **Capturar e inspeccionar**. La vista previa por sí sola suma cero inspecciones. También puedes clasificar una foto con **Subir imagen**.
4. Lee en voz alta la categoría predicha y compara las tres puntuaciones. La foto muestra toda la pieza. Una confianza inferior al umbral produce **REVISAR**. Por encima del umbral, una predicción `ok` queda **Pendiente de validación** y una categoría defectuosa muestra **Defecto predicho**. La decisión de calidad corresponde a quien inspecciona.
5. Abre **Historial**, selecciona la inspección y verifica la foto, el modelo, las puntuaciones y la latencia. Para volver al detector de superficies, detén la cámara, cambia el modelo y vuelve a iniciarla.

FastAPI carga `outputs/stamped-v1/full/weights/best.pt` al iniciar. Para instalar los pesos en otra ruta, establece `$env:ACERO_CLASSIFIER_PATH` antes del arranque. El detector usa su propia configuración `ACERO_MODEL_PATH` y conserva el flujo de detección de superficies. Las clasificaciones se guardan junto a la inspección en la tabla adicional `stamped_classifications` de SQLite. Los indicadores de detecciones y severidades se calculan sobre las inspecciones del detector. El historial contiene ambos modos.

## Fotografías y partición

Se reutilizaron el inventario y los 629 pares candidatos de la auditoría. Los 544 JPEG eran legibles. Se comprobó el SHA-256 de cada original al preparar sus copias. La auditoría encontró cero duplicados exactos y 107 pares de similitud perceptual entre categorías. Se conservaron las etiquetas del equipo de Mecánica.

| Etiqueta | Originales | Entrenamiento | Validación | Reserva |
|---|---:|---:|---:|---:|
| `ok` | 144 | 100 | 22 | 22 |
| `falta_embutido_material` | 200 | 140 | 30 | 30 |
| `ruptura_deformacion` | 200 | 140 | 30 | 30 |
| **Total** | **544** | **380** | **82** | **82** |

Las conexiones transitivas entre pares dieron 207 grupos visuales. Cada grupo completo se asignó a un solo conjunto. Se priorizaron grupos tardíos en el orden de los nombres de WhatsApp para la reserva y después para validación, respetando los cupos por clase y usando la semilla 42 para desempates. Se comprobó que ninguno de los 629 pares cruza conjuntos. La hora del nombre no identifica una sesión de captura. Puede haber fuga de identidad física entre conjuntos: distintas vistas de las mismas tres piezas pueden compartir marcas, fondo e iluminación. En la clase de falta de embutido reaparece una mancha marrón. La clase de ruptura tuvo menor luminancia media en la auditoría. El prototipo puede aprovechar estas pistas.

El manifiesto local `dataset/stamped-v1/manifest.json` vincula cada ID, ruta original, hash, grupo y partición. Se mantuvo toda la imagen añadiendo márgenes grises hasta 224 × 224. Durante entrenamiento se permitieron pequeñas variaciones de brillo/contraste (0.10) y saturación (0.04). Se desactivaron recortes de área variable, volteos, borrado, mezcla y aumentos automáticos. Validación, reserva e inferencia usan el encuadre completo.

## Entrenar y reproducir en PowerShell

Usa el entorno con CUDA descrito en el README. Esta corrida utilizó Ultralytics 8.4.210 y PyTorch 2.14.1+cu130. Los pesos iniciales fueron `yolo11n-cls.pt`, SHA-256 `c62d41bf9625777760018bf914d2e6cd472420ccd01706d97a61cb6c82502bd7`. Ultralytics descarga ese archivo si falta. El detector superficial se carga por separado.

Los comandos siguientes usan directorios nuevos para poder reproducir la corrida sin sobrescribir el modelo de demostración. Si ya tienes el inventario, comienza directamente por la preparación. Sólo para una instalación nueva sin la auditoría, genérala una vez con `& $python -m training.audit_stamped $source $audit` después de definir las variables.

```powershell
$python = '.\.venv\Scripts\python.exe'
$source = 'C:\Users\picud\Downloads\Data set'
$audit = 'outputs\stamped-audit-20261112'
$data = 'dataset\stamped-reproduccion'
$runs = 'outputs\stamped-reproduccion'

& $python -m training.stamped prepare --source $source --audit $audit --data $data
if ($LASTEXITCODE) { throw 'Falló la preparación' }
& $python -m training.stamped train --data $data --runs $runs --name smoke --epochs 2 --batch 16
if ($LASTEXITCODE) { throw 'Falló la prueba corta' }
& $python -m training.stamped train --data $data --runs $runs --name full --epochs 50 --batch 16
if ($LASTEXITCODE) { throw 'Falló el entrenamiento' }
& $python -m training.evaluate_stamped --data $data --run "$runs\full" --output "$runs\evaluation"
if ($LASTEXITCODE) { throw 'Falló la evaluación' }
```

Ambas corridas parten de los mismos pesos iniciales con transferencia, GPU 0, lote 16, semilla 42 y paciencia 10. El ajuste sólo ve `fit/train` y `fit/val`. La reserva está fuera de `fit`. Cada corrida comprueba su checkpoint en CUDA y escribe `run.json`, `args.yaml`, `results.csv` y `weights/{best,last}.pt`. Para usar la reproducción en el dashboard, ejecuta `$env:ACERO_CLASSIFIER_PATH = (Resolve-Path "$runs\full\weights\best.pt").Path` antes de iniciar la aplicación.

## Resultados de esta corrida

La prueba corta duró 20.0 s. La completa terminó por parada temprana en la época 12 de 50, con mejor época 2 según el entrenador. Duró 37.6 s incluyendo la comprobación del checkpoint. PyTorch registró 282 MiB de memoria CUDA reservada máxima en el proceso de entrenamiento sobre la RTX 4050 Laptop. Esta cifra excluye otros procesos y memoria del controlador.

Se evaluó una vez el checkpoint elegido por validación sobre las 82 fotografías reservadas. Hubo **76 aciertos (92.68 %)**. La tabla usa la clase con mayor puntuación, incluidas las predicciones marcadas para revisión.

| Clase real | Fotos | Precisión | Recall | F1 | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| Falta de embutido y material | 30 | 100.00 % | 96.67 % | 98.31 % | 0 | 1 |
| OK | 22 | 78.57 % | 100.00 % | 88.00 % | 6 | 0 |
| Ruptura y deformación | 30 | 100.00 % | 83.33 % | 90.91 % | 0 | 5 |

| Real ↓ / Predicha → | Falta | OK | Ruptura |
|---|---:|---:|---:|
| Falta | 29 | 1 | 0 |
| OK | 0 | 22 | 0 |
| Ruptura | 0 | 5 | 25 |

**Defectuosas predichas como OK: 6 de 60.** La foto 322 era de falta de embutido. Las fotos 500, 512, 514, 515 y 519 eran de ruptura. El umbral provisional fijado antes de la evaluación marcó para revisión 7 de las 82 fotos, entre ellas 4 de los 6 errores. Las fotos 514 y 519 recibieron 98.1 % y 93.5 % para OK y quedaron pendientes de validación. Las métricas describen vistas de piezas conocidas. La generalización a otras piezas físicas sigue sin medirse.

Los resultados locales están en `outputs/stamped-v1/evaluation/`: `metrics.json`, `confusion.png`, `predictions.csv` y `errores.html`. Abre la galería en el mismo equipo del dataset preparado. El checkpoint entregado tiene SHA-256 `9a708c8d319fa0850c491b67eabe1ae9eb99bc6f07723a35686e1d7967084b60`.

## Prueba física con las tres piezas

Identifica cada pieza con Mecánica antes de capturar y anota su categoría real. Mantén la pieza completa dentro del encuadre. Toma como referencia una vista frontal a 30 cm con luz difusa. Para cada una de las tres piezas, prueba esa referencia, luz lateral, menor iluminación, giro de −15° y +15°, y distancias de 20 y 40 cm. Cambia una condición por vez. Recoloca la pieza entre capturas. Con tres repeticiones por condición obtendrás 63 capturas. Conserva también las que fallen.

Después de cada captura manual, toma su ID de **Historial**. El siguiente ejemplo registra las condiciones observadas y recupera desde FastAPI las tres puntuaciones, la decisión, el umbral, los pesos y la latencia. Sustituye el ID de ejemplo por el que acabas de verificar.

```powershell
.\tools\registrar_prueba_estampado.ps1 -Inspeccion 123 -Real ruptura_deformacion -Sesion hackaton-1 -Luz lateral -Angulo 0 -DistanciaCm 30
```

El archivo `outputs/webcam-estampado/ensayos.csv` es exclusivo de los ensayos físicos registrados por el operador. Al finalizar, cuenta aciertos y errores por condición y categoría, incluyendo todos los casos `defectuosa_como_ok`, aunque el estado sea REVISAR. Reporta la mediana y el rango de `inferencia_ms` para CUDA. Las métricas de webcam van en su propio informe.

**Comprobación técnica realizada.** DirectShow leyó la cámara 0 a 640 × 480 y el clasificador procesó la vista previa en `cuda:0`. En 12 muestras posteriores al arranque, la latencia mediana fue 9.66 ms (8.75–12.16 ms), medida alrededor de la llamada de inferencia y su preprocesamiento. Se registraron cero inspecciones en esa comprobación. La captura manual, persistencia y consulta desde el navegador se probaron con vídeo de demostración en una base temporal. El reconocimiento físico bajo las distintas condiciones queda pendiente de presentar las tres piezas.
