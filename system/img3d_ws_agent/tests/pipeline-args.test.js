"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const pythonInputArgs = require("../pipelineArgs");

test("system_frame worker stages explicitly require Python provenance", () => {
  const sessionDir = "data/system-sessions/session/frames/frame";
  assert.deepEqual(
    pythonInputArgs(sessionDir, { jobType: "system_frame" }),
    ["-i", sessionDir, "--require-provenance"],
  );
});

test("legacy worker stages do not impose new provenance pins", () => {
  const sessionDir = "data/legacy-session";
  assert.deepEqual(
    pythonInputArgs(sessionDir, { jobType: "legacy" }),
    ["-i", sessionDir],
  );
  assert.deepEqual(pythonInputArgs(sessionDir, {}), ["-i", sessionDir]);
});
