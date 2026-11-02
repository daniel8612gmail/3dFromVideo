'use strict';

const assert = require('node:assert/strict');
const test = require('node:test');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const crypto = require('node:crypto');
const {
  validGlb,
  manifestFrame,
  validateConventionSidecar,
  validateCaptureTransform,
  frameDir,
  retryStatus,
} = require('../src/system-session-jobs');

const systemSessionId = '0123456789abcdef0123456789abcdef';
const frameId = 'frame_001';
const codeRevision = '74fbce054ebed49800de42d0ad0e83495065719a';
const checkpointSha256 = 'b'.repeat(64);
const imageSha256 = 'a'.repeat(64);

function glb(length = 20) {
  const buffer = Buffer.alloc(length);
  buffer.write('glTF', 0, 'ascii');
  buffer.writeUInt32LE(2, 4);
  buffer.writeUInt32LE(length, 8);
  return buffer;
}

function registeredFrame(glbPath) {
  return {
    frameId,
    sequence: 1,
    sha256: imageSha256,
    width: 1920,
    height: 1080,
    orientation: 0,
    imageTransform: {
      sourceWidth: 1920,
      sourceHeight: 1080,
      rotationDegrees: 0,
      mirrorX: false,
      crop: { x: 0, y: 0, width: 1, height: 1 },
    },
    cameraToFirstFrame: {
      translationM: [1, 2, 3],
      rotationQuaternionXyzw: [0, 0, 0, 1],
    },
    frameGlb: path.basename(glbPath),
  };
}

function workerSidecar(glbSha256) {
  return {
    schemaVersion: 1,
    conventionId: 'moge3-v3-metric-opencv-camera-legacy-glb',
    basis: {
      moge: 'opencv-camera,+X-right,+Y-down,+Z-forward',
      storedGlb: 'legacy-export-F-applied-to-MoGe',
      captureCamera: 'arcore-opengl,+X-right,+Y-up,-Z-forward',
      world: 'right-handed,+X-right,+Y-up,-Z-forward',
    },
    glbStoredToMogeMatrix4x4: [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1],
    mogeToCaptureCameraMatrix4x4: [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1],
    scale: 1.0,
    unit: 'm',
    provenance: {
      modelVersion: 'v3',
      codeRevision,
      checkpointSha256,
      verification: 'pinned-source-git-revision+configured-checkpoint-sha256',
    },
    canonicalOrientation: {
      verified: true,
      method: 'EXIF orientation absent or 1; source pixels used without rotation or mirroring',
      exifOrientation: null,
      imageSha256,
    },
    glbSha256,
  };
}

test('validates binary GLB header, version, and declared length', () => {
  assert.equal(validGlb(glb()), true);
  assert.equal(validGlb(Buffer.from('not a GLB')), false);
  const badLength = glb();
  badLength.writeUInt32LE(21, 8);
  assert.equal(validGlb(badLength), false);
  const badVersion = glb();
  badVersion.writeUInt32LE(1, 4);
  assert.equal(validGlb(badVersion), false);
});

test('builds aggregator metadata from capture pose and worker sidecar, not client model fields', (t) => {
  const previousRevision = process.env.MOGE_EXPECTED_CODE_REVISION;
  const previousCheckpoint = process.env.MOGE_EXPECTED_CHECKPOINT_SHA256;
  process.env.MOGE_EXPECTED_CODE_REVISION = codeRevision;
  process.env.MOGE_EXPECTED_CHECKPOINT_SHA256 = checkpointSha256;
  t.after(() => {
    if (previousRevision === undefined) delete process.env.MOGE_EXPECTED_CODE_REVISION;
    else process.env.MOGE_EXPECTED_CODE_REVISION = previousRevision;
    if (previousCheckpoint === undefined) delete process.env.MOGE_EXPECTED_CHECKPOINT_SHA256;
    else process.env.MOGE_EXPECTED_CHECKPOINT_SHA256 = previousCheckpoint;
  });

  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'img3d-system-session-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const glbPath = path.join(root, 'frame.attempt-1.glb');
  const bytes = glb();
  fs.writeFileSync(glbPath, bytes);
  const glbSha256 = crypto.createHash('sha256').update(bytes).digest('hex');
  fs.writeFileSync(`${glbPath}.convention.json`, JSON.stringify(workerSidecar(glbSha256)));

  const manifest = manifestFrame(frameId, registeredFrame(glbPath), glbPath);
  assert.deepEqual(manifest.cameraToFirstFrame.translationM, [1, 2, 3]);
  assert.equal(manifest.conventionSidecarPath, `${glbPath}.convention.json`);
  assert.equal(Object.hasOwn(manifest, 'mogeToCameraMatrix4x4'), false);
  assert.equal(Object.hasOwn(manifest, 'scaleEstimate'), false);
  assert.equal(Object.hasOwn(manifest, 'axes'), false);
});

test('requires explicit cameraToFirstFrame and identity sequence zero', () => {
  const record = registeredFrame('frame.attempt-1.glb');
  record.sequence = 0;
  record.cameraToFirstFrame = {
    translationM: [1, 0, 0],
    rotationQuaternionXyzw: [0, 0, 0, 1],
  };
  assert.throws(() => manifestFrame(frameId, record, 'frame.attempt-1.glb'), /Sequence 0.*identity/);
  const ambiguous = registeredFrame('frame.attempt-1.glb');
  ambiguous.cameraToSystemSessionFrame = ambiguous.cameraToFirstFrame;
  delete ambiguous.cameraToFirstFrame;
  assert.throws(() => manifestFrame(frameId, ambiguous, 'frame.attempt-1.glb'), /ambiguous legacy/);
});

