import { ListTodo } from "lucide-react";

export function FeedContextPanel() {
  return (
    <section className="feed-context-panel" aria-labelledby="feed-context-title">
      <header className="feed-context-toolbar">
        <div><ListTodo size={16} aria-hidden="true" /><span>Overview</span></div>
      </header>
      <div className="feed-context-content">
        <h2 id="feed-context-title">Choose a task to continue</h2>
        <p>Select work from Today, Upcoming, Overdue, or Completed. Its learning goal, planned steps, progress, and next action will open here.</p>
      </div>
    </section>
  );
}
