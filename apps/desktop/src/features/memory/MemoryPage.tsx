import { useNavigate } from "react-router-dom";
import { Button } from "@keen/ui";
import { Page } from "../../components/Page";

export function MemoryPage() {
  const navigate = useNavigate();
  return (
    <Page title="Learner Memory" description="A future home for learner-approved goals, preferences, and evidence.">
      <section className="memory-boundary" aria-labelledby="memory-boundary-title">
        <div className="memory-boundary-copy">
          <h2 id="memory-boundary-title">Learner memory is not connected</h2>
          <p>Keen does not currently infer a learner profile or pass memory records to an Agent. No sample goals, misconceptions, or mastery values are shown as if they were saved evidence.</p>
        </div>
        <dl className="memory-facts">
          <div><dt>Agent context</dt><dd>Not connected</dd></div>
          <div><dt>Automatic inference</dt><dd>Not implemented</dd></div>
          <div><dt>Edit and deletion</dt><dd>Not available</dd></div>
        </dl>
        <div className="memory-next-step">
          <div><strong>Available now</strong><p>Use the Knowledge Base to review the local sources Keen can currently display and verify.</p></div>
          <Button onClick={() => navigate("/knowledge")}>Open Knowledge Base</Button>
        </div>
      </section>
    </Page>
  );
}
