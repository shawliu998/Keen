const learningIdentifier = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
const MAX_RETURN_TO_LENGTH = 512;

function containsControlCharacter(value: string): boolean {
  return Array.from(value).some((character) => {
    const codePoint = character.codePointAt(0) ?? 0;
    return codePoint < 32 || codePoint === 127;
  });
}

export type DeepLearnReturnTarget = {
  courseId: string;
  sessionId: string;
  to: string;
};

export function buildDeepLearnReturnTo(
  sessionId: string,
  courseId: string,
): string | null {
  if (!learningIdentifier.test(sessionId) || !learningIdentifier.test(courseId)) {
    return null;
  }
  const search = new URLSearchParams({ course_id: courseId });
  return `/deep-learn/${encodeURIComponent(sessionId)}?${search.toString()}`;
}

export function buildProviderSettingsPath(
  sessionId: string,
  courseId: string,
): string {
  const search = new URLSearchParams({ section: "capabilities" });
  const returnTo = buildDeepLearnReturnTo(sessionId, courseId);
  if (returnTo) search.set("return_to", returnTo);
  return `/settings?${search.toString()}`;
}

export function parseDeepLearnReturnTo(
  value: string | null,
): DeepLearnReturnTarget | null {
  if (
    !value
    || value.length > MAX_RETURN_TO_LENGTH
    || !value.startsWith("/deep-learn/")
    || value.startsWith("//")
    || value.includes("\\")
    || containsControlCharacter(value)
  ) {
    return null;
  }

  const questionMark = value.indexOf("?");
  if (questionMark <= 0 || value.indexOf("?", questionMark + 1) !== -1) return null;
  const pathname = value.slice(0, questionMark);
  const searchValue = value.slice(questionMark + 1);
  const match = /^\/deep-learn\/([^/?#]+)$/u.exec(pathname);
  if (!match) return null;

  let sessionId: string;
  try {
    sessionId = decodeURIComponent(match[1]);
  } catch {
    return null;
  }
  if (!learningIdentifier.test(sessionId)) return null;

  const search = new URLSearchParams(searchValue);
  if (
    search.getAll("course_id").length !== 1
    || Array.from(search.keys()).some((key) => key !== "course_id")
  ) {
    return null;
  }
  const courseId = search.get("course_id");
  if (!courseId || !learningIdentifier.test(courseId)) return null;

  const canonical = buildDeepLearnReturnTo(sessionId, courseId);
  if (!canonical || value !== canonical) return null;
  return { courseId, sessionId, to: canonical };
}
