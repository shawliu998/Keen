import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { createLearningCoreClient, type DemoState, type LearningCoreClient } from "@keen/api-client";
import { discoverSidecar, isDesktopRuntime } from "./sidecarRuntime";

export type LearningCoreStatus = "demo" | "starting" | "healthy" | "unavailable" | "error";

type LearningCoreContextValue = {
  status: LearningCoreStatus;
  client: LearningCoreClient | null;
  connectionGeneration: number;
  demoState: DemoState | undefined;
  demoStatePending: boolean;
  demoStateError: Error | null;
  retry: () => Promise<void>;
};

const LearningCoreContext = createContext<LearningCoreContextValue | null>(null);
const SIDECAR_DISCOVERY_INTERVAL_MS = 2_000;
const SIDECAR_HEALTH_INTERVAL_MS = 5_000;
let nextConnectionGeneration = 0;

function toError(error: unknown): Error | null {
  if (error === null || error === undefined) return null;
  return error instanceof Error ? error : new Error("Unknown learning-core error");
}

export function LearningCoreProvider({ children }: { children: ReactNode }) {
  const desktop = isDesktopRuntime();
  const connectionQuery = useQuery({
    queryKey: ["learning-core", "connection"],
    queryFn: ({ signal }) => discoverSidecar(signal),
    enabled: desktop,
    retry: false,
    staleTime: 0,
    refetchOnWindowFocus: false,
    // A restart always rotates the token and may reuse the same port. Keep discovering after
    // the first healthy connection so the UI cannot remain pinned to stale credentials.
    refetchInterval: desktop ? SIDECAR_DISCOVERY_INTERVAL_MS : false,
  });

  const activePort = connectionQuery.data?.available ? connectionQuery.data.port : null;
  const activeToken = connectionQuery.data?.available ? connectionQuery.data.token : null;
  const connectionGeneration = useMemo(
    () => activePort === null || activeToken === null ? 0 : ++nextConnectionGeneration,
    [activePort, activeToken],
  );

  const client = useMemo(() => {
    const connection = connectionQuery.data;
    if (!connection?.available || connection.port === null || connection.token === null) return null;
    return createLearningCoreClient(`http://127.0.0.1:${connection.port}`, connection.token);
  }, [connectionQuery.data]);

  const port = connectionQuery.data?.port ?? "none";
  const healthQuery = useQuery({
    queryKey: ["learning-core", "health", port, connectionGeneration],
    queryFn: ({ signal }) => {
      if (!client) throw new Error("Learning core connection is not available.");
      return client.health({ signal });
    },
    enabled: desktop && client !== null,
    retry: 1,
    staleTime: 5_000,
    refetchOnWindowFocus: false,
    refetchInterval: desktop ? SIDECAR_HEALTH_INTERVAL_MS : false,
  });

  const status: LearningCoreStatus = !desktop
    ? "demo"
    : connectionQuery.isError
      ? "error"
      : connectionQuery.isPending
        ? "starting"
        : connectionQuery.data.status === "starting" || connectionQuery.data.status === "restarting"
          ? "starting"
        : !connectionQuery.data.available
          ? "unavailable"
          : healthQuery.isError
            ? "error"
            : healthQuery.isSuccess
              ? "healthy"
              : "starting";

  const demoStateQuery = useQuery({
    queryKey: ["learning-core", "demo-state", port, connectionGeneration],
    queryFn: ({ signal }) => {
      if (!client) throw new Error("Learning core connection is not available.");
      return client.demoState({ signal });
    },
    enabled: status === "healthy" && client !== null,
    retry: 1,
    staleTime: 10_000,
    refetchOnWindowFocus: false,
  });

  const retry = useCallback(async () => {
    if (!desktop || connectionQuery.isFetching || healthQuery.isFetching || demoStateQuery.isFetching) return;
    if (!connectionQuery.data?.available) {
      await connectionQuery.refetch();
      return;
    }
    if (!healthQuery.isSuccess) {
      await healthQuery.refetch();
      return;
    }
    await demoStateQuery.refetch();
  }, [connectionQuery, demoStateQuery, desktop, healthQuery]);

  const value = useMemo<LearningCoreContextValue>(() => ({
    status,
    client,
    connectionGeneration,
    demoState: demoStateQuery.data,
    demoStatePending: status === "healthy" && demoStateQuery.isPending,
    demoStateError: toError(demoStateQuery.error),
    retry,
  }), [client, connectionGeneration, demoStateQuery.data, demoStateQuery.error, demoStateQuery.isPending, retry, status]);

  return <LearningCoreContext.Provider value={value}>{children}</LearningCoreContext.Provider>;
}

export function useLearningCore(): LearningCoreContextValue {
  const value = useContext(LearningCoreContext);
  if (!value) throw new Error("useLearningCore must be used inside LearningCoreProvider.");
  return value;
}
