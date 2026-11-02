"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const glbOutputPath = require("../glbOutputPath");

test("system_frame export resolves frame_planes.glb beside its convention sidecar", (t) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "img3d-agent-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  const systemSessionId = "0123456789abcdef0123456789abcdef";
  const frameId = "frame_001";
  const sessionDir = path.join(root, "system-sessions", systemSessionId, "frames", frameId);
  const pythonOutput = path.join(sessionDir, "frame", "frame_planes.glb");
  fs.mkdirSync(path.dirname(pythonOutput), { recursive: true });
  fs.writeFileSync(pythonOutput, Buffer.from("synthetic GLB fixture"));

  const workerOutput = glbOutputPath(sessionDir, `${frameId}.png`, "system_frame");

  assert.equal(workerOutput, pythonOutput);
  assert.equal(fs.readFileSync(workerOutput, "utf8"), "synthetic GLB fixture");
  assert.equal(`${workerOutput}.convention.json`, path.join(sessionDir, "frame", "frame_planes.glb.convention.json"));
  assert.equal(path.basename(path.dirname(path.dirname(workerOutput))), frameId);
});

test("legacy export path continues to use the submitted image basename", () => {
  const sessionDir = path.join("data", "legacy-session");
  assert.equal(
    glbOutputPath(sessionDir, "input-image.jpg", "legacy"),
    path.join(sessionDir, "input-image", "input-image_planes.glb"),
  );
});
