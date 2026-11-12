# Prueba corta real — 2026-11-11

Se ejecutó YOLO11n con pesos COCO oficiales fijados y **dos épocas completas**
sobre CR7-DET V1, licencia CC BY 4.0. No se ejecutó el entrenamiento de 80 épocas.
Comandos y condiciones de uso: [pipeline](public-dataset-training.md).
Entorno exacto: [versiones instaladas](public-training-environment.txt).

## Datos y protocolo

4,140 imágenes originales, 11,020 cajas válidas y siete clases verificadas.
Partición con semilla 42: 3,085 train, 527 val y 528 test (1,462 cajas de test).
Se conservaron las rutas y SHA-256 originales en `dataset/cr7/manifest.json`.
59 imágenes son duplicados exactos por píxeles. La agrupación conservadora por
píxeles/dHash produjo 3,312 grupos; el mayor contiene 407 imágenes y permanece
en train. La similitud perceptual no prueba que sean la misma pieza; tampoco
hay identificadores de bobina/sesión para certificar independencia industrial.
Esta partición propia no es directamente comparable con otras publicaciones.

El mejor checkpoint se eligió por **validación**, antes de consultar test.
Evaluación de test: 640, batch 4, CUDA 0, conf mínima 0.001, NMS IoU 0.7.
Precisión y recall corresponden al punto max-F1 calculado por Ultralytics;
no son los conteos a umbral fijo de la evidencia.

| Métrica de test | Valor |
| --- | ---: |
| Precisión | 0.594622 |
| Recall | 0.634175 |
| mAP50 | 0.632414 |
| mAP50-95 | 0.375090 |

Evidencia a conf 0.25 e IoU de matching 0.5, misma clase y asignación uno a uno:
**920 TP, 675 FP y 542 FN**. Se guardaron 12 imágenes de cada categoría, con sus
anotaciones y predicciones en JSON. Las imágenes pueden pertenecer a varias
categorías. La matriz nativa se generó con conf 0.001, por lo que incluye muchas
propuestas de baja confianza y no tiene los mismos conteos que esta evidencia.

## Evidencia local conservada fuera de Git

| Artefacto | Ruta desde la raíz |
| --- | --- |
| Checkpoint seleccionado | `outputs/public-training/cr7-smoke/weights/best.pt` |
| Último checkpoint y snapshots por época | `outputs/public-training/cr7-smoke/weights/` |
| Métricas por época | `outputs/public-training/cr7-smoke/results.csv` |
| GPU, versiones, hashes y duración | `outputs/public-training/cr7-smoke/experiment.json` |
| Registro de entrenamiento | `outputs/public-training/training-smoke.log` |
| Captura NVIDIA durante entrenamiento | `outputs/public-training/gpu-smoke.csv` |
| Reporte de test | `outputs/public-training/cr7-smoke-test/report.json` |
| Matrices de confusión | `outputs/public-training/cr7-smoke-test/metrics/confusion_matrix*.png` |
| Evidencia TP/FP/FN | `outputs/public-training/cr7-smoke-test/examples/` |
| Predicciones completas de test | `outputs/public-training/cr7-smoke-test/per_image.json` |
| Inferencia con configuración del backend | `outputs/public-training/model-selection-check.json` |

El reporte pequeño de métricas también se versiona en
[public-training-report.json](public-training-report.json); imágenes, pesos y
resultados voluminosos permanecen locales y no se publican en el fork.

Hashes SHA-256:

- ZIP CR7-DET V1: `34500cc56ae4eadf7696b6197b504ed18c25349bc3c0564490ab63d95c3c3201`.
- Manifiesto de esta ejecución: `bde27f9f1851ee3a2d1451208e6c41d73d98a557c5fc070f2878aa627bc52675`.
- Inicialización YOLO11n: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- Mejor checkpoint: `f0c7b5cc741042b7840db86b5fcf273c087ec1fd38e4bf0ac83bea6f632e41ed`.
- Modelo anterior intacto: `621c742492ffe5137d214893499e47d59066685c53c400810de71cd26e4f8bac`.

`experiment.json` registra el commit base, el estado de trabajo modificado y los
hashes de los scripts al iniciar; el experimento se ejecutó antes del commit final.
Los resultados no constituyen una comparación con los pesos anteriores, que
tienen otras clases y una partición de entrenamiento desconocida.

## GPU y estimación antes del entrenamiento completo

RTX 4050 Laptop, 6,141 MiB físicos informados por NVIDIA, driver 610.78.
PyTorch 2.14.1+cu130, torchvision 0.29.1+cu130, Ultralytics 8.4.210,
Python 3.14.3 en Windows. El registro confirma CUDA:0, AMP y batch 4 a 640.

- Duración de `model.train`, incluyendo preparación interna y validación final:
  **280.74 segundos (4 min 41 s)**. La verificación previa de integridad queda
  fuera de ese cronómetro.
- Memoria máxima PyTorch: **628 MiB asignados, 842 MiB reservados**. NVIDIA mostró
  aproximadamente 830–980 MiB durante la ejecución. La memoria del proceso en RAM
  fue de aproximadamente 1.28 GB en una captura; no es una medición de pico de RAM.
- Tiempo acumulado al completar las épocas: 120.23 s y 234.29 s. La segunda tomó
  aproximadamente 114.06 s, incluyendo su validación.
- Extrapolación lineal de 80 épocas: aproximadamente **2 h 32 min–2 h 40 min**;
  reservar **2.5–3.5 horas** por variaciones de carga, temperatura y aumentación.
  La prueba corta cierra mosaic desde el inicio; una ejecución larga lo usa, de
  modo que esta estimación no sustituye una medición de dicha ejecución.
- Mantener batch 4 inicialmente: pasó sin OOM y deja margen dentro de 6 GB. El
  consumo de memoria no crece linealmente con las épocas. No se midió batch 8/16.
- Checkpoint completo por época: aproximadamente 26.6 MB. Con `save_period=1`,
  80 snapshots requieren unos **2.13 GB**, más pesos finales, dataset y gráficos.
  Reservar **al menos 3 GB libres** para el pipeline canónico.

## Integración y pruebas

Se cargó el checkpoint real mediante `ACERO_DATASET_PROFILE=cr7-det`,
`ACERO_MODEL_PATH` y `ACERO_IMG_SIZE=640`, y se ejecutó inferencia del backend en
`cuda:0` sobre una imagen de test: dos detecciones. No se cambió el modelo activo
por defecto ni se sobrescribieron los pesos anteriores. Esa llamada incluyó
calentamiento y no es un benchmark de latencia.

La suite completa pasa: **131 pruebas**; incluye preparación determinista,
duplicados, cajas inválidas, seis clases VOC, configuraciones de entrenamiento,
integridad, aislamiento de pesos, reanudación y matching TP/FP/FN. La reanudación
se verifica con dobles de prueba; no se interrumpió una sesión GPU a mitad de una
época para probar recuperación. Existe una advertencia de deprecación de
Starlette/httpx, sin fallos.

No se validaron piezas estampadas reales ni piezas sanas de producción. Las
reglas de severidad existentes no se calibraron con este dataset. La prueba
corta verifica el pipeline y produce métricas reales de CR7-DET; no es un modelo
final ni evidencia de aptitud para producción.
