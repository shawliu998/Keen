import { useState } from "react";
import type { Course, LearningCoreClient } from "@keen/api-client";
import { Button, Card } from "@keen/ui";
import { useCourseCreate } from "./useCourseCreate";

type CourseCacheKey = readonly ["learning-core", "demo-state", string | number, number];

export function CourseCreateForm({
  client,
  cacheKey,
  demo,
  onCreated,
}: {
  client: Pick<LearningCoreClient, "createCourse"> | null;
  cacheKey: CourseCacheKey;
  demo: boolean;
  onCreated: (course: Course) => void;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const { creating, error, notice, createCourse } = useCourseCreate({ client, cacheKey, onCreated });
  const disabled = demo || client === null || creating;
  const normalizedTitle = title.trim();

  return <Card className="course-create">
    <div>
      <strong>Create a course</strong>
      <span>{demo ? "Browser Demo cannot create or store courses." : "Create a local course, then it will be selected for the next import."}</span>
    </div>
    <form onSubmit={(event) => {
      event.preventDefault();
      if (!disabled && normalizedTitle) void createCourse(normalizedTitle, description);
    }}>
      <label>
        <span>Course title</span>
        <input aria-label="Course title" value={title} maxLength={240} disabled={disabled} onChange={(event) => setTitle(event.target.value)} />
      </label>
      <label>
        <span>Description</span>
        <textarea aria-label="Course description" value={description} maxLength={8_000} disabled={disabled} onChange={(event) => setDescription(event.target.value)} />
      </label>
      <Button className="primary" type="submit" disabled={disabled || !normalizedTitle} aria-busy={creating}>
        {creating ? "Creating…" : "Create course"}
      </Button>
    </form>
    {demo && <p className="course-create-demo" role="status">Browser Demo: course creation is unavailable and no request will be sent.</p>}
    {!demo && client === null && <p className="course-create-demo" role="status">Course creation is unavailable until Keen confirms the local service and course list. No request was sent.</p>}
    {notice && <p className="operation-notice" role="status">{notice}</p>}
    {error && <p className="operation-error" role="alert">{error}</p>}
  </Card>;
}
