import { describe, expect, it } from "vitest";
import {
  buildDeepLearnReturnTo,
  buildProviderSettingsPath,
  parseDeepLearnReturnTo,
} from "../src/features/settings/providerRecoveryRouting";

describe("provider recovery routing", () => {
  it("builds and parses one canonical internal Deep Learn return target", () => {
    const returnTo = buildDeepLearnReturnTo("session:1", "course:1");

    expect(returnTo).toBe("/deep-learn/session%3A1?course_id=course%3A1");
    expect(parseDeepLearnReturnTo(returnTo)).toEqual({
      sessionId: "session:1",
      courseId: "course:1",
      to: returnTo,
    });
    expect(buildProviderSettingsPath("session-1", "course-1")).toBe(
      "/settings?section=capabilities&return_to=%2Fdeep-learn%2Fsession-1%3Fcourse_id%3Dcourse-1",
    );
  });

  it.each([
    "https://evil.example/deep-learn/session-1?course_id=course-1",
    "//evil.example/deep-learn/session-1?course_id=course-1",
    "/deep-learn/session-1/extra?course_id=course-1",
    "/deep-learn/session%2Fadmin?course_id=course-1",
    "/deep-learn/%73ession-1?course_id=course-1",
    "/deep-learn/session-1?course_id=course-1&course_id=course-2",
    "/deep-learn/session-1?course_id=course-1&api_key=must-not-travel",
    "/deep-learn/session-1?course_id=course-1#fragment",
    "/deep-learn/session-1?course_id=course-1\nLocation:https://evil.example",
  ])("rejects a non-canonical or unsafe return target: %s", (value) => {
    expect(parseDeepLearnReturnTo(value)).toBeNull();
  });

  it("omits return_to when the supplied identifiers fail the learning identifier whitelist", () => {
    const path = buildProviderSettingsPath("https://evil.example", "course-1");

    expect(path).toBe("/settings?section=capabilities");
    expect(path).not.toContain("return_to");
    expect(path).not.toContain("api_key");
  });
});
