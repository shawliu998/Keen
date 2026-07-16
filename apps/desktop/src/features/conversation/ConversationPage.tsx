import { useCallback, useEffect, useRef, useState } from "react";
import { BookOpenText, Copy, Edit3, GitBranch, Paperclip, RefreshCw, Send, Square } from "lucide-react";
import { useParams } from "react-router-dom";
import { Badge, Card, IconButton } from "@keen/ui";
import {
  LearningCoreResponseError,
  LearningCoreSchemaError,
  type AnswerCitation,
  type AnswerStreamEvent,
} from "@keen/api-client";
import { useAppStore } from "../../state/appStore";
import { isLearningCoreStarting, useLearningCore } from "../../services/LearningCoreProvider";
import { PdfCitationViewer } from "./PdfCitationViewer";

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
  grounded: boolean | null;
  retrievalMode: "hybrid" | "lexical_only" | null;
};

const demoMessages: Message[] = [
  {
    id: "demo-user-1",
    role: "user",
    text: "Why does multiplying by a matrix preserve an eigenvector's direction?",
    status: "complete",
    citations: [],
    warnings: [],
    error: null,
    retryable: false,
    grounded: null,
    retrievalMode: null,
  },
  {
    id: "demo-assistant-1",
    role: "assistant",
    text: "This is fixed seed text, not a generated answer. An eigenvector lies on a direction that a matrix only stretches, shrinks, or flips. Algebraically, Av = λv, so the result stays on the same line.",
    question: "Why does multiplying by a matrix preserve an eigenvector's direction?",
    status: "complete",
    citations: [],
    warnings: ["Demo transcript only. No source was retrieved or validated."],
    error: null,
    retryable: false,
    grounded: false,
    retrievalMode: null,
  },
];

