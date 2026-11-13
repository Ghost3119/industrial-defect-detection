import { useEffect, useState } from "react";
import { api, ApiError, errorMessage } from "../services/api";
import { useResource } from "../hooks/useResource";
import type { CameraController } from "../hooks/useCamera";
import { ErrorNotice } from "./Common";

export function ConveyorControls({ camera }: { camera: CameraController }) {
  const status = useResource(api.conveyor, 1000);
  const [ports, setPorts] = useState<{ port: string; description: string }[]>([]);
  const [port, setPort] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let disposed = false;
    void api.conveyorPorts().then((result) => {
      if (!disposed) {
        setPorts(result.ports);
        setPort(result.ports[0]?.port || "");
      }
    }).catch((e) => { if (!disposed) setError(errorMessage(e)); });
    return () => { disposed = true; };
  }, []);
  async function action(task: () => Promise<unknown>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await task(); await status.reload(); }
    catch (e) { setError(e instanceof ApiError ? e.message : errorMessage(e)); }
    finally { setBusy(false); }
  }
  const connected = !!status.data?.connected;
  const locked = !!camera.data?.running || !!camera.busy;
  return <details className="panel capture-configuration">
    <summary>ESP32 y banda <span>{connected ? `${status.data?.port} · ${status.data?.running ? "En marcha" : "Detenida"}` : "Sin conexión"}</span></summary>
    <p className="microcopy">Conectar conserva el firmware cargado y deja la banda detenida. Cierra el monitor serial de Arduino para liberar el puerto.</p>
    <div className="form-grid">
      <label>Puerto USB del ESP32
        <select value={port} disabled={connected || busy} onChange={(e) => setPort(e.target.value)}>
          <option value="">Selecciona un puerto</option>
          {ports.map((p) => <option key={p.port} value={p.port}>{p.port} · {p.description}</option>)}
        </select>
      </label>
      <label>Velocidad de banda (%)
        <input type="number" min="1" max="100" value={camera.options.conveyor_speed ?? 25} disabled={locked}
          onChange={(e) => {
            const speed = Number(e.currentTarget.value);
            camera.setOptions((o) => ({ ...o, conveyor_speed: speed }));
          }} />
      </label>
    </div>
    <div className="button-row">
      <button className="button secondary" disabled={connected || busy} onClick={() => void action(async () => {
        const result = await api.conveyorPorts(); setPorts(result.ports); setPort(result.ports[0]?.port || "");
      })}>Buscar ESP32</button>
      <button className="button secondary" disabled={busy || (!connected && !port)}
        onClick={() => void action(() => connected ? api.disconnectConveyor() : api.connectConveyor(port))}>
        {connected ? "Desconectar ESP32" : "Conectar ESP32"}
      </button>
      <button className="button secondary" disabled={!connected || busy} onClick={() => void action(api.stopConveyor)}>{camera.data?.use_conveyor ? "Detener banda e inspección" : "Detener banda"}</button>
    </div>
    <label className="checkbox-row">
      <input type="checkbox" checked={!!camera.options.use_conveyor}
        disabled={locked || (!camera.options.use_conveyor && (!connected || !status.data?.hardware_confirmed))}
        onChange={(e) => {
          const checked = e.currentTarget.checked;
          camera.setOptions((o) => ({ ...o, use_conveyor: checked }));
        }} />
      Mover la banda durante la inspección del servidor
    </label>
    {!status.data?.hardware_confirmed && <p className="microcopy">Movimiento deshabilitado hasta confirmar controlador ULN2003, motor de 5 V, fuente y mecanismo.</p>}
    {(error || status.error || status.data?.error) && <ErrorNotice message={error || status.error || status.data?.error || ""} />}
  </details>;
}
