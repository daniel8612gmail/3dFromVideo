'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const protocol = require('../protocol');

const sessionId = '0123456789abcdef0123456789abcdef';
const frameId = 'frame_0000';
const requestId = 'a'.repeat(32);

function glb() {
  const bytes = Buffer.alloc(20);
  bytes.write('glTF', 0);
  bytes.writeUInt32LE(2, 4);
  bytes.writeUInt32LE(20, 8);
  return bytes;
}

function fixture() {
  const metadata = {
    schemaVersion: 1,
    requestId,
    systemSessionId: sessionId,
    frameId,
    sequence: 0,
    inputGlbPath: `system-sessions/${sessionId}/outbox/${requestId}/input.glb`,
    inputGlbSha256: protocol.sha256(glb()),
    frames: [{
      frameId,
      sequence: 0,
      glbPath: `system-sessions/${sessionId}/frames/${frameId}/frame.attempt-1.glb`,
      cameraToFirstFrame: {
        translationM: [0, 0, 0],
        rotationQuaternionXyzw: [0, 0, 0, 1],
      },
      conventionSidecarPath: `system-sessions/${sessionId}/frames/${frameId}/frame.attempt-1.glb.convention.json`,
    }],
  };
  const envelope = {
    requestId,
    systemSessionId: sessionId,
    frameId,
    sequence: 0,
    size: glb().length,
    inputGlbSha256: protocol.sha256(glb()),
    metadataSha256: protocol.sha256(Buffer.from(protocol.canonicalJson(metadata))),
  };
  return { metadata, envelope, bytes: glb() };
}

test('validates deterministic metadata hash, session paths, and first-frame identity', () => {
  const { metadata, envelope } = fixture();
  assert.doesNotThrow(() => protocol.validateMetadata(metadata, envelope));
  const legacy = { ...metadata, frames: metadata.frames.map(({ glbPath, conventionSidecarPath, ...frame }) => ({
    ...frame,
    cameraToFirstFrame: undefined,
    cameraToSystemSessionFrame: { translationM: [0, 0, 0], rotationQuaternionXyzw: [0, 0, 0, 1] },
    glbPath,
    conventionSidecarPath,
  })) };
  assert.throws(() => protocol.validateMetadata(legacy, envelope), /metadata integrity|frame metadata/);
  const escaped = structuredClone(metadata);
  escaped.frames[0].glbPath = `system-sessions/${sessionId}/frames/${frameId}/../outside.glb`;
  const escapedEnvelope = {
    ...envelope,
    metadataSha256: protocol.sha256(Buffer.from(protocol.canonicalJson(escaped))),
  };
  assert.throws(() => protocol.validateMetadata(escaped, escapedEnvelope), /outside/);
  const nonIdentity = structuredClone(metadata);
  nonIdentity.frames[0].cameraToFirstFrame.translationM = [0.1, 0, 0];
  const nonIdentityEnvelope = {
    ...envelope,
    metadataSha256: protocol.sha256(Buffer.from(protocol.canonicalJson(nonIdentity))),
  };
  assert.throws(() => protocol.validateMetadata(nonIdentity, nonIdentityEnvelope), /Sequence 0/);
});

test('durably stages verified payloads and rejects changed replay under the same requestId', (t) => {
  const { metadata, envelope, bytes } = fixture();
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'img3d-aggregator-'));
  t.after(() => fs.rmSync(dataDir, { recursive: true, force: true }));
  const sessionDir = path.join(dataDir, 'system-sessions', sessionId);
  const frameDir = path.join(sessionDir, 'frames', frameId);
  fs.mkdirSync(frameDir, { recursive: true });
  fs.writeFileSync(path.join(frameDir, 'frame.attempt-1.glb'), bytes);
  fs.writeFileSync(path.join(frameDir, 'frame.attempt-1.glb.convention.json'), JSON.stringify({
    schemaVersion: 1,
    glbSha256: envelope.inputGlbSha256,
  }));
  const first = protocol.stageRequest(dataDir, envelope, metadata, bytes);
  assert.equal(first.state.status, 'durable-accepted');
  assert.equal(fs.readFileSync(path.join(first.destination, 'input.glb')).length, bytes.length);
  assert.ok(fs.existsSync(path.join(first.destination, 'input.glb.convention.json')));
  assert.equal(protocol.stageRequest(dataDir, envelope, metadata, bytes).duplicate, true);

  const changed = Buffer.from(bytes);
  changed[12] = 2;
  assert.throws(() => protocol.stageRequest(dataDir, envelope, metadata, changed), /SHA-256/);
});
