import { vi } from "vitest";
import { api, ApiError, errorMessage } from "./api";
afterEach(() => vi.unstubAllGlobals());
test("camera start uses actual backend contract, including demo and device", async () => {
  const fetch = vi
    .fn()
    .mockResolvedValue({ ok: true, json: async () => ({ running: true }) });
  vi.stubGlobal("fetch", fetch);
  await api.start({
    source: "demo",
    backend: "dshow",
    width: 640,
    height: 480,
    fps: 30,
    conf: 0.61,
    device: "cuda",
  });
  expect(fetch).toHaveBeenCalledWith(
    "/camera/start",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        source_type: "demo",
        camera_index: 0,
        backend: "dshow",
        width: 640,
        height: 480,
        fps: 30,
        conf: 0.61,
        device: "cuda",
      }),
    }),
  );
});
test("preview has its own non-recording endpoint and carries inference settings", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  await api.image(new Blob(["image"]), "/preview", 0.57, "cpu");
  expect(fetch).toHaveBeenCalledWith(
    "/preview?conf=0.57&device=cpu",
    expect.objectContaining({ method: "POST", body: expect.any(FormData) }),
  );
});

test("automatic camera sends interval and optional linked conveyor without issuing separate RUN", async () => {
  const fetch = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
  vi.stubGlobal("fetch", fetch);
  await api.start({ source: "0", backend: "auto", width: 640, height: 480, fps: 30,
    conf: 0.4, device: "cpu", auto_interval_s: 1.5, use_conveyor: true, conveyor_speed: 20 });
  const body = JSON.parse(fetch.mock.calls[0][1].body);
  expect(body).toMatchObject({ auto_interval_s: 1.5, use_conveyor: true, conveyor_speed: 20 });
  expect(fetch).toHaveBeenCalledTimes(1);
});
test("503 errors are actionable and the raw backend error is retained", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ detail: "Missing weights" }),
      }),
  );
  await expect(api.health()).rejects.toThrow("Missing weights");
  expect(errorMessage(new ApiError(503, "Missing weights"))).toContain(
    "modelo o el dispositivo",
  );
});

test("missing ESP32 endpoints identify an outdated backend instead of an absent USB device", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 404, json: async () => ({ detail: "Not Found" }) }));
  await expect(api.conveyorPorts()).rejects.toThrow("Reinicia el backend");
});