test('admits only documented canonical capture image transforms for aggregation', () => {
  const canonical = registeredFrame('frame.attempt-1.glb');
  assert.doesNotThrow(() => validateCaptureTransform(frameId, canonical));

  const invalidRecords = [
    ['orientation=90', { ...canonical, orientation: 90 }, /orientation=0 only/],
    ['missing orientation', (() => { const r = { ...canonical }; delete r.orientation; return r; })(), /missing capture orientation/],
    ['unknown orientation', { ...canonical, orientation: 'unknown' }, /unsupported capture orientation/],
    ['rotated image', { ...canonical, imageTransform: { ...canonical.imageTransform, rotationDegrees: 90 } }, /rotationDegrees; aggregation supports 0 only/],
    ['unknown rotation', { ...canonical, imageTransform: { ...canonical.imageTransform, rotationDegrees: 45 } }, /rotationDegrees; aggregation supports 0 only/],
    ['missing rotation', { ...canonical, imageTransform: (() => { const t = { ...canonical.imageTransform }; delete t.rotationDegrees; return t; })() }, /missing or has unknown imageTransform/],
    ['mirrored image', { ...canonical, imageTransform: { ...canonical.imageTransform, mirrorX: true } }, /mirrorX; aggregation supports false only/],
    ['cropped image', { ...canonical, imageTransform: { ...canonical.imageTransform, crop: { x: 0.1, y: 0, width: 0.9, height: 1 } } }, /crop; aggregation supports the full frame only/],
    ['missing crop value', { ...canonical, imageTransform: { ...canonical.imageTransform, crop: { x: 0, y: 0, width: 1 } } }, /missing or has unknown imageTransform.crop/],
    ['missing image transform', (() => { const r = { ...canonical }; delete r.imageTransform; return r; })(), /missing or has unknown imageTransform/],
    ['unknown image transform field', { ...canonical, imageTransform: { ...canonical.imageTransform, flipY: false } }, /missing or has unknown imageTransform/],
    ['source dimensions differ from uploaded image', { ...canonical, imageTransform: { ...canonical.imageTransform, sourceWidth: 1280 } }, /source dimensions must match/],
    ['unknown crop field', { ...canonical, imageTransform: { ...canonical.imageTransform, crop: { ...canonical.imageTransform.crop, mode: 'center' } } }, /missing or has unknown imageTransform.crop/],
  ];
  for (const [label, record, error] of invalidRecords) {
    assert.throws(() => manifestFrame(frameId, record, 'unused.glb'), error, label);
  }
});

test('fails closed when worker pins or sidecar GLB/image binding do not match', () => {
  const glbSha256 = crypto.createHash('sha256').update(glb()).digest('hex');
  const sidecar = workerSidecar(glbSha256);
  const oldRevision = process.env.MOGE_EXPECTED_CODE_REVISION;
  const oldCheckpoint = process.env.MOGE_EXPECTED_CHECKPOINT_SHA256;
  delete process.env.MOGE_EXPECTED_CODE_REVISION;
  delete process.env.MOGE_EXPECTED_CHECKPOINT_SHA256;
  assert.throws(() => validateConventionSidecar(sidecar), /must be configured/);
  process.env.MOGE_EXPECTED_CODE_REVISION = codeRevision;
  process.env.MOGE_EXPECTED_CHECKPOINT_SHA256 = checkpointSha256;
  assert.throws(() => validateConventionSidecar(sidecar, 'c'.repeat(64), imageSha256), /not bound/);
  assert.throws(() => validateConventionSidecar(sidecar, glbSha256, 'c'.repeat(64)), /not bound/);
  assert.throws(() => validateConventionSidecar({
    ...sidecar,
    provenance: { ...sidecar.provenance, codeRevision: 'c'.repeat(40) },
  }), /provenance does not match the configured pin/);
  assert.throws(() => validateConventionSidecar({
    ...sidecar,
    canonicalOrientation: { ...sidecar.canonicalOrientation, exifOrientation: 6 },
  }), /canonical input image orientation/);
  if (oldRevision === undefined) delete process.env.MOGE_EXPECTED_CODE_REVISION;
  else process.env.MOGE_EXPECTED_CODE_REVISION = oldRevision;
  if (oldCheckpoint === undefined) delete process.env.MOGE_EXPECTED_CHECKPOINT_SHA256;
  else process.env.MOGE_EXPECTED_CHECKPOINT_SHA256 = oldCheckpoint;
});

test('keeps frame paths isolated by both system session and frame ID', () => {
  const first = frameDir(systemSessionId, frameId);
  const second = frameDir(systemSessionId, 'frame_002');
  const otherSession = frameDir('fedcba9876543210fedcba9876543210', frameId);
  assert.notEqual(first, second);
  assert.notEqual(first, otherSession);
  assert.equal(path.basename(first), frameId);
  assert.throws(() => frameDir(systemSessionId, '../escape'), /Invalid frameId/);
});

test('bounds worker retries and makes an exhausted frame terminal', () => {
  assert.equal(retryStatus(1), 'queued');
  assert.equal(retryStatus(2), 'queued');
  assert.equal(retryStatus(3), 'failed');
  assert.equal(retryStatus(-1), 'failed');
});
