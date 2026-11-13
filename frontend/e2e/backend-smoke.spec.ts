import { expect, test } from "@playwright/test";
import path from "node:path";
test("compiled frontend against isolated real FastAPI, YOLO and CUDA", async ({
  page,
  request,
}) => {
  const runtime = await (await request.get("/runtime")).json();
  expect(runtime.model_loaded).toBe(true);
  const before = (await (await request.get("/stats")).json()).total_inspected;
  await page.goto("/");
  await page.getByLabel("Registro de inspecciones").selectOption("manual");
  await expect(
    page.getByText("Sistema conectado", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Buscar cámaras" }).click();
  await page.getByLabel("Fuente de cámara").selectOption("demo");
  await page
    .getByLabel("Dispositivo de inferencia")
    .selectOption(runtime.cuda_available ? "cuda" : "cpu");
  await page
    .getByRole("button", { name: "Iniciar cámara", exact: true })
    .click();
  await expect
    .poll(
      async () =>
        (await (await request.get("/camera/status")).json()).frames_processed,
      { timeout: 30000 },
    )
    .toBeGreaterThan(2);
  expect((await (await request.get("/stats")).json()).total_inspected).toBe(before);
  await expect(
    page.getByRole("img", {
      name: "Vista previa de la cámara USB con detecciones",
    }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Capturar e inspeccionar", exact: true })
    .click();
  await expect(
    page.getByText(
      "Inspección registrada. Imágenes disponibles para descargar.",
    ),
  ).toBeVisible({ timeout: 30000 });
  await expect
    .poll(
      async () => (await (await request.get("/stats")).json()).total_inspected,
    )
    .toBe(before + 1);
  const original = await page
    .getByRole("link", { name: "Imagen original" })
    .getAttribute("href");
  expect((await request.get(original!)).status()).toBe(200);
  const state = await (await request.get("/camera/status")).json();
  expect(state.inference_device).toBe(
    runtime.cuda_available ? "cuda:0" : "cpu",
  );
  await page.getByLabel("Umbral de confianza", { exact: true }).fill("0.65");
  await page.getByRole("button", { name: "Aplicar umbral en vivo" }).click();
  await expect
    .poll(
      async () =>
        (await (await request.get("/camera/status")).json()).confidence,
    )
    .toBe(0.65);
  await page.evaluate(() => { window.scrollTo(0, 0); if(document.activeElement instanceof HTMLElement) document.activeElement.blur(); });
  await page.screenshot({
    path: path.resolve("../outputs/frontend-redesign/real-stack-demo.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Detener", exact: true }).click();
  await expect
    .poll(
      async () => (await (await request.get("/camera/status")).json()).running,
    )
    .toBe(false);
  if (await page.getByRole("button", { name: "Abrir navegación" }).isVisible())
    await page.getByRole("button", { name: "Abrir navegación" }).click();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: "Historial", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: /Ver inspección/ }).first(),
  ).toBeVisible();
});

test("stamped model captures a frame on GPU and restores its scores from history", async ({ page, request }) => {
  const runtime = await (await request.get("/runtime")).json();
  test.skip(!runtime.classifier_loaded, "Se requieren los pesos del prototipo");
  const before = (await (await request.get("/stats")).json()).total_inspected;
  await page.goto("/");
  await page.getByLabel("Modelo de inspección").selectOption("clasificador");
  await page.getByLabel("Registro de inspecciones").selectOption("manual");
  await expect(page.getByLabel("Umbral de confianza", { exact: true })).toHaveValue("0.9");
  await page.getByRole("button", { name: "Buscar cámaras" }).click();
  await page.getByLabel("Fuente de cámara").selectOption("demo");
  await page.getByLabel("Dispositivo de inferencia").selectOption("cuda");
  await page.getByRole("button", { name: "Iniciar cámara", exact: true }).click();
  try {
    const capture = page.getByRole("button", { name: "Capturar e inspeccionar" });
    await expect(capture).toBeEnabled({ timeout: 20000 });
    await capture.click();
    await expect(page.getByText("YOLO11n-cls estampadas", { exact: true })).toBeVisible();
    await expect(page.getByAltText("Pieza estampada inspeccionada")).toBeVisible();
    const [latest] = (await (await request.get("/history")).json()).inspections;
    expect(Object.keys(latest.classification.scores).sort()).toEqual(["falta_embutido_material", "ok", "ruptura_deformacion"]);
    expect(latest.classification.device).toBe("cuda:0");
    expect(latest.classification.inference_ms).toBeGreaterThan(0);
    expect((await request.get(latest.classification.captures.original_url)).status()).toBe(200);
    expect((await (await request.get("/stats")).json()).total_inspected).toBe(before);
    await page.goto("/#historial");
    await page.getByRole("button", { name: `Ver inspección ${latest.id}`, exact: true }).click();
    await expect(page.getByRole("dialog").getByText(latest.classification.model)).toBeVisible();
    await expect(page.getByRole("dialog").getByAltText("Pieza estampada inspeccionada")).toBeVisible();
  } finally {
    await request.post("/camera/stop");
  }
});
