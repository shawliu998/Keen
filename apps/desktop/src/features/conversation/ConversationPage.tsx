import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, BookOpenText, ChevronDown, Edit3, RefreshCw, Send, Square } from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import {
  LearningCoreResponseError,
  LearningCoreSchemaError,
  type AnswerCitation,
  type AnswerStreamEvent,
  type Conversation,
  type ConversationSourceScope,
  type DurableConversationMessage,
} from "@keen/api-client";
import { useAppStore } from "../../state/appStore";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { PdfCitationViewer } from "./PdfCitationViewer";
import { consumeConversationHandoff, peekConversationHandoff, type DurableConversationHandoff } from "./conversationHandoff";

type MessageStatus = "complete" | "streaming" | "error" | "stopped";
type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  question?: string;
  status: MessageStatus;
  citations: AnswerCitation[];
  warnings: string[];
  error: string | null;
  retryable: boolean;
  errorCode: string | null;
  grounded: boolean | null;
};

type ActiveRun = {
  controller: AbortController | null;
  assistantId: string;
  userId: string;
  question: string;
  conversationId: string;
  sourceScope: ConversationSourceScope;
  idempotencyKey: string;
  cancelIdempotencyKey: string;
  cancelRequested: boolean;
};

type LoadState = "idle" | "loading" | "ready" | "missing" | "error";

const demoMessages: Message[] = [
  { id: "demo-user-1", role: "user", text: "Why does multiplying by a matrix preserve an eigenvector's direction?", status: "complete", citations: [], warnings: [], error: null, retryable: false, errorCode: null, grounded: null },
  { id: "demo-assistant-1", role: "assistant", text: "An eigenvector identifies a direction that a matrix does not rotate away from itself. The transformation can stretch that vector, shrink it, reverse it, or map it to zero, but the result remains on the same line.\n\nAlgebraically, Av = λv. The scalar λ changes magnitude and possibly orientation; it does not introduce a new direction. For example, λ = −2 reverses the vector and doubles its length, while the vector still belongs to the same one-dimensional span.\n\nThis is why direction preservation is the defining geometric idea behind eigenvectors.", question: "Why does multiplying by a matrix preserve an eigenvector's direction?", status: "complete", citations: [], warnings: [], error: null, retryable: false, errorCode: null, grounded: false },
];

function emptyMessage(id: string, role: Message["role"], text: string): Message {
  return { id, role, text, status: "complete", citations: [], warnings: [], error: null, retryable: false, errorCode: null, grounded: null };
}

function addWarning(warnings: string[], warning: string): string[] {
  return warnings.includes(warning) ? warnings : [...warnings, warning];
}

