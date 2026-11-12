# Experimento público de Acero Cifrado

Rama `feat/public-dataset-training`, basada en `de65195` (master funcional, limpio y
sin diferencias con origin/master al iniciar). No se mezcló a master. El modelo de
validación existente `model/steel-defect-yolo11n.pt` se conserva con SHA-256
`621c742492ffe5137d214893499e47d59066685c53c400810de71cd26e4f8bac`.

## Selección y licencias (revisión 2026-11-11)

| Fuente | Evidencia consultada | Decisión |
| --- | --- | --- |
| [NEU, autores Song y Yan](https://faculty.neu.edu.cn/songkc/en/zdylm/263265/) | 1,800 imágenes de 200×200, seis clases, enlaces NEU-DET con anotaciones y solicitud de citar; sin licencia explícita | No descargar |
| [GitHub siddhartamukherjee](https://github.com/siddhartamukherjee/NEU-DET-Steel-Surface-Defect-Detection) | API de GitHub `license: null`; distribución usada por el conversor histórico | No descargar; el conversor histórico no acredita permiso |
| [Kaggle kaustubhdikshit](https://www.kaggle.com/datasets/kaustubhdikshit/neu-surface-defect-database) | API `/api/v1/datasets/view/kaustubhdikshit/neu-surface-defect-database`: `licenseName: Unknown`, versión 1 | No descargar |
| [Hugging Face KeenForgeAI](https://huggingface.co/datasets/KeenForgeAI/NEU-DET-corrected/blob/main/LICENSE) | Su LICENSE distingue modificaciones CC BY 4.0 de originales sin licencia declarada; no otorga permiso para imágenes originales | No descargar |
| [Roboflow intelfactor](https://universe.roboflow.com/intelfactor-aj2un/neu-det-fquva-er2ey) | Declara Public Domain; no acredita autorización de Song/Yan ni explica la cesión | No tomar la etiqueta del mirror como permiso del titular |
| [CR7-DET V1, autores](https://zenodo.org/records/14263276) | Publicación del dataset por Jiang, Shengquan; Wang, Xiaoyu; Chen, Shuzong; DOI 10.5281/zenodo.14263276; licencia explícita `cc-by-4.0` en API Zenodo | **Seleccionado como alternativa autorizada por el usuario** |

CR7-DET contiene acero laminado en frío, siete clases y cajas de detección. La ficha
describe 4,140 imágenes y 11,020 anotaciones. El archivo real se inspecciona y valida;
no se asume que la descripción de LabelMe implique XML: la distribución trae cajas
YOLO normalizadas TXT en `CR7-DET-main/lengzha/{image,label}`. La correspondencia
ID/clase se comprueba con prefijos de nombres originales y sus etiquetas:
`0 inclusion`, `1 dents`, `2 oil_spots`, `3 pits`, `4 punching`, `5 linear`, `6 macular`.
Los nombres con espacios de los originales se conservan; `oil_spots` es el nombre
normalizado de la clase, sin modificar el ID.

La licencia [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) permite usar y
adaptar imágenes y anotaciones con atribución, enlace a licencia e indicación de
cambios. Atribución: Jiang, Shengquan; Wang, Xiaoyu; Chen, Shuzong (2024), *CR7-DET*,
V1, Zenodo, DOI 10.5281/zenodo.14263276. Cambios locales: agrupación de duplicados,
división reproducible y reorganización YOLO; sin redibujar cajas ni aumentar los
originales antes de dividir. Citar además el artículo vinculado por sus autores:
[10.1016/j.engappai.2024.109325](https://doi.org/10.1016/j.engappai.2024.109325).

Ultralytics 8.4.210, YOLO11 y sus pesos oficiales `yolo11n.pt` se ofrecen bajo
[AGPL-3.0 o licencia Enterprise](https://www.ultralytics.com/license).
Las condiciones también alcanzan los modelos derivados según el proveedor.
No se interpreta la licencia MIT del código original como licencia de las
dependencias, datasets o pesos. Se conserva MIT y la atribución original; antes de
redistribuir/servir una solución derivada hay que cumplir AGPL, incluyendo el código
correspondiente, o contar con Enterprise. Los pesos actuales de hazemaaa también
declaran AGPL-3.0 (procedencia fijada en README). No se publican binarios en Git.

## PowerShell: entorno y descarga

Desde la raíz del repositorio, con Python del entorno existente:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-cuda.txt
.\.venv\Scripts\python.exe -m pip install -r requirements-training.txt -c docs/public-training-environment.txt
.\.venv\Scripts\python.exe -c "import torch; print(torch.__version__, torch.cuda.is_available()); print(torch.cuda.get_device_name(0))"
.\.venv\Scripts\python.exe -m training.download_public --output dataset/cr7-source
.\.venv\Scripts\python.exe -m training.download_weights
```

El descargador revisa la licencia del registro fijado, verifica el MD5 publicado
`adb0f1fd14a30cac7d1b2a16961cc8be`, calcula SHA-256 y conserva un recibo `source.json`
con metadatos de procedencia. Rechaza sobrescribir destinos existentes o archivos
con checksum distinto. El ZIP tiene 52,620,364 bytes. Una descarga fallida deja
`.partial` para inspección; no se usa para preparar ni entrenar.
El snapshot `public-training-environment.txt` fija las versiones usadas, sin
reemplazar los requisitos de la aplicación. PyTorch CUDA se instala primero desde
el índice oficial indicado en `requirements-cuda.txt`.

Inicialización oficial fijada en `ultralytics/assets`, release `v8.4.0`,
`yolo11n.pt`, SHA-256
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
El entrenador verifica ese hash al usar su modelo predeterminado.

## Preparar, entrenar y reanudar

```powershell
.\.venv\Scripts\python.exe -m training.prepare_public --raw dataset/cr7-source/CR7-DET-main/lengzha --output dataset/cr7 --classes inclusion dents oil_spots pits punching linear macular --source dataset/cr7-source/source.json
# Prueba corta: dos épocas, sin modificar los pesos de validación
.\.venv\Scripts\python.exe -m training.train --data dataset/cr7/data.yaml --epochs 2 --batch 4 --imgsz 640 --device cuda --name cr7-smoke
# Solamente tras decidir lanzar un entrenamiento completo:
.\.venv\Scripts\python.exe -m training.train --data dataset/cr7/data.yaml --epochs 80 --batch 4 --imgsz 640 --device auto --name cr7-full
# Reanudar una ejecución INTERRUMPIDA, conservando su objetivo de épocas original:
.\.venv\Scripts\python.exe -m training.train --data dataset/cr7/data.yaml --resume outputs/public-training/cr7-full/weights/last.pt --device cuda
```

`--epochs`, `--batch`, `--imgsz`, `--model`, `--data`, `--project`, `--seed`,
`--workers` y `--patience` son configurables. Predeterminado: YOLO11n, 640, batch 4,
AMP si CUDA, workers 0 (Windows). `--batch -1` activa AutoBatch de Ultralytics;
si falta memoria, reintentar en un **nuevo** nombre con batch 2 y después 1.
No se oculta una caída a CPU: `--device cuda` falla si CUDA no está disponible.
`auto` selecciona CUDA 0 cuando está disponible y anuncia fallback si no.
Se guardan `best.pt`, `last.pt`, checkpoints por época, CSV, gráficos y
`experiment.json` (versiones, GPU, VRAM, hashes, duración y memoria máxima).
No se permite reutilizar un nombre de ejecución sin `--resume`.

La preparación rechaza anotaciones inválidas, clases desconocidas, cajas duplicadas,
dimensiones inconsistentes, imágenes sin etiqueta y etiquetas huérfanas. Verifica
todas las clases en los tres conjuntos. Semilla 42, fracciones objetivo 70/15/15;
la asignación se estratifica por combinación de clases **por grupos**, por lo que
los tamaños exactos pueden variar. Iguales por píxeles y similares por dHash
(distancia Hamming <=2, cierre transitivo) permanecen juntos; se conservan todos los
originales. El manifiesto registra rutas, SHA-256 de imagen/anotación, hash de
píxeles, grupo, cajas y división. Antes de entrenar/evaluar se verifica integridad.
Combinaciones multiclase con menos de tres grupos independientes permanecen en
train y se enumeran en el manifiesto; cada clase individual debe aparecer en
train, val y test. CR7 contiene algunas imágenes con varias clases, aunque los
prefijos de archivo indiquen sólo una categoría principal.

No existen IDs de bobina, pieza o sesión en la publicación: este control impide
fugas por duplicados detectados, pero **no demuestra independencia entre bobinas**
ni detecta toda variante recortada/rotada. Las cifras son de este benchmark de
imágenes. La aumentación de Ultralytics ocurre únicamente después de dividir.

Para una futura NEU-DET con permiso verificado, el mismo preparador acepta
`--format voc` y las seis clases originales por defecto. Declarar explícitamente
`--box-convention voc-inclusive` (1-based inclusive) o `zero-exclusive` tras revisar
la distribución concreta; no inferirlo de un mirror. Pasar su recibo de permiso en
`--source`. Las pruebas unitarias cubren las seis clases y la conversión VOC.

## Evaluar y seleccionar modelo

```powershell
.\.venv\Scripts\python.exe -m training.evaluate --data dataset/cr7/data.yaml --weights outputs/public-training/cr7-smoke/weights/best.pt --output outputs/public-training/cr7-smoke-test --device cuda
# Selección explícita para la API; reiniciar el proceso después:
$env:ACERO_DATASET_PROFILE = 'cr7-det'
$env:ACERO_MODEL_PATH = 'outputs/public-training/cr7-smoke/weights/best.pt'
$env:ACERO_IMG_SIZE = '640'
$env:ACERO_DEVICE = 'cuda'
.\.venv\Scripts\python.exe backend/main.py
# Regresar al modelo previo:
$env:ACERO_DATASET_PROFILE = 'neu-det'
$env:ACERO_MODEL_PATH = 'model/steel-defect-yolo11n.pt'
```

`report.json` contiene precisión, recall, mAP50 y mAP50-95. Ultralytics calcula mAP
con conf mínima 0.001, NMS IoU 0.7 y precisión/recall en el punto max-F1. Genera
matrices de confusión en `metrics/`. Evidencia separada: conf 0.25, NMS 0.7,
matching greedy por confianza, misma clase e IoU >=0.5, uno a uno. Guarda hasta 12
imágenes por categoría TP/FP/FN, cajas GT verdes y predicciones rojas, JSON por
ejemplo y `per_image.json` completo. Las categorías pueden coexistir en una imagen.
Si una categoría no aparece, se informa cero; no se fabrican ejemplos.
Los conteos de evidencia no tienen por qué coincidir con la matriz de Ultralytics,
que utiliza su propio matching y umbrales. Las métricas no se usan para escoger
hiperparámetros: ajustar sólo con train/val; reservar test para el protocolo fijado.
La prueba corta es una comprobación del pipeline, no selección de modelo final.

El evaluador exige procedencia de entrenamiento con el mismo manifiesto. No se
compara con `steel-defect-yolo11n.pt`: sus clases son distintas y no conocemos su
partición original. Una comparación futura requiere mismas clases, preprocesado,
test y garantía de que ninguno haya visto esas imágenes al entrenar.

No se cambia la API, dashboard, SQLite ni ESP32. Un perfil de clases explícito
impide aceptar pesos COCO como detector de defectos. No hay evidencia de desempeño
en piezas estampadas reales, ni calibración de severidad para CR7-DET.
Esta distribución contiene imágenes con defectos; no permite estimar por sí sola
la tasa de falsos rechazos en piezas sanas ni certificar aprobación de producción.

## Validación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
git status --short
git diff --check
```

Datasets, checkpoints y resultados quedan ignorados. El informe de la ejecución
corta y la estimación medida se registran en `docs/public-training-results.md`.
