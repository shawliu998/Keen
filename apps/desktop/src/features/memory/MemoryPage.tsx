import { useMemo, useState } from "react";
import { Brain, Check, Edit3, Eye, EyeOff, Search, Trash2 } from "lucide-react";
import { Badge, Button, Card, EmptyState } from "@keen/ui";
import { Page, Segmented } from "../../components/Page";
import { useAppStore } from "../../state/appStore";

type Filter = "All" | "Goals" | "Preferences" | "Knowledge" | "Inferences";
const kindLabel = { goal: "Goal", preference: "Preference", misconception: "Misconception", mastery: "Mastered", weakness: "Weak concept", inference: "Agent inference" } as const;

export function MemoryPage() {
  const { memories, toggleMemory, deleteMemory, setInspector } = useAppStore();
  const [filter, setFilter] = useState<Filter>("All");
  const [search, setSearch] = useState("");
  const filtered = useMemo(() => memories.filter((m) => m.statement.toLowerCase().includes(search.toLowerCase()) && (filter === "All" || filter === "Goals" && m.kind === "goal" || filter === "Preferences" && m.kind === "preference" || filter === "Knowledge" && ["mastery","weakness","misconception"].includes(m.kind) || filter === "Inferences" && m.kind === "inference")), [memories, filter, search]);
  return (
    <Page title="Learner Memory" description="Review exactly what Keen remembers and why. You can edit, disable, or delete any item." actions={<Badge tone="success"><Check size={11} />Local only</Badge>}>
      <Card className="persona-card"><div className="persona-avatar"><Brain size={22} /></div><div><strong>Your learning profile</strong><p>Prefers examples before formal notation · 20–30 minute sessions · Morning focus</p></div><Button><Edit3 size={14} />Edit profile</Button></Card>
      <div className="memory-tools"><Segmented value={filter} options={["All","Goals","Preferences","Knowledge","Inferences"]} onChange={setFilter} /><div className="search-box"><Search size={14} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search memory…" /></div></div>
      <div className="memory-list">{filtered.map((memory) => <Card className={`memory-card ${memory.enabled ? "" : "disabled"}`} key={memory.id}><div className={`memory-kind kind-${memory.kind}`}><Brain size={15} /></div><div className="memory-copy"><div><Badge>{kindLabel[memory.kind]}</Badge>{!memory.enabled && <Badge tone="warning">Not used</Badge>}</div><h3>{memory.statement}</h3><button onClick={() => setInspector({ eyebrow: "Memory evidence", title: kindLabel[memory.kind], body: memory.evidence, meta: ["Stored locally", memory.enabled ? "Available to agent" : "Excluded from agent context"] })}>Evidence: {memory.evidence}</button></div><div className="memory-actions"><button aria-label="Edit memory"><Edit3 size={15} /></button><button aria-label={memory.enabled ? "Disable memory" : "Enable memory"} onClick={() => toggleMemory(memory.id)}>{memory.enabled ? <Eye size={15} /> : <EyeOff size={15} />}</button><button aria-label="Delete memory" onClick={() => deleteMemory(memory.id)}><Trash2 size={15} /></button></div></Card>)}{filtered.length === 0 && <Card><EmptyState icon={<Brain size={26} />} title="No matching memories" description="Try another filter or search term." /></Card>}</div>
      <Card className="privacy-callout"><EyeOff size={17} /><div><strong>You control agent memory</strong><p>Disabled memories stay visible here but are never added to model context. Deleted memories are removed from local storage.</p></div><Button>Memory settings</Button></Card>
    </Page>
  );
}
