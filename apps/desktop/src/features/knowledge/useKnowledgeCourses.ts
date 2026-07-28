import { useMemo, useState } from "react";
import type { Course } from "@keen/api-client";
import { documents as seedDocuments } from "../../data/seed";
import type { CourseOption } from "./documentJobs";

type CreatedCourse = Course & { connectionId: string };

export const demoCourses: CourseOption[] = Array.from(new Set(seedDocuments.map((document) => document.course)))
  .map((title, index) => ({ id: `demo-course-${index + 1}`, title }));
export const demoCourseByTitle = new Map(demoCourses.map((course) => [course.title, course]));

export function useKnowledgeCourses({
  isDemo,
  persistedCourses,
  connectionId,
}: {
  isDemo: boolean;
  persistedCourses: Course[] | undefined;
  connectionId: string;
}) {
  const [createdCourses, setCreatedCourses] = useState<CreatedCourse[]>([]);
  const courses = useMemo<CourseOption[]>(() => {
    if (isDemo) return demoCourses;
    const known = new Map((persistedCourses ?? []).map((course) => [course.id, course]));
    for (const course of createdCourses) {
      if (course.connectionId === connectionId) known.set(course.id, course);
    }
    return Array.from(known.values(), (course) => ({ id: course.id, title: course.title }));
  }, [connectionId, createdCourses, isDemo, persistedCourses]);
  const courseTitles = useMemo(() => new Map(courses.map((course) => [course.id, course.title])), [courses]);
  const addCreatedCourse = (course: Course) => setCreatedCourses((current) => current.some((item) => item.id === course.id && item.connectionId === connectionId)
    ? current.map((item) => item.id === course.id && item.connectionId === connectionId ? { ...course, connectionId } : item)
    : [...current, { ...course, connectionId }]);

  return { courses, courseTitles, addCreatedCourse };
}
