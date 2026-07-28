import { Badge, Button } from "@keen/ui";
import { CalendarOff, Database, FileInput, ListTodo, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { Page } from "../../components/Page";

const requirements = [
  { icon: FileInput, title: "Course inputs", description: "A real syllabus or course source must be imported and validated before it can shape a plan." },
  { icon: Database, title: "Durable planning state", description: "Study constraints, proposed sessions, edits, and recovery need a persisted local contract." },
  { icon: ShieldCheck, title: "Calendar handoff", description: "A calendar adapter and explicit Level 3 confirmation are required before any event can be written." },
] as const;

export function PlannerPage() {
  const navigate = useNavigate();
  return (
    <Page
      className="planner-page"
      title="Study Planner"
      description="Planning and calendar integration are not implemented in this build."
      actions={<Badge tone="warning">Not implemented</Badge>}
    >
      <section className="planner-boundary" aria-labelledby="planner-boundary-title">
        <div className="planner-boundary-icon" aria-hidden="true"><CalendarOff size={22} /></div>
        <div>
          <span>Current availability</span>
          <h2 id="planner-boundary-title">No study plan is connected</h2>
          <p>Keen does not currently parse a syllabus into a schedule, generate study sessions, or read and write a system calendar.</p>
        </div>
        <Button onClick={() => navigate("/feed")}><ListTodo size={15} />Open Learning Feed</Button>
      </section>

      <section className="planner-requirements" aria-labelledby="planner-requirements-title">
        <div className="planner-requirements-heading">
          <div><span>Future capability contract</span><h2 id="planner-requirements-title">Required before planning can ship</h2></div>
          <p>These are implementation gates, not available setup steps.</p>
        </div>
        <ul>
          {requirements.map(({ icon: Icon, title, description }) => (
            <li key={title}>
              <Icon size={17} aria-hidden="true" />
              <span><strong>{title}</strong><small>{description}</small></span>
              <Badge>Pending</Badge>
            </li>
          ))}
        </ul>
      </section>

      <p className="planner-permission-note"><ShieldCheck size={14} aria-hidden="true" />Future calendar writes remain Level 3 actions: Keen must show the proposed events and ask for confirmation immediately before writing them.</p>
    </Page>
  );
}
