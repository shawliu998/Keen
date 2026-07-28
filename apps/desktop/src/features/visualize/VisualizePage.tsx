import { Badge } from "@keen/ui";
import { CircleCheck, CircleMinus, FileText } from "lucide-react";
import { Page } from "../../components/Page";

const unavailable = ["Course-source grounding", "Generated diagrams or animation", "Export and narration"];

export function VisualizePage() {
  return (
    <Page
      className="visualize-page"
      title="Visual explanation"
      description="A bundled teaching example for reviewing Keen’s visual language."
      actions={<Badge>Bundled local example</Badge>}
    >
      <div className="visualize-disclosure" role="note">
        <FileText size={15} aria-hidden="true" />
        <span>This page uses fixed interface content. It does not read course files, call a model, or create an artifact.</span>
      </div>

      <div className="visualize-workspace">
        <figure className="visual-example">
          <div className="visual-example-header">
            <div><span>Linear algebra</span><h2>Why an eigenvector keeps its direction</h2></div>
            <Badge>Bundled SVG</Badge>
          </div>
          <svg className="eigenvector-diagram" viewBox="0 0 820 390" role="img" aria-labelledby="eigenvector-title eigenvector-description">
            <title id="eigenvector-title">Eigenvector transformation diagram</title>
            <desc id="eigenvector-description">Two coordinate planes show a vector before and after multiplication by matrix A. Its length changes while its direction stays the same.</desc>
            <defs>
              <pattern id="coordinate-grid" width="28" height="28" patternUnits="userSpaceOnUse" className="diagram-grid-pattern">
                <path d="M 28 0 L 0 0 0 28" fill="none" stroke="currentColor" strokeWidth="1" />
              </pattern>
              <marker id="vector-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="currentColor" />
              </marker>
            </defs>

            <g className="diagram-plane-group" transform="translate(42 42)">
              <rect width="292" height="260" rx="8" className="diagram-surface" />
              <rect width="292" height="260" rx="8" fill="url(#coordinate-grid)" className="diagram-grid" />
              <path d="M146 18V242M18 130H274" className="diagram-axis" />
              <path d="M146 130L229 82" className="diagram-vector-line" markerEnd="url(#vector-arrow)" />
              <circle cx="146" cy="130" r="4" className="diagram-origin" />
              <text x="236" y="78" className="diagram-vector-label">v</text>
              <text x="16" y="286" className="diagram-state-label">Before transformation</text>
            </g>

            <g className="diagram-transform" transform="translate(383 146)">
              <text x="26" y="0">A</text>
              <path d="M0 30H68" markerEnd="url(#vector-arrow)" />
            </g>

            <g className="diagram-plane-group" transform="translate(486 42)">
              <rect width="292" height="260" rx="8" className="diagram-surface" />
              <g transform="skewX(-11) translate(25 0)">
                <rect width="248" height="260" fill="url(#coordinate-grid)" className="diagram-grid" />
                <path d="M124 18V242M0 130H248" className="diagram-axis" />
              </g>
              <path d="M146 130L256 66" className="diagram-vector-line" markerEnd="url(#vector-arrow)" />
              <circle cx="146" cy="130" r="4" className="diagram-origin" />
              <text x="260" y="61" className="diagram-vector-label">Av</text>
              <text x="16" y="286" className="diagram-state-label">After transformation</text>
            </g>
          </svg>
          <figcaption>
            <strong>Av = λv</strong>
            <span>The matrix scales the vector by λ. Its magnitude may change, but it remains on the same line.</span>
          </figcaption>
        </figure>

        <aside className="visual-example-notes" aria-label="Example availability">
          <div>
            <span className="visual-notes-label">Available here</span>
            <h2>A fixed, inspectable example</h2>
            <p>The diagram and explanation ship with the interface so layout and readability can be reviewed without implying generation.</p>
          </div>
          <ul className="visual-availability-list">
            <li><CircleCheck size={15} aria-hidden="true" /><span><strong>Local and offline</strong><small>No service connection is required.</small></span></li>
            {unavailable.map((item) => <li className="is-unavailable" key={item}><CircleMinus size={15} aria-hidden="true" /><span><strong>{item}</strong><small>Not implemented in this build.</small></span></li>)}
          </ul>
        </aside>
      </div>
    </Page>
  );
}