function emptyMessage(id: string, role: Message["role"], text: string): Message {
  return {
    id,
    role,
    text,
    status: "complete",
    citations: [],
    warnings: [],
    error: null,
    retryable: false,
    grounded: null,
    retrievalMode: null,
  };
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

function safeStreamFailure(error: unknown): { message: string; retryable: boolean } {
  if (error instanceof LearningCoreResponseError) {
    return {
      message: error.detail?.message ?? `The learning core rejected this answer request (HTTP ${error.status}).`,
      retryable: error.detail?.retryable ?? false,
    };
  }
  if (error instanceof LearningCoreSchemaError) {
    return {
      message: "The answer stream did not match Keen's authenticated event contract. No completed answer was accepted. Retry after the learning core is healthy.",
      retryable: true,
    };
  }
  return {
    message: "The local answer stream disconnected before completion. The partial text below was not recorded as a completed answer. Check the learning core, then retry.",
    retryable: true,
  };
}

export function ConversationPage() {
  const { id: routeId } = useParams();
  const { status, client, connectionGeneration, demoState, retry: retryLearningCore } = useLearningCore();
  const demo = status === "demo";
  const [generatedConversationId] = useState(() => crypto.randomUUID());
  const conversationId = routeId && routeId !== "new" ? routeId : generatedConversationId;
  const draftKey = `keen-conversation-draft:${routeId ?? "new"}`;
  const [incomingDraft] = useState(() => sessionStorage.getItem("keen-new-message"));
  const [messages, setMessages] = useState<Message[]>(demo ? demoMessages : []);
  const [draft, setDraft] = useState(() => incomingDraft ?? localStorage.getItem(draftKey) ?? "");
  const [courseId, setCourseId] = useState<string | null>(null);
  const [pageNotice, setPageNotice] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<AnswerCitation | null>(null);
  const [activeAssistantId, setActiveAssistantId] = useState<string | null>(null);
  const activeRun = useRef<{ controller: AbortController; assistantId: string; question: string } | null>(null);
  const previousDemoMode = useRef(demo);
  const previousGeneration = useRef(connectionGeneration);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { setInspector } = useAppStore();

  useEffect(() => {
    if (incomingDraft !== null) {
      sessionStorage.removeItem("keen-new-message");
    }
    localStorage.setItem(draftKey, draft);
  }, [draft, draftKey, incomingDraft]);

  useEffect(() => {
    if (previousDemoMode.current !== demo) {
      setMessages(demo ? demoMessages : []);
      setPageNotice(null);
      previousDemoMode.current = demo;
    }
  }, [demo]);

  const updateAssistant = useCallback((id: string, update: (message: Message) => Message) => {
    setMessages((current) => current.map((message) => message.id === id ? update(message) : message));
  }, []);

  useEffect(() => {
    if (previousGeneration.current !== connectionGeneration && activeRun.current) {
      const { controller, assistantId } = activeRun.current;
      activeRun.current = null;
      setActiveAssistantId(null);
      controller.abort();
      updateAssistant(assistantId, (message) => ({
        ...message,
        status: "error",
        error: "The learning core restarted while this answer was streaming. The partial text was not completed; retry sends a new authenticated request.",
        retryable: true,
      }));
    }
    previousGeneration.current = connectionGeneration;
  }, [connectionGeneration, updateAssistant]);

  useEffect(() => () => activeRun.current?.controller.abort(), []);

  const applyEvent = useCallback((assistantId: string, event: AnswerStreamEvent) => {
    updateAssistant(assistantId, (message) => {
      if (event.type === "delta") return { ...message, text: message.text + event.data.text };
      if (event.type === "retrieval") {
        return {
          ...message,
          retrievalMode: event.data.mode,
          warnings: event.data.warning ? [...message.warnings, event.data.warning] : message.warnings,
        };
      }
      if (event.type === "warning") {
        return { ...message, warnings: [...message.warnings, event.data.message] };
      }
      if (event.type === "citation") {
        return { ...message, citations: [...message.citations, event.data] };
      }
      if (event.type === "done") {
        return { ...message, status: "complete", grounded: event.data.grounded };
      }
      if (event.type === "error") {
        return {
          ...message,
          status: "error",
          error: event.data.message,
          retryable: event.data.retryable,
          grounded: false,
        };
      }
      return message;
    });
  }, [updateAssistant]);

  const sendQuestion = useCallback(async (rawQuestion: string) => {
    const question = rawQuestion.trim();
    if (!question || activeRun.current) return;
    setPageNotice(null);
    const userId = crypto.randomUUID();

    if (demo) {
      setDraft("");
      setMessages((current) => [...current, emptyMessage(userId, "user", question)]);
      setPageNotice("Added to this local Demo transcript. No model or retrieval request was made.");
      return;
    }
    if (!client || status !== "healthy") {
      setPageNotice("The learning core is not ready, so no answer request was sent. Recover the service and retry.");
      return;
    }
    setDraft("");

    const assistantId = crypto.randomUUID();
    const assistant: Message = {
      ...emptyMessage(assistantId, "assistant", ""),
      question,
      status: "streaming",
    };
    setMessages((current) => [...current, emptyMessage(userId, "user", question), assistant]);
    const controller = new AbortController();
    activeRun.current = { controller, assistantId, question };
    setActiveAssistantId(assistantId);
    try {
      for await (const event of client.answerStream({
        question,
        courseId,
        conversationId,
        retrievalLimit: 8,
      }, { signal: controller.signal })) {
        applyEvent(assistantId, event);
      }
    } catch (error) {
      if (!isAbortError(error) && activeRun.current?.assistantId === assistantId) {
        const failure = safeStreamFailure(error);
        updateAssistant(assistantId, (message) => ({
          ...message,
          status: "error",
          error: failure.message,
          retryable: failure.retryable,
        }));
      }
    } finally {
      if (activeRun.current?.assistantId === assistantId) activeRun.current = null;
      setActiveAssistantId((current) => current === assistantId ? null : current);
      if (typeof bottomRef.current?.scrollIntoView === "function") {
        bottomRef.current.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [applyEvent, client, conversationId, courseId, demo, status, updateAssistant]);

  const stopGeneration = () => {
    const run = activeRun.current;
    if (!run) return;
    activeRun.current = null;
    setActiveAssistantId(null);
    run.controller.abort();
    updateAssistant(run.assistantId, (message) => ({
      ...message,
      status: "stopped",
      error: "Stopped locally: Keen aborted the response stream. No server done event was received, so backend cancellation is not independently confirmed here.",
      retryable: true,
    }));
  };

  const editAndResend = (question: string) => {
    setDraft(question);
    textareaRef.current?.focus();
  };

  const openCitation = (citation: AnswerCitation) => {
    setInspector({
      eyebrow: "Validated retrieval citation",
      title: citation.documentName,
      body: citation.excerpt || "This citation has no excerpt text.",
      meta: [
        `Page ${citation.pageNumber}`,
        `Chunk ${citation.chunkId}`,
        citation.sectionPath.length ? citation.sectionPath.join(" › ") : "No section path",
        citation.bbox ? "Stored PDF geometry available" : "PDF geometry unavailable",
      ],
    });
    setSelectedCitation(citation);
  };

  const serviceUnavailable = !demo && status !== "healthy";
  return (
    <div className="conversation-page">
      {selectedCitation && <PdfCitationViewer key={`${selectedCitation.citationId}:${connectionGeneration}`} citation={selectedCitation} client={client} onClose={() => setSelectedCitation(null)} />}
      <div className="conversation-heading">
        <Badge tone={demo ? "warning" : status === "healthy" ? "success" : "danger"}>
          {demo ? "Demo transcript" : status === "healthy" ? "Live local RAG" : "Learning core unavailable"}
        </Badge>
        <h1>{demo ? "Why eigenvectors keep their direction" : "Conversation"}</h1>
        <p>{demo ? "No model or retrieval request was made" : "Answers stream from the authenticated local learning core."}</p>
        {!demo && demoState?.courses.length ? <label className="conversation-course">
          <span>Course scope</span>
          <select aria-label="Conversation course scope" value={courseId ?? ""} onChange={(event) => setCourseId(event.target.value || null)} disabled={activeAssistantId !== null}>
            <option value="">All indexed courses</option>
            {demoState.courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
          </select>
        </label> : null}
      </div>

      <div className="messages">
        {!messages.length && <Card className="conversation-empty"><strong>Ask from your indexed learning materials</strong><p>Keen will show retrieval limitations, generation errors, and validated citations without replacing them with Demo content.</p></Card>}
        {messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
          <div className="avatar">{message.role === "assistant" ? "K" : "You"}</div>
          <div className="message-body">
            <strong>{message.role === "assistant" ? "Keen" : "You"}</strong>
            {message.text ? <p>{message.text}</p> : message.status === "streaming" ? <p className="stream-placeholder">Waiting for the local provider…</p> : null}
            {message.retrievalMode && <Badge tone={message.retrievalMode === "hybrid" ? "success" : "warning"}>{message.retrievalMode === "hybrid" ? "Hybrid retrieval" : "Lexical-only retrieval"}</Badge>}
            {message.warnings.map((warning) => <p className="conversation-warning" key={warning}>{warning}</p>)}
            {message.error && <div className={`conversation-run-state ${message.status}`} role="alert">{message.error}</div>}
            {message.citations.map((citation) => <button className="citation" key={citation.citationId} onClick={() => openCitation(citation)}>
              <BookOpenText size={13} />{citation.documentName} · p. {citation.pageNumber}
            </button>)}
            {message.role === "assistant" && message.status !== "streaming" && <div className="message-actions">
              <button aria-label="Copy answer unavailable" disabled><Copy size={13} /></button>
              <button aria-label="Retry answer" disabled={!message.question || !message.retryable && message.status !== "complete"} onClick={() => message.question && void sendQuestion(message.question)}><RefreshCw size={13} /></button>
              <button aria-label="Edit and resend" disabled={!message.question} onClick={() => message.question && editAndResend(message.question)}><Edit3 size={13} /></button>
              <button aria-label="Branch unavailable" disabled><GitBranch size={13} /></button>
            </div>}
          </div>
        </article>)}
        <div ref={bottomRef} />
      </div>

      <div className="conversation-composer">
        {pageNotice && <div className="conversation-notice" role="status">{pageNotice}</div>}
        {serviceUnavailable && <div className="conversation-service-state" role="alert">
          <span>{isLearningCoreStarting(status) ? "The learning core is starting; no request can be sent yet." : "The learning core is unavailable; no request will be sent."}</span>
          {!isLearningCoreStarting(status) && <button onClick={() => void retryLearningCore()}>Recover learning core</button>}
        </div>}
        <div className="composer card">
          <textarea
            ref={textareaRef}
            aria-label="Reply"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                void sendQuestion(draft);
              }
            }}
            placeholder={demo ? "Add a note to the Demo transcript…" : "Ask your indexed learning materials…"}
          />
          <div className="composer-bottom">
            <div className="composer-tools"><IconButton label="Attachment unavailable" disabled><Paperclip size={16} /></IconButton><span className="draft-state">Draft saved locally{demo ? " · demo only" : ""}</span></div>
            <button className="send-button" aria-label={activeAssistantId ? "Stop generation" : demo ? "Add to Demo transcript" : "Send message"} onClick={activeAssistantId ? stopGeneration : () => void sendQuestion(draft)} disabled={!activeAssistantId && !draft.trim()}>
              {activeAssistantId ? <Square size={14} /> : <Send size={15} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
