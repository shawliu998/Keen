import { useEffect, useRef, useState } from "react";
import {
  LearningCoreResponseError,
  type AutonomousStudySession,
  type LearningCoreClient,
} from "@keen/api-client";
import { Pause, Play } from "lucide-react";
import { Button } from "@keen/ui";

type SessionCommand = "pause" | "resume";

type PendingIntent = {
  command: SessionCommand;
  expectedRevision: number;
  idempotencyKey: string;
};

type Props = {
  client: LearningCoreClient;
  sessionId: string;
  courseId: string;
  session: AutonomousStudySession;
  onSessionChanged: () => void;
};

function createIntent(command: SessionCommand, expectedRevision: number): PendingIntent {
  return {
    command,
    expectedRevision,
    idempotencyKey: `study-session-${command}-${crypto.randomUUID()}`,
  };
}

export function SessionPauseControl({ client, sessionId, courseId, session, onSessionChanged }: Props) {
  const command: SessionCommand = session.status === "paused" ? "resume" : "pause";
  const [intent, setIntent] = useState<PendingIntent | null>(null);
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const apply = async () => {
    if (pending) return;
    const nextIntent = intent?.command === command && intent.expectedRevision === session.revision
      ? intent
      : createIntent(command, session.revision);
    setIntent(nextIntent);
    setPending(true);
    setNotice(null);
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const request = {
        course_id: courseId,
        expected_revision: nextIntent.expectedRevision,
        idempotency_key: nextIntent.idempotencyKey,
      };
      if (command === "pause") {
        await client.pauseStudySession(sessionId, request, { signal: controller.signal });
      } else {
        await client.resumeStudySession(sessionId, request, { signal: controller.signal });
      }
      setIntent(null);
      setNotice(command === "pause" ? "Session paused." : "Session resumed.");
      onSessionChanged();
    } catch (error) {
      if (error instanceof LearningCoreResponseError && error.status === 409) {
        setIntent(null);
        setNotice("The session changed. Its current state is being restored.");
        onSessionChanged();
      } else if (error instanceof LearningCoreResponseError && error.status >= 400 && error.status < 500) {
        setIntent(null);
        setNotice(error.detail?.message ?? "This session action is no longer available.");
      } else if (!(error instanceof Error && error.name === "AbortError")) {
        setNotice(`Keen could not confirm the ${command}. Use the same action to retry safely.`);
      }
    } finally {
      if (controllerRef.current === controller) controllerRef.current = null;
      setPending(false);
    }
  };

  const label = command === "pause" ? "Pause" : "Resume";
  return <div className="session-pause-control">
    <Button
      type="button"
      size="small"
      variant={command === "resume" ? "primary" : "secondary"}
      loading={pending}
      loadingLabel={`${label} session`}
      onClick={() => { void apply(); }}
    >
      {command === "pause" ? <Pause size={13} aria-hidden="true" /> : <Play size={13} aria-hidden="true" />}
      {label}
    </Button>
    {notice ? <span role="status">{notice}</span> : null}
  </div>;
}
