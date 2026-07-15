import { useEffect, useRef, useState } from "react";
import { BookOpenText, Check, ChevronDown, Copy, Edit3, GitBranch, Paperclip, RefreshCw, Send, Square, Wrench } from "lucide-react";
import { Badge, Card, IconButton } from "@keen/ui";
import { useAppStore } from "../../state/appStore";

type Message = { id: number; role: "user" | "assistant"; text: string };

const initial: Message[] = [
  { id: 1, role: "user", text: "Why does multiplying by a matrix preserve an eigenvector's direction?" },
  { id: 2, role: "assistant", text: "Think of a matrix as a transformation of space. Most vectors rotate away from their original line. An eigenvector lies on a special direction that the transformation only stretches, shrinks, or flips.\n\nAlgebraically, **Av = λv**. The result is a scalar multiple of v, so it stays on the same line. For example:\n\nA = [[2, 0], [0, 1]] and v = [1, 0] → Av = [2, 0] = 2v\n\nThe x-axis direction is preserved, while its length doubles." },
];

export function ConversationPage() {
  const [messages, setMessages] = useState(initial);
  const [draft, setDraft] = useState(() => {
    const incoming = sessionStorage.getItem("keen-new-message");
    if (incoming) sessionStorage.removeItem("keen-new-message");
    return incoming ?? localStorage.getItem("keen-conversation-draft") ?? "";
  });
  const [generating, setGenerating] = useState(false);
  const [traceOpen, setTraceOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const { setInspector } = useAppStore();
  useEffect(() => localStorage.setItem("keen-conversation-draft", draft), [draft]);
  const send = () => {
    if (!draft.trim() || generating) return;
    const question = draft; setDraft(""); setGenerating(true); setMessages((m) => [...m, { id: Date.now(), role: "user", text: question }]);
    window.setTimeout(() => { setMessages((m) => [...m, { id: Date.now() + 1, role: "assistant", text: "Offline demo response: the model and retrieval sidecar are not connected, so Keen did not generate a source-grounded answer. Configure a provider after sidecar integration is available." }]); setGenerating(false); bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, 650);
  };
  return (
    <div className="conversation-page">
      <div className="conversation-heading"><Badge tone="warning">Demo transcript</Badge><h1>Why eigenvectors keep their direction</h1><p>Linear Algebra · deterministic seed content</p></div>
      <div className="messages">{messages.map((message) => <article className={`message ${message.role}`} key={message.id}>
        <div className="avatar">{message.role === "assistant" ? "K" : "AC"}</div><div className="message-body"><strong>{message.role === "assistant" ? "Keen" : "You"}</strong>
          {message.text.split("\n\n").map((part) => <p key={part}>{part}</p>)}
          {message.role === "assistant" && <><button className="citation" onClick={() => setInspector({ eyebrow: "Unverified demo citation", title: "Linear Algebra — Chapter 5", body: "This excerpt is deterministic seed content. No source PDF is present, so it is not a validated citation.", meta: ["Nominal page 14", "Demo chunk d1-p14-c3", "Verification unavailable"] })}><BookOpenText size={13} />Demo citation · p. 14</button>
            <div className="message-actions"><button aria-label="Copy answer"><Copy size={13} /></button><button aria-label="Regenerate answer"><RefreshCw size={13} /></button><button aria-label="Edit and resend"><Edit3 size={13} /></button><button aria-label="Branch conversation"><GitBranch size={13} /></button></div></>}
        </div></article>)}
        <Card className="trace-card"><button onClick={() => setTraceOpen(!traceOpen)}><Wrench size={14} /><span>Demo trace · no tools executed</span><Badge tone="warning"><Check size={10} /> Seed only</Badge><ChevronDown size={14} /></button>{traceOpen && <div><code>Planned: search_course_sources("eigenvector direction")</code><code>Planned: get_source_page(document="d1", page=14)</code><p>Sidecar unavailable · no tokens used · no state mutations</p></div>}</Card>
        <div ref={bottomRef} />
      </div>
      <div className="conversation-composer"><div className="composer card"><textarea aria-label="Reply" value={draft} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } }} placeholder="Ask a follow-up…" /><div className="composer-bottom"><div className="composer-tools"><IconButton label="Attach a file"><Paperclip size={16} /></IconButton><span className="draft-state">Draft saved locally</span></div><button className="send-button" aria-label={generating ? "Stop generating" : "Send"} onClick={generating ? () => setGenerating(false) : send}>{generating ? <Square size={14} /> : <Send size={15} />}</button></div></div></div>
    </div>
  );
}