function questionTitle(messages: Message[], routeId: string | undefined): string {
  const question = messages.find((message) => message.role === "user")?.text;
  if (question) return question.length > 72 ? `${question.slice(0, 69).trimEnd()}…` : question;
  return routeId === "new" || routeId === undefined ? "New learning request" : "Learning question";
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function safeStreamFailure(error: unknown): { message: string; retryable: boolean } {
  if (error instanceof LearningCoreResponseError) return { message: error.detail?.message ?? `The learning core rejected this answer request (HTTP ${error.status}).`, retryable: error.detail?.retryable ?? false };
  if (error instanceof LearningCoreSchemaError) return { message: "The answer stream did not match Keen's authenticated event contract. Keen could not accept a completed answer; the saved message was checked before this state was shown.", retryable: true };
  return { message: "The local answer stream disconnected before completion. Keen could not confirm a terminal saved result. Retry after the learning core is healthy.", retryable: true };
}

function storedDraft(routeKey: string): string {
  return (routeKey === "new" ? sessionStorage.getItem("keen-new-message") : null) ?? localStorage.getItem(`keen-conversation-draft:${routeKey}`) ?? "";
}

function durableMessageView(message: DurableConversationMessage, question?: string): Message {
  if (message.role === "user") return emptyMessage(message.id, "user", message.content);
  const terminalError = message.status === "failed"
    ? message.errorDetail ?? "The saved answer failed before completion."
    : message.status === "cancelled"
      ? "The saved answer was cancelled. Its partial text was not recorded as complete."
      : message.status === "interrupted"
        ? "The learning core restarted before this saved answer completed. You can retry the question."
        : null;
  return {
    id: message.id,
    role: "assistant",
    text: message.content,
    question,
    status: message.status === "completed" ? "complete" : message.status === "pending" || message.status === "streaming" ? "streaming" : message.status === "failed" ? "error" : "stopped",
    citations: message.status === "completed" ? message.citations : [],
    warnings: message.status === "completed" && message.citations.length === 0
      ? ["There was not enough source support for this answer."]
      : [],
    error: terminalError,
    retryable: message.status === "failed" || message.status === "cancelled" || message.status === "interrupted",
    errorCode: message.errorCode,
    grounded: message.status === "completed" ? message.citations.length > 0 : message.status === "failed" ? false : null,
  };
}

function durableTranscript(messages: DurableConversationMessage[]): Message[] {
  const users = new Map(messages.filter((message) => message.role === "user").map((message) => [message.id, message.content]));
  return messages.map((message) => durableMessageView(message, message.replyToMessageId ? users.get(message.replyToMessageId) : undefined));
}

function terminalStatus(status: DurableConversationMessage["status"]): boolean {
  return ["completed", "failed", "cancelled", "interrupted"].includes(status);
}

function waitForPoll(signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(resolve, 120);
    signal?.addEventListener("abort", () => { window.clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
  });
}

export function ConversationPage() {
  const { id: routeId } = useParams();
  const navigate = useNavigate();
  const { status, client, connectionGeneration, demoState, demoStatePending, demoStateError, retry: retryLearningCore } = useLearningCore();
  const demo = status === "demo";
  const demoTranscript = demo && Boolean(routeId && routeId !== "new");
  const routeKey = routeId ?? "new";
  const viewKey = `${routeKey}:${demo}:${demoTranscript}`;
  const draftKey = `keen-conversation-draft:${routeKey}`;
  const [messages, setMessages] = useState<Message[]>(demoTranscript ? demoMessages : []);
  const [draftState, setDraftState] = useState(() => ({ routeKey, text: storedDraft(routeKey) }));
  const [renderedViewKey, setRenderedViewKey] = useState(viewKey);
  const [courseId, setCourseId] = useState<string | null>(null);
  const [scopeLabelOverride, setScopeLabelOverride] = useState<string | null>(null);
  const [conversation, setConversation] = useState<Conversation | null>(null);
  const [loadState, setLoadState] = useState<LoadState>(routeKey === "new" || demo ? "ready" : "idle");
  const [transcriptLoadAttempt, setTranscriptLoadAttempt] = useState(0);
  const [pageNotice, setPageNotice] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<{ routeId: string | undefined; citation: AnswerCitation } | null>(null);
  const [activeAssistantId, setActiveAssistantId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [unknownRun, setUnknownRun] = useState<ActiveRun | null>(null);
  const activeRun = useRef<ActiveRun | null>(null);
  const adoptedConversationId = useRef<string | null>(null);
  const previousViewKey = useRef(viewKey);
  const previousRouteKey = useRef(routeKey);
  const previousGeneration = useRef(connectionGeneration);
  const activeRouteKey = useRef(routeKey);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const transcriptRef = useRef<HTMLElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const messageRefs = useRef(new Map<string, HTMLElement>());
  const { setInspector } = useAppStore();

  const clearSelectedCitation = useCallback(() => { setSelectedCitation(null); setInspector(null); }, [setInspector]);
  const focusMessage = useCallback((messageId: string) => { window.setTimeout(() => messageRefs.current.get(messageId)?.focus({ preventScroll: true }), 0); }, []);
  const viewStateIsCurrent = renderedViewKey === viewKey;
  const visibleMessages = viewStateIsCurrent ? messages : demoTranscript ? demoMessages : [];
  const visibleDraft = viewStateIsCurrent && draftState.routeKey === routeKey ? draftState.text : "";
  const visibleCourseId = viewStateIsCurrent ? courseId : null;
  const visibleActiveAssistantId = viewStateIsCurrent ? activeAssistantId : null;
  const visiblePageNotice = viewStateIsCurrent ? pageNotice : null;
  const draft = visibleDraft;
  const setDraft = useCallback((text: string) => setDraftState({ routeKey, text }), [routeKey]);

  useEffect(() => {
    if (draftState.routeKey === routeKey) localStorage.setItem(draftKey, draftState.text);
  }, [draftKey, draftState, routeKey]);

  useEffect(() => {
    if (previousViewKey.current === viewKey) return;
    const run = activeRun.current;
    const adoptingCreatedRoute = previousRouteKey.current === "new" && adoptedConversationId.current === routeKey;
    activeRouteKey.current = routeKey;
    if (!adoptingCreatedRoute) {
      run?.controller?.abort();
      activeRun.current = null;
      setActiveAssistantId(null);
      setMessages(demoTranscript ? demoMessages : []);
      setConversation(null);
      setCourseId(null);
      setScopeLabelOverride(null);
      setPageNotice(null);
      setUnknownRun(null);
      setLoadState(routeKey === "new" || demo ? "ready" : "idle");
      setDraftState({ routeKey, text: storedDraft(routeKey) });
    } else {
      adoptedConversationId.current = null;
      setDraftState({ routeKey, text: "" });
      localStorage.removeItem("keen-conversation-draft:new");
      setLoadState("ready");
    }
    setSelectedCitation(null);
    setInspector(null);
    if (routeKey === "new") sessionStorage.removeItem("keen-new-message");
    previousViewKey.current = viewKey;
    previousRouteKey.current = routeKey;
    setRenderedViewKey(viewKey);
  }, [demo, demoTranscript, routeKey, setInspector, viewKey]);

  useEffect(() => { if (routeKey === "new") sessionStorage.removeItem("keen-new-message"); }, [routeKey]);
  useEffect(() => () => setInspector(null), [setInspector]);
  const updateAssistant = useCallback((id: string, update: (message: Message) => Message) => { setMessages((current) => current.map((message) => message.id === id ? update(message) : message)); }, []);

  useEffect(() => {
    if (demo || routeKey === "new" || status !== "healthy" || !client) return;
    if (peekConversationHandoff(routeKey)) return;
    if (activeRun.current?.conversationId === routeKey && activeRun.current.controller !== null) return;
    const controller = new AbortController();
    setLoadState("loading");
    void Promise.all([
      client.getConversation(routeKey, { signal: controller.signal }),
      client.listConversationMessages(routeKey, { signal: controller.signal }),
    ]).then(([savedConversation, transcript]) => {
      if (controller.signal.aborted || activeRouteKey.current !== routeKey) return;
      setConversation(savedConversation);
      setCourseId(savedConversation.courseId);
      setMessages(durableTranscript(transcript.messages));
      const pending = [...transcript.messages].reverse().find((message) => message.role === "assistant" && !terminalStatus(message.status));
      if (pending) {
        const question = transcript.messages.find((message) => message.id === pending.replyToMessageId)?.content ?? "";
        activeRun.current = { controller: null, assistantId: pending.id, userId: pending.replyToMessageId ?? "", question, conversationId: routeKey, sourceScope: pending.sourceScope, idempotencyKey: crypto.randomUUID(), cancelIdempotencyKey: crypto.randomUUID(), cancelRequested: false };
        setActiveAssistantId(pending.id);
        void (async () => {
          let latest = pending;
          for (let attempt = 0; attempt < 3 && !controller.signal.aborted; attempt += 1) {
            if (attempt > 0) await waitForPoll(controller.signal);
            latest = await client.getConversationMessage(routeKey, pending.id, { signal: controller.signal });
            if (terminalStatus(latest.status)) {
              if (activeRouteKey.current !== routeKey) return;
              setMessages((current) => current.map((message) => message.id === latest.id
                ? durableMessageView(latest, question)
                : message));
              activeRun.current = null;
              setActiveAssistantId(null);
              setPageNotice(null);
              focusMessage(latest.id);
              return;
            }
          }
          if (!controller.signal.aborted && activeRouteKey.current === routeKey) {
            setPageNotice("The saved answer is still recovering. You can cancel it, or return later to check its authoritative state.");
          }
        })().catch((error: unknown) => {
          if (isAbortError(error) || controller.signal.aborted || activeRouteKey.current !== routeKey) return;
          setPageNotice("Keen could not finish checking the saved answer. Reload this conversation to reconcile its authoritative state.");
        });
      } else {
        activeRun.current = null;
        setActiveAssistantId(null);
      }
      setLoadState("ready");
    }).catch((error: unknown) => {
      if (isAbortError(error) || controller.signal.aborted || activeRouteKey.current !== routeKey) return;
      setLoadState(error instanceof LearningCoreResponseError && error.status === 404 ? "missing" : "error");
      setMessages([]);
    });
    return () => controller.abort();
  }, [client, connectionGeneration, demo, focusMessage, routeKey, status, transcriptLoadAttempt]);

  useEffect(() => {
    if (previousGeneration.current !== connectionGeneration && activeRun.current?.controller) {
      activeRun.current.controller.abort();
      activeRun.current.controller = null;
      updateAssistant(activeRun.current.assistantId, (message) => ({ ...message, citations: [] }));
      setPageNotice("The learning core restarted while this answer was active. Keen is reloading the saved message before allowing another request.");
      clearSelectedCitation();
    }
    previousGeneration.current = connectionGeneration;
  }, [clearSelectedCitation, connectionGeneration, updateAssistant]);

  useEffect(() => () => activeRun.current?.controller?.abort(), []);

  const applyEvent = useCallback((assistantId: string, event: AnswerStreamEvent) => {
    if (event.type === "error") clearSelectedCitation();
    updateAssistant(assistantId, (message) => {
      if (event.type === "delta") return { ...message, text: message.text + event.data.text };
      if (event.type === "retrieval") return { ...message, warnings: event.data.warning ? addWarning(message.warnings, event.data.warning) : message.warnings };
      if (event.type === "warning") return { ...message, warnings: addWarning(message.warnings, event.data.message) };
      if (event.type === "citation") return { ...message, citations: [...message.citations, event.data] };
      if (event.type === "done") return { ...message, status: "complete", grounded: event.data.grounded, warnings: !event.data.grounded && message.warnings.length === 0 ? addWarning(message.warnings, "There was not enough source support for this answer.") : message.warnings };
      if (event.type === "error") return { ...message, status: "error", citations: [], error: event.data.message, retryable: event.data.retryable, errorCode: event.data.code, grounded: false };
      return message;
    });
  }, [clearSelectedCitation, updateAssistant]);

  const reconcileRun = useCallback(async (run: ActiveRun, signal?: AbortSignal): Promise<DurableConversationMessage | null> => {
    if (!client) return null;
    let latest: DurableConversationMessage | null = null;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      latest = await client.getConversationMessage(run.conversationId, run.assistantId, { signal });
      if (terminalStatus(latest.status)) return latest;
      if (attempt < 2) await waitForPoll(signal);
    }
    return latest;
  }, [client]);

  const finishFromDurable = useCallback((run: ActiveRun, saved: DurableConversationMessage) => {
    if (saved.status !== "completed") clearSelectedCitation();
    updateAssistant(run.assistantId, () => durableMessageView(saved, run.question));
    if (terminalStatus(saved.status)) {
      if (activeRun.current?.assistantId === run.assistantId) activeRun.current = null;
      setActiveAssistantId((current) => current === run.assistantId ? null : current);
      setPageNotice(null);
      setUnknownRun(null);
    } else {
      activeRun.current = run;
      setActiveAssistantId(run.assistantId);
      setPageNotice("The stream ended before a terminal event, but the saved answer is still active. You can cancel it, or return later to reload its final state.");
    }
  }, [clearSelectedCitation, updateAssistant]);

  const streamAnswer = useCallback(async (run: ActiveRun) => {
    if (!client) return;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        for await (const event of client.streamConversationAnswer(run.conversationId, {
          question: run.question,
          idempotencyKey: run.idempotencyKey,
          userMessageId: run.userId,
          assistantMessageId: run.assistantId,
          sourceScope: run.sourceScope,
          retrievalLimit: 8,
        }, { signal: run.controller?.signal })) {
          if (activeRouteKey.current !== run.conversationId) break;
          applyEvent(run.assistantId, event);
        }
        break;
      } catch (error) {
        if (run.cancelRequested || activeRouteKey.current !== run.conversationId) break;
        run.controller = null;
        try {
          const saved = await reconcileRun(run);
          if (saved) finishFromDurable(run, saved);
          break;
        } catch (reconcileError) {
          const messageNotVisible = reconcileError instanceof LearningCoreResponseError && reconcileError.status === 404;
          if (messageNotVisible && attempt < 2) {
            await waitForPoll();
            run.controller = new AbortController();
            activeRun.current = run;
            updateAssistant(run.assistantId, (message) => ({ ...message, text: "", citations: [], warnings: [], error: null, status: "streaming" }));
            continue;
          }
          const failure = safeStreamFailure(isAbortError(error) ? reconcileError : error);
          updateAssistant(run.assistantId, (message) => ({ ...message, status: "error", citations: [], error: failure.message, retryable: false, errorCode: "stream_status_unknown" }));
          clearSelectedCitation();
          setPageNotice("Keen could not confirm the saved answer status. Reload this conversation after the learning core is healthy before retrying.");
          setUnknownRun(run);
          activeRun.current = null;
          setActiveAssistantId(null);
          break;
        }
      }
    }
    {
      if (!run.cancelRequested && activeRun.current?.assistantId === run.assistantId && activeRun.current.controller !== null) {
        activeRun.current = null;
        setActiveAssistantId(null);
      }
      if (activeRouteKey.current === run.conversationId) {
        const transcript = transcriptRef.current;
        if (transcript && transcript.scrollHeight > transcript.clientHeight + 8 && typeof bottomRef.current?.scrollIntoView === "function") {
          const reducedMotion = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
          bottomRef.current.scrollIntoView({ behavior: reducedMotion ? "auto" : "smooth" });
        }
        focusMessage(run.assistantId);
      }
    }
  }, [applyEvent, clearSelectedCitation, client, finishFromDurable, focusMessage, reconcileRun, updateAssistant]);

  const sendQuestion = useCallback(async (rawQuestion: string, prepared?: DurableConversationHandoff) => {
    const question = rawQuestion.trim();
    if (!question || activeRun.current || creating) return;
    setPageNotice(null);
    if (demo) {
      setDraft("");
      setMessages((current) => [...current, emptyMessage(crypto.randomUUID(), "user", question)]);
      setPageNotice("Note added to this sample. No answer request was sent.");
      textareaRef.current?.focus();
      return;
    }
    if (!client || status !== "healthy") {
      setPageNotice("The learning core is not ready, so no answer request was sent. Recover the service and retry.");
      return;
    }
    const sourceScope: ConversationSourceScope = prepared?.sourceScope ?? (routeKey !== "new" && conversation
      ? conversation.sourceScope
      : courseId ? { kind: "course", courseId } : { kind: "all_indexed" });
    let conversationId = prepared?.conversationId ?? routeKey;
    if (routeKey === "new") {
      conversationId = crypto.randomUUID();
      setCreating(true);
      try {
        const created = await client.createConversation({ id: conversationId, question, sourceScope });
        setConversation(created.conversation);
        setCourseId(created.conversation.courseId);
      } catch (error) {
        try {
          const saved = await client.getConversation(conversationId);
          setConversation(saved);
          setCourseId(saved.courseId);
        } catch {
          const failure = safeStreamFailure(error);
          setPageNotice(`${failure.message} No saved conversation route was adopted.`);
          setCreating(false);
          return;
        }
      }
      setCreating(false);
    }
    const userId = prepared?.userMessageId ?? crypto.randomUUID();
    const assistantId = prepared?.assistantMessageId ?? crypto.randomUUID();
    const controller = new AbortController();
    const run: ActiveRun = { controller, assistantId, userId, question, conversationId, sourceScope, idempotencyKey: prepared?.idempotencyKey ?? crypto.randomUUID(), cancelIdempotencyKey: prepared?.cancelIdempotencyKey ?? crypto.randomUUID(), cancelRequested: false };
    setDraft("");
    setMessages((current) => [...current, emptyMessage(userId, "user", question), { ...emptyMessage(assistantId, "assistant", ""), question, status: "streaming" }]);
    activeRun.current = run;
    activeRouteKey.current = conversationId;
    setActiveAssistantId(assistantId);
    if (routeKey === "new") {
      adoptedConversationId.current = conversationId;
      navigate(`/conversation/${encodeURIComponent(conversationId)}`, { replace: true });
    }
    void streamAnswer(run);
  }, [client, conversation, courseId, creating, demo, navigate, routeKey, setDraft, status, streamAnswer]);

  useEffect(() => {
    if (demo || routeKey === "new" || status !== "healthy" || !client || !peekConversationHandoff(routeKey)) return;
    // Delay consumption until after React StrictMode's first effect cleanup. The discarded
    // effect clears this timer, leaving the handoff for the committed mount to consume once.
    const timer = window.setTimeout(() => {
      const handoff = consumeConversationHandoff(routeKey);
      if (!handoff || activeRouteKey.current !== routeKey || activeRun.current) return;
      setConversation(handoff.conversation);
      setScopeLabelOverride(handoff.scopeLabel);
      setCourseId(handoff.sourceScope.kind === "course" ? handoff.sourceScope.courseId : null);
      setLoadState("ready");
      void sendQuestion(handoff.question, handoff);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [client, demo, routeKey, sendQuestion, status]);

  const stopGeneration = useCallback(async () => {
    const run = activeRun.current;
    if (!run || !client || run.cancelRequested) return;
    run.cancelRequested = true;
    setPageNotice("Confirming cancellation with the learning core…");
    try {
      const response = await client.cancelConversationAnswer(run.conversationId, run.assistantId, { idempotencyKey: run.cancelIdempotencyKey });
      run.controller?.abort();
      run.controller = null;
      finishFromDurable(run, response.message);
    } catch {
      try {
        const saved = await reconcileRun(run);
        if (saved && terminalStatus(saved.status)) {
          run.controller?.abort();
          run.controller = null;
          finishFromDurable(run, saved);
        } else {
          run.cancelRequested = false;
          activeRun.current = run;
          setActiveAssistantId(run.assistantId);
          setPageNotice("Cancellation was not applied yet. The saved answer is still active; retry Cancel or return later to reload its state.");
        }
      } catch {
        run.cancelRequested = false;
        activeRun.current = run;
        setActiveAssistantId(run.assistantId);
        setPageNotice("Cancellation could not be confirmed. The saved answer may still be active; retry Cancel or return later to reload its state.");
      }
    }
    clearSelectedCitation();
    focusMessage(run.assistantId);
  }, [clearSelectedCitation, client, finishFromDurable, focusMessage, reconcileRun]);

  const reloadUnknownOutcome = useCallback(async () => {
    const run = unknownRun;
    if (!run || !client) return;
    setPageNotice("Checking the saved answer…");
    try {
      const saved = await reconcileRun(run);
      if (saved) {
        finishFromDurable(run, saved);
        if (!terminalStatus(saved.status)) {
          setUnknownRun(run);
          setPageNotice("The saved answer is still active. Check again before starting another answer.");
        }
      }
    } catch (error) {
      if (error instanceof LearningCoreResponseError && error.status === 404) {
        run.controller = new AbortController();
        run.cancelRequested = false;
        activeRun.current = run;
        setUnknownRun(null);
        setActiveAssistantId(run.assistantId);
        updateAssistant(run.assistantId, (message) => ({ ...message, status: "streaming", text: "", citations: [], warnings: [], error: null, retryable: false, errorCode: null }));
        void streamAnswer(run);
        return;
      }
      setUnknownRun(run);
      setPageNotice("Keen still could not confirm the saved answer. Check again after the learning core recovers.");
    }
  }, [client, finishFromDurable, reconcileRun, streamAnswer, unknownRun, updateAssistant]);

  const serviceUnavailable = !demo && status !== "healthy";
  const scopeLoading = !demo && status === "healthy" && (demoStatePending || (routeKey !== "new" && loadState !== "ready" && loadState !== "missing" && loadState !== "error"));
  const scopeError = !demo && status === "healthy" && (demoStateError !== null || loadState === "error" || loadState === "missing");
  const courses = demoState?.courses ?? [];
  const hasCourseScope = !demo && courses.length > 0;
  const savedRouteReady = routeKey === "new" || loadState === "ready";
  const composerBlocked = serviceUnavailable || scopeLoading || scopeError || creating || unknownRun !== null || !savedRouteReady || (!demo && !hasCourseScope) || conversation?.status === "archived";
  const selectedCourse = courses.find((course) => course.id === visibleCourseId) ?? null;
  const savedCourseContext = routeKey !== "new" && hasCourseScope;
  const visibleCitation = selectedCitation && selectedCitation.routeId === routeId ? selectedCitation.citation : null;
  const title = demoTranscript ? "Why eigenvectors keep their direction" : conversation?.title ?? questionTitle(visibleMessages, routeId);
  const emptyTitle = loadState === "missing" ? "Conversation not found" : loadState === "error" ? "Conversation could not be loaded" : scopeError ? "Source scopes could not be loaded" : demo ? "Start with a learning question" : hasCourseScope ? "Ask from your learning materials" : "Select a source scope first";
  const emptyBody = loadState === "missing" ? "This saved conversation does not exist. No replacement transcript was invented." : loadState === "error" ? "The saved transcript could not be read. Retry after recovering the learning core." : scopeError ? "The learning service is available, but the current saved state could not be read. Recover the service before asking." : demo ? "Your draft stays in this browser preview; submitting it will not generate an answer." : hasCourseScope ? "Choose a course above, then ask one focused question." : "Add or organize course sources in Knowledge Base before asking a grounded question.";

  const openCitation = (citation: AnswerCitation) => { setInspector(null); setSelectedCitation({ routeId, citation }); };
  return <div className="conversation-page">
    {visibleCitation && <PdfCitationViewer key={`${visibleCitation.citationId}:${connectionGeneration}`} citation={visibleCitation} client={client} onClose={clearSelectedCitation} />}
    <div className="conversation-heading"><div className="conversation-title-row"><h1>{title}</h1></div><div className="conversation-context"><p aria-label={savedCourseContext ? "Conversation course scope" : undefined}>{demoTranscript ? "Eigenvectors" : demo ? "Draft a question for a course or source scope" : selectedCourse ? selectedCourse.title : scopeLabelOverride ?? (hasCourseScope ? "All indexed courses" : "Choose sources before asking a grounded question")}</p>
      {hasCourseScope && routeKey === "new" ? <label className="conversation-course"><span>Course scope</span><span className="conversation-course-control"><select aria-label="Conversation course scope" value={visibleCourseId ?? ""} onChange={(event) => setCourseId(event.target.value || null)} disabled={visibleActiveAssistantId !== null}><option value="">All indexed courses</option>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select><ChevronDown size={14} aria-hidden="true" /></span></label> : null}
    </div></div>
    <section ref={transcriptRef} className="messages" aria-label="Conversation transcript">
      {!visibleMessages.length && scopeLoading ? <div className="conversation-skeleton" role="status" aria-label={routeKey === "new" ? "Loading source scopes" : "Loading conversation"}><span /><span /><span /></div> : null}
      {!visibleMessages.length && !scopeLoading && <div className="conversation-empty"><strong>{emptyTitle}</strong><p>{emptyBody}</p>{loadState === "error" ? <button type="button" onClick={() => setTranscriptLoadAttempt((attempt) => attempt + 1)}>Retry transcript</button> : scopeError ? <button type="button" onClick={() => void retryLearningCore()}>Recover learning core</button> : !hasCourseScope ? <Link to="/knowledge">Open Knowledge Base</Link> : null}</div>}
      {visibleMessages.map((message) => {
        const showRetry = !demo && Boolean(message.question) && message.retryable;
        const showAskAgain = !demo && Boolean(message.question) && message.status === "complete";
        const showReuse = Boolean(message.question) && message.errorCode !== "stream_status_unknown";
        return <article className={`message ${message.role}`} key={message.id} aria-busy={message.status === "streaming"} tabIndex={-1} ref={(node) => { if (node) messageRefs.current.set(message.id, node); else messageRefs.current.delete(message.id); }}><div className="message-body">
          <div className="message-meta"><strong>{message.role === "assistant" ? demoTranscript ? "Sample answer" : "Answer" : "Question"}</strong>{message.status === "streaming" && <span role="status">Answer in progress</span>}</div>
          {message.text ? <p>{message.text}</p> : message.status === "streaming" ? <p className="stream-placeholder">Preparing the answer…</p> : null}
          {message.warnings.map((warning) => <div className="conversation-warning" key={warning}><AlertTriangle size={13} />{warning}</div>)}
          {message.error && <div className={`conversation-run-state ${message.status}`} role="alert"><AlertTriangle size={14} /><span>{message.error}</span></div>}
          {message.errorCode === "provider_missing" && <Link className="conversation-recovery-link" to="/settings?section=capabilities">Open provider settings</Link>}
          {message.citations.length > 0 && <div className="message-sources"><span>Sources</span><div>{message.citations.map((citation) => <button className="citation" key={citation.citationId} aria-label={`${citation.documentName} · p. ${citation.pageNumber}`} onClick={() => openCitation(citation)}><BookOpenText size={13} /><span>{citation.documentName}</span><small>p. {citation.pageNumber}</small></button>)}</div></div>}
          {message.role === "assistant" && message.status !== "streaming" && (showRetry || showAskAgain || showReuse) && <div className="message-actions">{showRetry && <button aria-label="Retry answer" onClick={() => message.question && void sendQuestion(message.question)}><RefreshCw size={13} />Retry</button>}{showAskAgain && <button aria-label="Ask again" onClick={() => message.question && void sendQuestion(message.question)}><RefreshCw size={13} />Ask again</button>}{showReuse && <button aria-label="Reuse question" onClick={() => { if (message.question) { setDraft(message.question); textareaRef.current?.focus(); } }}><Edit3 size={13} />Reuse question</button>}</div>}
        </div></article>;
      })}<div ref={bottomRef} />
    </section>
    <div className="conversation-composer">{visiblePageNotice && <div className="conversation-notice" role="status"><span>{visiblePageNotice}</span>{unknownRun ? <button type="button" onClick={() => void reloadUnknownOutcome()}>Reload saved answer</button> : null}</div>}{serviceUnavailable && <div className="conversation-service-state" role="alert"><span>{isLearningCoreStarting(status) ? "The learning core is starting; no request can be sent yet." : "The learning core is unavailable; no request will be sent."}</span>{!isLearningCoreStarting(status) && <button onClick={() => void retryLearningCore()}>Recover learning core</button>}</div>}
      <div className="composer card"><textarea ref={textareaRef} aria-label="Reply" value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); void sendQuestion(draft); } }} placeholder={demoTranscript ? "Add a note to this sample…" : demo ? "Enter a learning question…" : "Ask your indexed learning materials…"} disabled={visibleActiveAssistantId !== null || composerBlocked} /><div className="composer-bottom"><span className="draft-state">{demo ? "Draft saved in this browser" : "Draft saved on this Mac"}</span><button className="send-button conversation-submit" aria-label={visibleActiveAssistantId ? "Cancel answer" : demoTranscript ? "Add note" : demo ? "Add question" : "Ask question"} onClick={visibleActiveAssistantId ? () => void stopGeneration() : () => void sendQuestion(draft)} disabled={!visibleActiveAssistantId && (!draft.trim() || composerBlocked)}>{visibleActiveAssistantId ? <Square size={13} /> : <Send size={14} />}<span>{visibleActiveAssistantId ? "Cancel" : demoTranscript ? "Add note" : creating ? "Saving…" : "Ask"}</span></button></div></div>
    </div>
  </div>;
}
