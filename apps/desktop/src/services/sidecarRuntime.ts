import { invoke, isTauri } from "@tauri-apps/api/core";
import { sidecarConnectionSchema, type SidecarConnection } from "@keen/api-client";

export function isDesktopRuntime(): boolean {
  return isTauri();
}

export async function discoverSidecar(signal?: AbortSignal): Promise<SidecarConnection> {
  signal?.throwIfAborted();
  const value: unknown = await invoke("get_sidecar_connection");
  signal?.throwIfAborted();
  return sidecarConnectionSchema.parse(value);
}
