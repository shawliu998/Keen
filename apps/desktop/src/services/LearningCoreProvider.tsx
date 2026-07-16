import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { createLearningCoreClient, type DemoState, type LearningCoreClient } from "@keen/api-client";
import { discoverSidecar, isDesktopRuntime, restartSidecar } from "./sidecarRuntime";

export type LearningCoreStatus =
  | "demo"
  | "starting"
  | "binding"
  | "migrating"
  | "recovering"
  | "starting_server"
  | "health_checking"
  | "restarting"
  | "healthy"
  | "unavailable"
  | "configuration_error"
  | "error";

export type LearningCoreErrorKind = "connection" | "health";

type RetryFailure = {
  message: string;
  connectionUpdatedAt: number;
};

export function isLearningCoreStarting(status: LearningCoreStatus): boolean {
  return status === "starting"
    || status === "binding"
    || status === "migrating"
    || status === "recovering"
    || status === "starting_server"
    || status === "health_checking"
    || status === "restarting";
}

type LearningCoreContextValue = {
  status: LearningCoreStatus;
  errorKind: LearningCoreErrorKind | null;
  serviceMessage: string | null;
  retryError: string | null;
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
const MAX_SERVICE_MESSAGE_LENGTH = 500;
const RETRY_FAILURE_MESSAGE = "Keen could not confirm the requested learning-core recovery. No replacement service was assumed to be running. The supervised status was refreshed; retry after resolving the current error.";
let nextConnectionGeneration = 0;

function toError(error: unknown): Error | null {
  if (error === null || error === undefined) return null;
  return error instanceof Error ? error : new Error("Unknown learning-core error");
}

function toSafeServiceMessage(message: string | null | undefined): string | null {
  if (!message) return null;
  const normalized = Array.from(message, (character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint < 32 || codePoint === 127 ? " " : character;
  })
    .join("")
    .replace(/\s+/gu, " ")
    .trim();
  return normalized ? normalized.slice(0, MAX_SERVICE_MESSAGE_LENGTH) : null;
}

export function LearningCoreProvider({ children }: { children: ReactNode }) {
  const desktop = isDesktopRuntime();
  const retryInFlight = useRef<Promise<void> | null>(null);
  const [retryFailure, setRetryFailure] = useState<RetryFailure | null>(null);
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

  const status: LearningCoreStatus = (() => {
    if (!desktop) return "demo";
    if (connectionQuery.isError) return "error";
    if (connectionQuery.isPending) return "starting";
    const connection = connectionQuery.data;
    if (connection.status === "configuration_error") return "configuration_error";
    if (connection.status === "restarting") return "restarting";
    if (connection.status === "starting") return connection.phase ?? "starting";
    if (connection.status === "stopped" || connection.status === "unavailable" || !connection.available) return "unavailable";
    if (healthQuery.isError) return "error";
    if (healthQuery.isSuccess) return "healthy";
    return "health_checking";
  })();
  const errorKind: LearningCoreErrorKind | null = connectionQuery.isError
    ? "connection"
    : connectionQuery.data?.status === "ready" && healthQuery.isError ? "health" : null;
  const serviceMessage = toSafeServiceMessage(connectionQuery.data?.message);
  const retryError = retryFailure?.connectionUpdatedAt === connectionQuery.dataUpdatedAt
    ? retryFailure.message
    : null;

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
    if (!desktop) return;
    if (retryInFlight.current) return retryInFlight.current;

    const operation = (async () => {
      setRetryFailure(null);
      try {
        const connectionStatus = connectionQuery.data?.status;
        if (connectionQuery.isError || connectionStatus === "starting" || connectionStatus === "restarting") {
          await connectionQuery.refetch();
          return;
        }
        if (connectionStatus === "configuration_error") {
          await restartSidecar("configuration_recovered");
          await connectionQuery.refetch();
          return;
        }
        if (connectionStatus === "unavailable" || connectionStatus === "stopped") {
          await restartSidecar("sidecar_unavailable");
          await connectionQuery.refetch();
          return;
        }
        if (connectionStatus === "ready" && !healthQuery.isSuccess) {
          await healthQuery.refetch();
          return;
        }
        if (connectionStatus === "ready") {
          await demoStateQuery.refetch();
          return;
        }
        await connectionQuery.refetch();
      } catch {
        let connectionUpdatedAt = connectionQuery.dataUpdatedAt;
        try {
          const refreshed = await connectionQuery.refetch();
          connectionUpdatedAt = refreshed.dataUpdatedAt;
        } catch {
          // Keep the recovery error bounded and resolved even if rediscovery transport also fails.
        }
        setRetryFailure({
          message: RETRY_FAILURE_MESSAGE,
          connectionUpdatedAt,
        });
      }
    })().finally(() => {
      retryInFlight.current = null;
    });
    retryInFlight.current = operation;
    return operation;
  }, [connectionQuery, demoStateQuery, desktop, healthQuery]);

  const value = useMemo<LearningCoreContextValue>(() => ({
    status,
    errorKind,
    serviceMessage,
    retryError,
    client,
    connectionGeneration,
    demoState: demoStateQuery.data,
    demoStatePending: status === "healthy" && demoStateQuery.isPending,
    demoStateError: toError(demoStateQuery.error),
    retry,
  }), [client, connectionGeneration, demoStateQuery.data, demoStateQuery.error, demoStateQuery.isPending, errorKind, retry, retryError, serviceMessage, status]);

  return <LearningCoreContext.Provider value={value}>{children}</LearningCoreContext.Provider>;
}

export function useLearningCore(): LearningCoreContextValue {
  const value = useContext(LearningCoreContext);
  if (!value) throw new Error("useLearningCore must be used inside LearningCoreProvider.");
  return value;
}
