import { expect, test } from "vitest";

test("frontend source and tests contain no React or backup artifacts", () => {
  const files = Object.keys(import.meta.glob(["../src/**/*", "./**/*"], { query: "?raw", import: "default" }));
  expect(files.filter((path) => /(?:\.tsx|\.bak)$/.test(path))).toEqual([]);
});
