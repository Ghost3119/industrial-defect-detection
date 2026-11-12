import { CameraControls } from "../components/CameraControls";
import { ErrorNotice, Panel } from "../components/Common";
import type { CameraController } from "../hooks/useCamera";
import type { Health, Runtime } from "../types";
import { defectName, num } from "../format";
export function Settings({
  camera,
  runtime,
  health,
}: {
  camera: CameraController;
  runtime?: Runtime;
  health?: Health;
}) {
  return (
    <div className="two-columns settings-columns">
      <Panel
        title="Cámara y captura"
        detail="Opciones de la sesión del servidor"
      >
        <CameraControls camera={camera} runtime={runtime} />
        {camera.actionError && <ErrorNotice message={camera.actionError} />}
        <p role="status" className="action-message">
          {camera.message}
        </p>
      </Panel>
      <div className="settings-stack">
        <Panel
          title="Modelo de inspección"
          detail={
            health?.model_loaded
              ? "Detector de superficies disponible"
              : "Sin pesos cargados"
          }
        >
          <p className="muted">Configura los pesos del detector con <code>ACERO_MODEL_PATH</code> y los del clasificador con <code>ACERO_CLASSIFIER_PATH</code>.</p>
          <p>Clasificador de estampado · {runtime?.classifier_loaded ? "Disponible" : "Sin pesos cargados"}</p>
          <h3 className="subheading">Clases del detector</h3>
          <div className="class-tags">
            {health?.classes.map((c) => <span key={c}>{defectName(c)}</span>) ||
              "Sin información"}
          </div>
        </Panel>
        <Panel
          title="Entorno de inferencia"
          detail="Información real reportada por el servidor"
        >
          <dl className="system-details">
            <div>
              <dt>Dispositivo activo del detector</dt>
              <dd>{runtime?.active_device || "Aún sin inferencia"}</dd>
            </div>
            <div>
              <dt>CUDA</dt>
              <dd>
                {runtime?.cuda_available ? "Disponible" : "No disponible"}
              </dd>
            </div>
            <div>
              <dt>GPU</dt>
              <dd>
                {runtime?.gpus
                  .map((g) => `${g.name} · ${num(g.memory_mb)} MB`)
                  .join(", ") || "No detectada"}
              </dd>
            </div>
            <div>
              <dt>PyTorch / CUDA runtime</dt>
              <dd>
                {runtime?.torch_version || "—"} / {runtime?.cuda_runtime || "—"}
              </dd>
            </div>
          </dl>
        </Panel>
      </div>
    </div>
  );
}
