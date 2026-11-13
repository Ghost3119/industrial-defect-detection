import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ConveyorControls } from "./ConveyorControls";
import { api } from "../services/api";
import type { CameraController } from "../hooks/useCamera";

function camera(useConveyor: boolean) {
  return { options: { use_conveyor: useConveyor, conveyor_speed: 25 },
    data: { running: false }, busy: "", setOptions: vi.fn() } as unknown as CameraController;
}

test("loading the panel lists USB ports without connecting or enabling movement", async () => {
  vi.spyOn(api, "conveyor").mockResolvedValue({ connected: false, running: false, port: null, hardware_confirmed: false });
  const connect = vi.spyOn(api, "connectConveyor");
  const ports = vi.spyOn(api, "conveyorPorts").mockResolvedValue({ ports: [{ port: "COM5", description: "ESP32" }] });
  render(<ConveyorControls camera={camera(false)} />);
  await userEvent.click(screen.getByText("ESP32 y banda", { exact: false }).closest("summary")!);
  await waitFor(() => expect(screen.getByRole("checkbox", { name: /Mover la banda/ })).toBeDisabled());
  expect(connect).not.toHaveBeenCalled();
  expect(ports).toHaveBeenCalledTimes(1);
  await waitFor(() => expect(screen.getByLabelText("Puerto USB del ESP32")).toHaveValue("COM5"));
});

test("a previously linked conveyor can be unchecked after disconnection", async () => {
  vi.spyOn(api, "conveyor").mockResolvedValue({ connected: false, running: false, port: null, hardware_confirmed: true });
  vi.spyOn(api, "conveyorPorts").mockResolvedValue({ ports: [] });
  const controller = camera(true);
  render(<ConveyorControls camera={controller} />);
  await userEvent.click(screen.getByText("ESP32 y banda", { exact: false }).closest("summary")!);
  const checkbox = screen.getByRole("checkbox", { name: /Mover la banda/ });
  expect(checkbox).toBeEnabled();
  await userEvent.click(checkbox);
  const update = vi.mocked(controller.setOptions).mock.calls[0][0] as (o: object) => { use_conveyor: boolean };
  expect(update(controller.options).use_conveyor).toBe(false);
});
