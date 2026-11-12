import { render, screen } from "@testing-library/react";
import { ResultPanel, HistoryTable } from "./Common";
import { HistoryDetail } from "../views/History";
import { vi } from "vitest";
const row = {
  id: 17,
  timestamp: "2026-11-11T20:00:00Z",
  status: "PASS",
  defects_found: 0,
  primary_defect: null,
  primary_confidence: null,
  severity: null,
};
test("stamped result shows the three scores and pending quality on a whole image", () => {
  render(<ResultPanel result={{ status: "REVISAR", defects_found: 0, defects: [], severity: null, annotated_image: "",
    classification: { model: "YOLO11n-cls estampadas", predicted: "ok", confidence: .75, review_threshold: .90,
      weights_sha256: "test", scores: {ok: .75, ruptura_deformacion: .10, falta_embutido_material: .15} } }} />);
  expect(screen.getByText("REVISAR")).toBeVisible();
  expect(screen.getByText(/Calidad pendiente de validación/)).toBeVisible();
  expect(screen.getByText("Falta de embutido y material")).toBeVisible();
  expect(screen.getByText("Ruptura y deformación")).toBeVisible();
  expect(screen.getByText("OK", {exact: true})).toBeVisible();
  expect(screen.queryByText(/zonas señaladas/)).not.toBeInTheDocument();
});
test("absence of detections never certifies approval", () => {
  render(
    <ResultPanel
      result={{
        status: "NO_DETECTIONS",
        defects_found: 0,
        defects: [],
        severity: null,
        annotated_image: "",
      }}
    />,
  );
  expect(screen.getByText("Sin detecciones")).toBeVisible();
  expect(
    screen.getByText(/calidad de la pieza no está verificada/),
  ).toBeVisible();
  expect(screen.queryByText(/^Aprobada$/)).not.toBeInTheDocument();
});
test("detection names, severity and meaning of confidence are in Spanish", () => {
  render(
    <ResultPanel
      result={{
        status: "FAIL",
        defects_found: 1,
        defects: [
          { class_name: "patches", severity: "MAJOR", confidence: 74.7 },
        ],
        severity: "MAJOR",
        annotated_image: "",
      }}
    />,
  );
  expect(screen.getByText("Manchas o parches")).toBeVisible();
  expect(screen.getByText("Moderada")).toBeVisible();
  expect(screen.getByText(/no el porcentaje de daño/)).toBeVisible();
  expect(screen.queryByText(/Prueba con aluminio/)).not.toBeInTheDocument();
});
test("legacy PASS remains explicitly unverified", () => {
  render(<HistoryTable rows={[row]} onSelect={vi.fn()} />);
  expect(screen.getByText("Histórico sin verificar")).toBeVisible();
});
test("historical details disclose missing media and model instead of inventing them", () => {
  render(<HistoryDetail row={row} onClose={vi.fn()} />);
  expect(screen.getByRole("dialog")).toBeVisible();
  expect(screen.getByText("No disponibles en este registro")).toBeVisible();
  expect(screen.getByText("Imágenes no vinculadas al historial")).toBeVisible();
});
