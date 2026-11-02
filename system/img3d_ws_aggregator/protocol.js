'use strict';

const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const SESSION_ID = /^[a-f0-9]{32}$/;
const REQUEST_ID = /^[a-f0-9]{32}$/;
const FRAME_ID = /^[A-Za-z0-9_-]{1,96}$/;
const SHA256 = /^[a-f0-9]{64}$/;
const MAX_GLB_BYTES = 512 * 1024 * 1024;
const MAX_METADATA_BYTES = 1024 * 1024;

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (isPlainObject(value)) {
    return `{${Object.keys(value).sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex');
}

function validGlb(buffer) {
  return Buffer.isBuffer(buffer) && buffer.length >= 20 && buffer.length <= MAX_GLB_BYTES
    && buffer.subarray(0, 4).toString('ascii') === 'glTF'
    && buffer.readUInt32LE(4) === 2
    && buffer.readUInt32LE(8) === buffer.length;
}

function identityPose(frame) {
  const pose = frame.cameraToFirstFrame;
  return pose && Array.isArray(pose.translationM) && pose.translationM.length === 3
    && Array.isArray(pose.rotationQuaternionXyzw) && pose.rotationQuaternionXyzw.length === 4
    && pose.translationM.every((value) => Number.isFinite(value) && Math.abs(value) <= 0.001)
    && pose.rotationQuaternionXyzw.slice(0, 3).every((value) => Number.isFinite(value) && Math.abs(value) <= 0.001)
    && Number.isFinite(pose.rotationQuaternionXyzw[3])
    && Math.abs(Math.abs(pose.rotationQuaternionXyzw[3]) - 1) <= 0.001;
}

function validRelativePath(relative, expectedPrefix) {
  if (typeof relative !== 'string' || relative.includes('\\') || path.posix.isAbsolute(relative)
    || relative.split('/').some((part) => part === '..' || part === '' || part === '.')) return false;
  return relative.startsWith(expectedPrefix);
}

function validateMetadata(metadata, expected) {
  if (!isPlainObject(metadata) || metadata.schemaVersion !== 1
    || metadata.requestId !== expected.requestId
    || metadata.systemSessionId !== expected.systemSessionId
    || metadata.frameId !== expected.frameId
    || !Number.isSafeInteger(metadata.sequence) || metadata.sequence < 0
    || metadata.sequence !== expected.sequence
    || !SHA256.test(metadata.inputGlbSha256 || '')
    || metadata.inputGlbSha256 !== expected.inputGlbSha256
    || !Array.isArray(metadata.frames) || metadata.frames.length < 1 || metadata.frames.length > 500) {
    throw new Error('Aggregation metadata does not match the authenticated request envelope.');
  }
  const inputPrefix = `system-sessions/${expected.systemSessionId}/outbox/${expected.requestId}/`;
  if (metadata.inputGlbPath !== `${inputPrefix}input.glb`
    || !validRelativePath(metadata.inputGlbPath, inputPrefix)) {
    throw new Error('Aggregation input path is not a request-local DATA_DIR path.');
  }
  const seen = new Set();
  const seenSequences = new Set();
  let hasCurrentFrame = false;
  for (const frame of metadata.frames) {
    const pose = frame && frame.cameraToFirstFrame;
    const poseKeys = isPlainObject(pose) ? Object.keys(pose).sort() : [];
    if (!isPlainObject(frame) || !FRAME_ID.test(frame.frameId || '')
      || !Number.isSafeInteger(frame.sequence) || frame.sequence < 0
      || seen.has(frame.frameId) || seenSequences.has(frame.sequence)
      || !isPlainObject(pose) || poseKeys.join(',') !== 'rotationQuaternionXyzw,translationM'
      || !Array.isArray(pose.translationM) || pose.translationM.length !== 3
      || !pose.translationM.every((value) => Number.isFinite(value) && Math.abs(value) <= 1000000)
      || !Array.isArray(pose.rotationQuaternionXyzw) || pose.rotationQuaternionXyzw.length !== 4
      || !pose.rotationQuaternionXyzw.every((value) => Number.isFinite(value) && Math.abs(value) <= 1.001)
      || Math.abs(Math.hypot(...pose.rotationQuaternionXyzw) - 1) > 0.001) {
      throw new Error('Aggregation frame metadata contains invalid identifiers or pose values.');
    }
    const framePrefix = `system-sessions/${expected.systemSessionId}/frames/${frame.frameId}/`;
    if (!validRelativePath(frame.glbPath, framePrefix)
      || !validRelativePath(frame.conventionSidecarPath, framePrefix)) {
      throw new Error('Aggregation frame path is outside the expected session/frame directory.');
    }
    if (!/\/frame\.attempt-[1-9][0-9]*\.glb$/.test(frame.glbPath)
      || frame.conventionSidecarPath !== `${frame.glbPath}.convention.json`) {
      throw new Error('Frame GLB and adjacent convention-sidecar filenames are invalid.');
    }
    if (frame.sequence === 0 && !identityPose({
      cameraToFirstFrame: pose,
    })) {
      throw new Error('Sequence 0 must have the identity cameraToFirstFrame pose.');
    }
    if (frame.frameId === expected.frameId && frame.sequence === expected.sequence) hasCurrentFrame = true;
    seen.add(frame.frameId);
    seenSequences.add(frame.sequence);
  }
  if (!hasCurrentFrame) throw new Error('Aggregation metadata must include its current frame.');
  const metadataBytes = Buffer.from(canonicalJson(metadata), 'utf8');
  if (metadataBytes.length > MAX_METADATA_BYTES || sha256(metadataBytes) !== expected.metadataSha256) {
    throw new Error('Aggregation metadata integrity check failed.');
  }
  return metadata;
}

function ensureInside(parent, target) {
  const relative = path.relative(parent, target);
  if (relative === '' || relative.startsWith(`..${path.sep}`) || relative === '..' || path.isAbsolute(relative)) {
    throw new Error('Aggregator storage path escaped DATA_DIR.');
  }
}

function requestDirectory(dataDir, systemSessionId, requestId) {
  if (!SESSION_ID.test(systemSessionId || '') || !REQUEST_ID.test(requestId || '')) {
    throw new Error('Invalid systemSessionId/requestId.');
  }
  const root = path.resolve(dataDir, 'system-sessions');
  const session = path.resolve(root, systemSessionId);
  const destination = path.resolve(session, 'aggregator-inbox', requestId);
  ensureInside(root, session);
  ensureInside(session, destination);
  return { root, session, destination };
}

function durableWrite(filePath, data) {
  const temporary = `${filePath}.${process.pid}.${crypto.randomUUID()}.tmp`;
  const descriptor = fs.openSync(temporary, 'wx', 0o600);
  try {
    fs.writeFileSync(descriptor, data);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  fs.renameSync(temporary, filePath);
  syncDirectory(path.dirname(filePath));
}

function syncDirectory(directory) {
  if (process.platform === 'win32') return;
  let descriptor;
  try {
    descriptor = fs.openSync(directory, 'r');
    fs.fsyncSync(descriptor);
  } catch (error) {
    if (!['EINVAL', 'EISDIR', 'EPERM', 'ENOTSUP'].includes(error.code)) throw error;
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
}

function lstatIfPresent(filePath) {
  try { return fs.lstatSync(filePath); } catch (error) {
    if (error.code === 'ENOENT') return null;
    throw error;
  }
}

function currentConventionSidecar(dataDir, metadata, inputHash) {
  const frame = metadata.frames.find((entry) =>
    entry.frameId === metadata.frameId && entry.sequence === metadata.sequence);
  if (!frame) throw new Error('Current frame is absent from the publisher manifest.');
  const expectedFrameDirectory = `system-sessions/${metadata.systemSessionId}/frames/${metadata.frameId}/`;
  if (!validRelativePath(frame.conventionSidecarPath, expectedFrameDirectory)
    || !/\/frame\.attempt-[1-9][0-9]*\.glb\.convention\.json$/.test(frame.conventionSidecarPath)) {
    throw new Error('Current convention sidecar path is invalid.');
  }
  const dataRoot = fs.realpathSync(path.resolve(dataDir));
  const frameDirectory = path.resolve(dataRoot, 'system-sessions', metadata.systemSessionId, 'frames', metadata.frameId);
  const systemSessionsPath = path.join(dataRoot, 'system-sessions');
  if (!fs.lstatSync(systemSessionsPath).isDirectory() || fs.lstatSync(systemSessionsPath).isSymbolicLink()) {
    throw new Error('system-sessions storage root is not a regular directory.');
  }
  const systemSessions = fs.realpathSync(systemSessionsPath);
  const sessionDirectory = path.join(systemSessions, metadata.systemSessionId);
  if (fs.lstatSync(sessionDirectory).isSymbolicLink()
    || path.dirname(fs.realpathSync(sessionDirectory)) !== systemSessions) {
    throw new Error('Current system session directory escaped DATA_DIR.');
  }
  const framesDirectory = path.join(sessionDirectory, 'frames');
  if (fs.lstatSync(framesDirectory).isSymbolicLink()
    || path.dirname(fs.realpathSync(framesDirectory)) !== fs.realpathSync(sessionDirectory)) {
    throw new Error('Current frame root escaped its system session.');
  }
  if (fs.lstatSync(frameDirectory).isSymbolicLink()) throw new Error('Current frame directory is a symlink.');
  const realFrameDirectory = fs.realpathSync(frameDirectory);
  if (path.dirname(realFrameDirectory) !== fs.realpathSync(framesDirectory)) {
    throw new Error('Current frame directory escaped the session frames root.');
  }
  const sidecarPath = path.resolve(dataRoot, ...frame.conventionSidecarPath.split('/'));
  const stat = fs.lstatSync(sidecarPath);
  if (!stat.isFile() || stat.size < 1 || stat.size > 64 * 1024
    || path.dirname(fs.realpathSync(sidecarPath)) !== realFrameDirectory) {
    throw new Error('Current convention sidecar is missing, oversized, or outside the frame directory.');
  }
  const bytes = fs.readFileSync(sidecarPath);
  const sidecar = JSON.parse(bytes.toString('utf8'));
  if (!isPlainObject(sidecar) || sidecar.schemaVersion !== 1 || sidecar.glbSha256 !== inputHash) {
    throw new Error('Current convention sidecar is not bound to the staged GLB.');
  }
  return bytes;
}

function stageRequest(dataDir, envelope, metadata, input) {
  if (!validGlb(input) || input.length !== envelope.size
    || sha256(input) !== envelope.inputGlbSha256) {
    throw new Error('Aggregator GLB failed size, header, or SHA-256 verification.');
  }
  validateMetadata(metadata, envelope);
  const { root, session, destination } = requestDirectory(
    dataDir, envelope.systemSessionId, envelope.requestId,
  );
  const rootStat = lstatIfPresent(root);
  const sessionStat = lstatIfPresent(session);
  if (!rootStat || !rootStat.isDirectory() || rootStat.isSymbolicLink()
    || !sessionStat || !sessionStat.isDirectory() || sessionStat.isSymbolicLink()) {
    throw new Error('System session storage is missing or is a symlink.');
  }
  const realRoot = fs.realpathSync(root);
  const realSession = fs.realpathSync(session);
  ensureInside(realRoot, realSession);
  const inboxParent = path.dirname(destination);
  const inboxParentStat = lstatIfPresent(inboxParent);
  if (inboxParentStat && (!inboxParentStat.isDirectory() || inboxParentStat.isSymbolicLink())) {
    throw new Error('Aggregator inbox parent is a symlink.');
  }
  fs.mkdirSync(inboxParent, { recursive: true, mode: 0o750 });
  syncDirectory(realSession);
  if (path.dirname(fs.realpathSync(inboxParent)) !== realSession) {
    throw new Error('Aggregator inbox directory escaped the session storage root.');
  }
  const destinationStat = lstatIfPresent(destination);
  if (destinationStat) {
    if (!destinationStat.isDirectory() || destinationStat.isSymbolicLink()) {
      throw new Error('Aggregator inbox request path is not a regular directory.');
    }
    const statePath = path.join(destination, 'state.json');
    const inputPath = path.join(destination, 'input.glb');
    const stateStat = fs.lstatSync(statePath);
    const inputStat = fs.lstatSync(inputPath);
    if (!stateStat.isFile() || stateStat.size > 64 * 1024
      || !inputStat.isFile() || inputStat.size > MAX_GLB_BYTES) {
      throw new Error('Previously staged request files are not regular files.');
    }
    const state = JSON.parse(fs.readFileSync(statePath, 'utf8'));
    if (state.requestId !== envelope.requestId
      || state.systemSessionId !== envelope.systemSessionId
      || state.frameId !== envelope.frameId
      || state.sequence !== envelope.sequence
      || state.inputGlbSha256 !== envelope.inputGlbSha256
      || state.metadataSha256 !== envelope.metadataSha256
      || !['durable-accepted', 'publishing', 'committed', 'rejected'].includes(state.status)
      || (state.status === 'committed'
        && (!Number.isSafeInteger(state.version) || state.version < 1 || state.version > 999999999))
      || (state.status === 'rejected' && typeof state.error !== 'string')) {
      throw new Error('requestId was replayed with different bytes or metadata.');
    }
    const saved = fs.readFileSync(inputPath);
    if (!validGlb(saved) || sha256(saved) !== envelope.inputGlbSha256) {
      throw new Error('Previously staged input failed integrity verification.');
    }
    const sidecarPath = path.join(destination, 'input.glb.convention.json');
    const sidecarStat = fs.lstatSync(sidecarPath);
    if (!sidecarStat.isFile() || sidecarStat.size > 64 * 1024) {
      throw new Error('Previously staged convention sidecar is not a regular bounded file.');
    }
    const savedSidecar = fs.readFileSync(sidecarPath);
    if (sha256(savedSidecar) !== state.conventionSidecarSha256) {
      throw new Error('Previously staged convention sidecar failed integrity verification.');
    }
    if (JSON.parse(savedSidecar.toString('utf8')).glbSha256 !== envelope.inputGlbSha256) {
      throw new Error('Previously staged convention sidecar is not bound to the input GLB.');
    }
    return { destination, state, duplicate: true };
  }
  const sidecarBytes = currentConventionSidecar(dataDir, metadata, envelope.inputGlbSha256);
  const temporaryDirectory = `${destination}.${process.pid}.${crypto.randomUUID()}.tmp`;
  fs.mkdirSync(temporaryDirectory, { mode: 0o750 });
  try {
    durableWrite(path.join(temporaryDirectory, 'input.glb'), input);
    durableWrite(path.join(temporaryDirectory, 'input.glb.convention.json'), sidecarBytes);
    durableWrite(path.join(temporaryDirectory, 'request.json'), Buffer.from(canonicalJson(metadata), 'utf8'));
    const state = {
      requestId: envelope.requestId,
      systemSessionId: envelope.systemSessionId,
      frameId: envelope.frameId,
      sequence: envelope.sequence,
      inputGlbSha256: envelope.inputGlbSha256,
      metadataSha256: envelope.metadataSha256,
      conventionSidecarSha256: sha256(sidecarBytes),
      status: 'durable-accepted',
      createdAt: Date.now(),
    };
    durableWrite(path.join(temporaryDirectory, 'state.json'), Buffer.from(JSON.stringify(state, null, 2)));
    syncDirectory(temporaryDirectory);
    fs.renameSync(temporaryDirectory, destination);
    syncDirectory(inboxParent);
    return { destination, state, duplicate: false };
  } catch (error) {
    fs.rmSync(temporaryDirectory, { recursive: true, force: true });
    throw error;
  }
}

module.exports = {
  MAX_GLB_BYTES,
  REQUEST_ID,
  SESSION_ID,
  FRAME_ID,
  canonicalJson,
  sha256,
  validGlb,
  validateMetadata,
  requestDirectory,
  durableWrite,
  syncDirectory,
  lstatIfPresent,
  currentConventionSidecar,
  stageRequest,
};
