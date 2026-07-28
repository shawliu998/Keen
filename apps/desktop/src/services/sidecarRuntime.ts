import { invoke, isTauri } from "@tauri-apps/api/core";
import { sidecarConnectionSchema, type SidecarConnection } from "@keen/api-client";

export type SidecarRestartReason = "sidecar_unavailable" | "configuration_recovered" | "health_check_failed";

export function isDesktopRuntime(): boolean {
  return isTauri();
}

export async function discoverSidecar(signal?: AbortSignal): Promise<SidecarConnection> {
  signal?.throwIfAborted();
  const value: unknown = await invoke("get_sidecar_connection");
  signal?.throwIfAborted();
  return sidecarConnectionSchema.parse(value);
}

export async function restartSidecar(reason?: SidecarRestartReason): Promise<SidecarConnection> {
  const value: unknown = await invoke("restart_sidecar", reason ? { reason } : {});
  return sidecarConnectionSchema.parse(value);
}
