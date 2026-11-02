'use strict';

const {
  fs, path, crypto, DATA_DIR, log, logError,
} = require('./config');

const ROOT = path.join(DATA_DIR, 'system-sessions');
const FRAME_ID = /^[A-Za-z0-9_-]{1,96}$/;
const SESSION_ID = /^[a-f0-9]{32}$/;
const MAX_ATTEMPTS = 3;
const CONVENTION_ID = 'moge3-v3-metric-opencv-camera-legacy-glb';
const VERIFIED_CODE_REVISION = '74fbce054ebed49800de42d0ad0e83495065719a';
const PROVENANCE_METHOD = 'pinned-source-git-revision+configured-checkpoint-sha256';
const ORIENTATION_METHOD = 'EXIF orientation absent or 1; source pixels used without rotation or mirroring';
const FIXED_CONVENTION_MATRIX = [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, 0, 0, 0, 1];
const FIXED_BASIS = {
  moge: 'opencv-camera,+X-right,+Y-down,+Z-forward',
  storedGlb: 'legacy-export-F-applied-to-MoGe',
  captureCamera: 'arcore-opengl,+X-right,+Y-up,-Z-forward',
  world: 'right-handed,+X-right,+Y-up,-Z-forward',
};
let scheduleScan = () => {};
let sessionCursor = 0;

function agentPool() {
  return require('./agents');
}

function configureScan(callback) {
  scheduleScan = callback;
}

function readJson(file) {
  try {
    const stat = fs.lstatSync(file);
    if (!stat.isFile() || stat.size > 512 * 1024) return null;
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (_) {
    return null;
  }
}

function writeJson(file, value) {
  const temporary = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
  const descriptor = fs.openSync(temporary, 'wx', 0o600);
  try {
    fs.writeFileSync(descriptor, JSON.stringify(value, null, 2), 'utf8');
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  fs.renameSync(temporary, file);
  syncDirectory(path.dirname(file));
}

function writeBinaryAtomic(file, buffer) {
  const temporary = `${file}.${process.pid}.${crypto.randomUUID()}.tmp`;
  const descriptor = fs.openSync(temporary, 'wx', 0o600);
  try {
    fs.writeFileSync(descriptor, buffer);
    fs.fsyncSync(descriptor);
  } finally {
    fs.closeSync(descriptor);
  }
  fs.renameSync(temporary, file);
  syncDirectory(path.dirname(file));
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

function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function sessionDir(systemSessionId) {
  if (!SESSION_ID.test(systemSessionId || '')) throw new Error('Invalid systemSessionId');
  const directory = path.join(ROOT, systemSessionId);
  if (fs.existsSync(directory)) {
    if (fs.lstatSync(directory).isSymbolicLink()) throw new Error('System session directory is a symlink');
    const rootReal = fs.realpathSync(ROOT);
    const directoryReal = fs.realpathSync(directory);
    if (path.dirname(directoryReal) !== rootReal) throw new Error('System session path escaped storage root');
  }
  return directory;
}

function frameDir(systemSessionId, frameId) {
  if (!FRAME_ID.test(frameId || '')) throw new Error('Invalid frameId');
  const directory = path.join(sessionDir(systemSessionId), 'frames', frameId);
  if (fs.existsSync(directory)) {
    if (fs.lstatSync(directory).isSymbolicLink()) throw new Error('Frame directory is a symlink');
    const sessionReal = fs.realpathSync(sessionDir(systemSessionId));
    const framesReal = fs.realpathSync(path.join(sessionDir(systemSessionId), 'frames'));
    const directoryReal = fs.realpathSync(directory);
    if (path.dirname(framesReal) !== sessionReal || path.basename(framesReal) !== 'frames') {
      throw new Error('Frame root escaped system session storage');
    }
    if (path.dirname(directoryReal) !== framesReal) throw new Error('Frame path escaped storage root');
  }
  return directory;
}

function frameJsonPath(systemSessionId, frameId) {
  return path.join(frameDir(systemSessionId, frameId), 'frame.json');
}

function updateSessionProgress(directory, statusOverride) {
  const sessionFile = path.join(directory, 'session.json');
  const session = readJson(sessionFile);
  if (!session) return;
  const framesRoot = path.join(directory, 'frames');
  let total = 0;
  let completed = 0;
  let pending = 0;
  let working = 0;
  let failed = 0;
  for (const name of safeReadDir(framesRoot)) {
    const record = readJson(path.join(framesRoot, name, 'frame.json'));
    if (!record) continue;
    total += 1;
    if (record.status === 'complete') completed += 1;
    else if (record.status === 'queued') pending += 1;
    else if (record.status === 'processing' || record.status === 'aggregator_pending'
      || record.status === 'aggregating') working += 1;
    else if (record.status === 'failed') failed += 1;
  }
  const status = statusOverride || (failed ? 'error' : session.acceptingFrames
    ? (working ? 'processing' : pending ? 'queued' : completed ? 'ready' : 'collecting')
    : (pending || working) ? 'closing' : 'complete');
  writeJson(path.join(directory, 'status.json'), {
    status, progress: total ? Math.floor(completed * 100 / total) : 0,
    completedFrames: completed, pendingFrames: pending, processingFrames: working,
    failedFrames: failed, totalFrames: total,
    currentVersion: (readJson(path.join(directory, 'current-version.json')) || {}).currentVersion || 0,
  });
}

function safeReadDir(directory) {
  try {
    if (!fs.lstatSync(directory).isDirectory()) return [];
    return fs.readdirSync(directory, { withFileTypes: true })
      .filter((entry) => entry.isDirectory()).map((entry) => entry.name);
  } catch (_) {
    return [];
  }
}

function scanPending(systemJobs) {
  reconcileOutbox();
  if (!fs.existsSync(ROOT)) return;
  const { getIdleAgent } = agentPool();
  const sessions = safeReadDir(ROOT).filter((name) => SESSION_ID.test(name)).sort();
  if (!sessions.length) return;
  let offset = sessionCursor % sessions.length;
  const attempted = new Set();
  while (true) {
    const available = getIdleAgent();
    if (!available) return;
    let selected = null;
    let selectedIndex = -1;
    for (let step = 0; step < sessions.length; step += 1) {
      const index = (offset + step) % sessions.length;
      const systemSessionId = sessions[index];
      const directory = sessionDir(systemSessionId);
      const session = readJson(path.join(directory, 'session.json'));
      if (!session || session.systemSessionId !== systemSessionId) continue;
      const records = safeReadDir(path.join(directory, 'frames'))
        .filter((name) => FRAME_ID.test(name))
        .map((frameId) => ({ frameId, record: readJson(frameJsonPath(systemSessionId, frameId)) }))
        .filter((item) => item.record && item.record.frameId === item.frameId
          && Number.isSafeInteger(item.record.sequence) && item.record.sequence >= 0);
      for (const item of records) {
        if (item.record.status === 'processing'
          && !systemJobsHasFrame(systemJobs, systemSessionId, item.frameId)) {
          item.record.status = retryStatus(item.record.attempts || 0);
          item.record.progress = 0;
          item.record.lastError = 'Recovered a worker job without a live broker assignment.';
          if (item.record.status === 'failed') {
            item.record.error = 'Worker retry limit reached before the server restarted.';
          }
          writeJson(frameJsonPath(systemSessionId, item.frameId), item.record);
        }
      }
      if (records.some((item) => item.record.status === 'failed')) {
        updateSessionProgress(directory, 'error');
        continue;
      }
      const candidates = records
        .filter((item) => item.record.status === 'queued'
          && !attempted.has(`${systemSessionId}/${item.frameId}`))
        .sort((a, b) => a.record.sequence - b.record.sequence);
      if (candidates.length) {
        selected = { systemSessionId, frameId: candidates[0].frameId, record: candidates[0].record };
        selectedIndex = index;
        break;
      }
      updateSessionProgress(directory);
    }
    if (!selected) return;
    attempted.add(`${selected.systemSessionId}/${selected.frameId}`);
    const success = dispatchFrame(selected.systemSessionId, selected.frameId, selected.record,
      available.agentId, available.agent, systemJobs);
    offset = (selectedIndex + 1) % sessions.length;
    sessionCursor = offset;
    // Send failures are attempted only once per scan; later events may retry.
    if (!success) continue;
  }
}

function systemJobsHasFrame(systemJobs, systemSessionId, frameId) {
  for (const job of systemJobs.values()) {
    if (job.jobType === 'system_frame'
      && job.systemSessionId === systemSessionId && job.frameId === frameId) return true;
  }
  return false;
}

function dispatchFrame(systemSessionId, frameId, record, agentId, agent, systemJobs) {
  const directory = sessionDir(systemSessionId);
  const dir = frameDir(systemSessionId, frameId);
  if (!/^(image\.(jpg|jpeg|png|webp))$/.test(record.imageFile || '')
    || !/^[a-f0-9]{64}$/.test(record.sha256 || '')) {
    record.status = 'failed';
    record.error = 'Frame storage metadata is invalid.';
    writeJson(frameJsonPath(systemSessionId, frameId), record);
    updateSessionProgress(directory);
    return false;
  }
  const file = path.join(dir, record.imageFile);
  if (!fs.existsSync(file) || !fs.lstatSync(file).isFile()) {
    record.status = 'failed';
    record.error = 'Uploaded frame image is missing from shared storage.';
    writeJson(frameJsonPath(systemSessionId, frameId), record);
    updateSessionProgress(directory);
    return false;
  }
  const jobId = crypto.randomUUID();
  const job = {
    jobId, jobType: 'system_frame', systemSessionId, frameId, agentId,
    attempts: (record.attempts || 0) + 1,
  };
  systemJobs.set(jobId, job);
  agent.busy = true;
  agent.jobId = jobId;
  record.status = 'processing';
  record.progress = 0;
  record.attempts = job.attempts;
  record.startedAt = Date.now();
  delete record.error;
  writeJson(frameJsonPath(systemSessionId, frameId), record);
  updateSessionProgress(directory);
  try {
    const image = fs.readFileSync(file);
    const realDir = fs.realpathSync(dir);
    const realFile = fs.realpathSync(file);
    if (path.dirname(realFile) !== realDir || image.length < 1 || image.length > 20 * 1024 * 1024
      || crypto.createHash('sha256').update(image).digest('hex') !== record.sha256) {
      throw new Error('Stored frame failed path, size, or SHA-256 verification.');
    }
    const extension = path.extname(record.imageFile).toLowerCase();
    agent.ws.send(JSON.stringify({
      type: 'job',
      jobType: 'system_frame',
      jobId,
      systemSessionId,
      frameId,
      filename: `${frameId}${extension}`,
      size: image.length,
      sha256: record.sha256,
    }));
    agent.ws.send(image, { binary: true });
    log(`Dispatched system frame ${systemSessionId}/${frameId} to agent ${agentId}.`);
    return true;
  } catch (error) {
    systemJobs.delete(jobId);
    agent.busy = false;
    agent.jobId = null;
    retryFrame(job, systemJobs, `Unable to send frame: ${error.message}`);
    return false;
  }
}

function retryFrame(job, systemJobs, reason) {
  const file = frameJsonPath(job.systemSessionId, job.frameId);
  const record = readJson(file);
  if (!record || record.status === 'complete') return;
  record.status = retryStatus(record.attempts || 0);
  if (record.status === 'queued') {
    record.progress = 0;
    record.lastError = reason;
  } else {
    record.error = `Frame processing exhausted retries: ${reason}`;
  }
  writeJson(file, record);
  updateSessionProgress(sessionDir(job.systemSessionId));
  setImmediate(scheduleScan);
}

function retryStatus(attempts) {
  return Number.isInteger(attempts) && attempts >= 0 && attempts < MAX_ATTEMPTS
    ? 'queued'
    : 'failed';
}

function updateProgress(job, progress, details = {}) {
  const file = frameJsonPath(job.systemSessionId, job.frameId);
  const record = readJson(file);
  if (!record || record.status !== 'processing') return;
  record.progress = progress;
  if (typeof details.stage === 'string') record.stage = details.stage.slice(0, 100);
  if (typeof details.text === 'string') record.message = details.text.slice(0, 500);
  writeJson(file, record);
  updateSessionProgress(sessionDir(job.systemSessionId));
}

function validGlb(buffer) {
  return Buffer.isBuffer(buffer) && buffer.length >= 20
    && buffer.length <= 512 * 1024 * 1024
    && buffer.subarray(0, 4).toString('ascii') === 'glTF'
    && buffer.readUInt32LE(4) === 2
    && buffer.readUInt32LE(8) === buffer.length;
}

function isPlainObject(value) {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function hasExactKeys(value, keys) {
  return isPlainObject(value)
    && Object.keys(value).sort().join(',') === [...keys].sort().join(',');
}

function validateCaptureTransform(frameId, record) {
  if (!Object.hasOwn(record, 'orientation')) {
    throw new Error(`Frame ${frameId} is missing capture orientation metadata.`);
  }
  if (record.orientation !== 0) {
    throw new Error(`Frame ${frameId} declares unsupported capture orientation; aggregation supports orientation=0 only.`);
  }

  const transform = record.imageTransform;
  if (!hasExactKeys(transform, [
    'sourceWidth', 'sourceHeight', 'rotationDegrees', 'mirrorX', 'crop',
  ])) {
    throw new Error(`Frame ${frameId} is missing or has unknown imageTransform metadata.`);
  }
  if (!Number.isSafeInteger(record.width) || !Number.isSafeInteger(record.height)
    || transform.sourceWidth !== record.width || transform.sourceHeight !== record.height) {
    throw new Error(`Frame ${frameId} imageTransform source dimensions must match the uploaded image dimensions.`);
  }
  if (transform.rotationDegrees !== 0) {
    throw new Error(`Frame ${frameId} declares unsupported imageTransform.rotationDegrees; aggregation supports 0 only.`);
  }
  if (transform.mirrorX !== false) {
    throw new Error(`Frame ${frameId} declares unsupported imageTransform.mirrorX; aggregation supports false only.`);
  }
  if (!hasExactKeys(transform.crop, ['x', 'y', 'width', 'height'])) {
    throw new Error(`Frame ${frameId} is missing or has unknown imageTransform.crop metadata.`);
  }
  if (transform.crop.x !== 0 || transform.crop.y !== 0
    || transform.crop.width !== 1 || transform.crop.height !== 1) {
    throw new Error(`Frame ${frameId} declares unsupported imageTransform.crop; aggregation supports the full frame only.`);
  }
}

function validateConventionSidecar(sidecar, expectedGlbSha256, expectedImageSha256) {
  const expectedCheckpoint = (process.env.MOGE_EXPECTED_CHECKPOINT_SHA256 || '').trim().toLowerCase();
  const configuredRevision = (process.env.MOGE_EXPECTED_CODE_REVISION || '').trim().toLowerCase();
  if (configuredRevision !== VERIFIED_CODE_REVISION
    || !/^[a-f0-9]{64}$/.test(expectedCheckpoint)) {
    throw new Error('Trusted MoGe code revision and checkpoint SHA-256 must be configured on Node.');
  }
  if (!hasExactKeys(sidecar, [
    'schemaVersion', 'conventionId', 'basis', 'glbStoredToMogeMatrix4x4',
    'mogeToCaptureCameraMatrix4x4', 'scale', 'unit', 'provenance',
    'canonicalOrientation', 'glbSha256',
  ])) {
    throw new Error('Worker convention sidecar has an unsupported schema.');
  }
  if (sidecar.schemaVersion !== 1 || sidecar.conventionId !== CONVENTION_ID
    || !hasExactKeys(sidecar.basis, ['moge', 'storedGlb', 'captureCamera', 'world'])
    || sidecar.basis.moge !== FIXED_BASIS.moge
    || sidecar.basis.storedGlb !== FIXED_BASIS.storedGlb
    || sidecar.basis.captureCamera !== FIXED_BASIS.captureCamera
    || sidecar.basis.world !== FIXED_BASIS.world
    || !Array.isArray(sidecar.glbStoredToMogeMatrix4x4)
    || !Array.isArray(sidecar.mogeToCaptureCameraMatrix4x4)
    || sidecar.glbStoredToMogeMatrix4x4.length !== 16
    || sidecar.mogeToCaptureCameraMatrix4x4.length !== 16
    || sidecar.glbStoredToMogeMatrix4x4.some((value, index) => value !== FIXED_CONVENTION_MATRIX[index])
    || sidecar.mogeToCaptureCameraMatrix4x4.some((value, index) => value !== FIXED_CONVENTION_MATRIX[index])
    || sidecar.scale !== 1.0 || sidecar.unit !== 'm') {
    throw new Error('Worker convention sidecar does not declare the supported fixed metric basis.');
  }
  const provenance = sidecar.provenance;
  if (!hasExactKeys(provenance, ['modelVersion', 'codeRevision', 'checkpointSha256', 'verification'])
    || provenance.modelVersion !== 'v3'
    || provenance.codeRevision !== configuredRevision
    || provenance.checkpointSha256 !== expectedCheckpoint
    || provenance.verification !== PROVENANCE_METHOD) {
    throw new Error('Worker convention sidecar MoGe provenance does not match the configured pin.');
  }
  const orientation = sidecar.canonicalOrientation;
  if (!hasExactKeys(orientation, ['verified', 'method', 'exifOrientation', 'imageSha256'])
    || orientation.verified !== true || orientation.method !== ORIENTATION_METHOD
    || (orientation.exifOrientation !== null && orientation.exifOrientation !== 1)
    || !/^[a-f0-9]{64}$/.test(orientation.imageSha256)) {
    throw new Error('Worker sidecar does not verify canonical input image orientation.');
  }
  if (!/^[a-f0-9]{64}$/.test(sidecar.glbSha256)
    || (expectedGlbSha256 && sidecar.glbSha256 !== expectedGlbSha256)
    || (expectedImageSha256 && orientation.imageSha256 !== expectedImageSha256)) {
    throw new Error('Worker convention sidecar is not bound to the exact frame GLB and uploaded image.');
  }
  return sidecar;
}

function readFrameConvention(glbPath, record) {
  const sidecarPath = `${glbPath}.convention.json`;
  const stat = fs.lstatSync(sidecarPath);
  if (!stat.isFile() || stat.size < 1 || stat.size > 64 * 1024) {
    throw new Error(`Frame convention sidecar is missing or oversized: ${sidecarPath}`);
  }
  const glbStat = fs.lstatSync(glbPath);
  if (!glbStat.isFile()) throw new Error(`Frame GLB is not a regular file: ${glbPath}`);
  if (path.dirname(fs.realpathSync(sidecarPath)) !== path.dirname(fs.realpathSync(glbPath))) {
    throw new Error(`Frame convention sidecar is not adjacent to its GLB: ${sidecarPath}`);
  }
  const sidecar = readJson(sidecarPath);
  if (!sidecar) throw new Error(`Frame convention sidecar is invalid JSON: ${sidecarPath}`);
  const glb = fs.readFileSync(glbPath);
  if (!validGlb(glb)) throw new Error(`Frame GLB is invalid: ${glbPath}`);
  const glbHash = crypto.createHash('sha256').update(glb).digest('hex');
  validateConventionSidecar(sidecar, glbHash, record.sha256);
  return sidecarPath;
}

function manifestFrame(frameId, record, glbPath) {
  validateCaptureTransform(frameId, record);
  if (!/^frame\.attempt-[1-9][0-9]*\.glb$/.test(path.basename(glbPath))) {
    throw new Error(`Frame ${frameId} has an invalid stored GLB filename.`);
  }
  if (Object.hasOwn(record, 'cameraToSystemSessionFrame')) {
    throw new Error(`Frame ${frameId} uses ambiguous legacy cameraToSystemSessionFrame metadata.`);
  }
  const pose = record.cameraToFirstFrame;
  const poseKeys = pose && typeof pose === 'object' && !Array.isArray(pose)
    ? Object.keys(pose).sort().join(',') : '';
  if (!pose || !Array.isArray(pose.translationM) || pose.translationM.length !== 3
    || !pose.translationM.every((value) => Number.isFinite(value) && Math.abs(value) <= 1000000)
    || !Array.isArray(pose.rotationQuaternionXyzw) || pose.rotationQuaternionXyzw.length !== 4
    || !pose.rotationQuaternionXyzw.every((value) => Number.isFinite(value) && Math.abs(value) <= 1.001)
    || poseKeys !== 'rotationQuaternionXyzw,translationM'
    || Math.abs(Math.hypot(...pose.rotationQuaternionXyzw) - 1) > 0.001) {
    throw new Error(`Frame ${frameId} is missing a valid cameraToFirstFrame pose.`);
  }
  if (record.sequence === 0
    && (pose.translationM.some((value) => Math.abs(value) > 0.001)
      || pose.rotationQuaternionXyzw.slice(0, 3).some((value) => Math.abs(value) > 0.001)
      || Math.abs(Math.abs(pose.rotationQuaternionXyzw[3]) - 1) > 0.001)) {
    throw new Error('Sequence 0 must define the identity cameraToFirstFrame pose.');
  }
  const conventionSidecarPath = readFrameConvention(glbPath, record);
  return {
    frameId: record.frameId,
    sequence: record.sequence,
    glbPath,
    cameraToFirstFrame: {
      translationM: pose.translationM,
      rotationQuaternionXyzw: pose.rotationQuaternionXyzw,
    },
    conventionSidecarPath,
  };
}

function notifyAgent(agent, message) {
  if (!agent || !agent.ws || agent.ws.readyState !== 1) return;
  try {
    agent.ws.send(JSON.stringify(message));
  } catch (error) {
    logError('Worker notification failed:', error.message);
  }
}

function outboxPath(systemSessionId, requestId) {
  if (!/^[a-f0-9]{32}$/.test(requestId || '')) throw new Error('Invalid aggregation requestId');
  const session = sessionDir(systemSessionId);
  const outbox = path.join(session, 'outbox');
  const request = path.join(outbox, requestId);
  if (fs.existsSync(outbox)) {
    if (fs.lstatSync(outbox).isSymbolicLink()
      || path.dirname(fs.realpathSync(outbox)) !== fs.realpathSync(session)) {
      throw new Error('Aggregation outbox escaped session storage.');
    }
  }
  if (fs.existsSync(request)) {
    if (fs.lstatSync(request).isSymbolicLink()
      || path.dirname(fs.realpathSync(request)) !== fs.realpathSync(outbox)) {
      throw new Error('Aggregation request directory escaped its outbox.');
    }
  }
  return request;
}

function readOutboxFile(directory, name, maximumBytes) {
  const file = path.join(directory, name);
  const stat = fs.lstatSync(file);
  if (!stat.isFile() || stat.size > maximumBytes
    || path.dirname(fs.realpathSync(file)) !== fs.realpathSync(directory)) {
    throw new Error(`Invalid durable outbox file ${name}.`);
  }
  return fs.readFileSync(file);
}

function buildAggregationMetadata(systemSessionId, frameId, record, requestId, inputPath) {
  const directory = sessionDir(systemSessionId);
  const frames = [];
  for (const candidateId of safeReadDir(path.join(directory, 'frames'))) {
    // The current frame's GLB name/hash are finalized in memory before its
    // frame.json handoff is persisted. Use that authoritative record here so
    // the initial metadata snapshot cannot omit the frame being staged.
    const candidate = candidateId === frameId
      ? record : readJson(frameJsonPath(systemSessionId, candidateId));
    if (!candidate) continue;
    if (candidateId !== frameId
      && !['complete', 'aggregator_pending', 'aggregating'].includes(candidate.status)) continue;
    const glbName = candidateId === frameId ? record.frameGlb : candidate.frameGlb;
    if (!/^frame\.attempt-[1-9][0-9]*\.glb$/.test(glbName || '')) {
      throw new Error(`Frame ${candidateId} has an invalid stored GLB filename.`);
    }
    const glbPath = path.join(frameDir(systemSessionId, candidateId), glbName || '');
    const glbExists = fs.existsSync(glbPath) && fs.lstatSync(glbPath).isFile();
    const sidecarExists = fs.existsSync(`${glbPath}.convention.json`)
      && fs.lstatSync(`${glbPath}.convention.json`).isFile();
    if (!glbExists || !sidecarExists) {
      if (candidateId === frameId) throw new Error('Current frame GLB or convention sidecar is missing.');
      continue;
    }
    const entry = manifestFrame(candidateId, candidate, glbPath);
    frames.push({
      frameId: entry.frameId,
      sequence: entry.sequence,
      glbPath: path.relative(DATA_DIR, glbPath).split(path.sep).join('/'),
      cameraToFirstFrame: entry.cameraToFirstFrame,
      conventionSidecarPath: path.relative(DATA_DIR, entry.conventionSidecarPath).split(path.sep).join('/'),
    });
  }
  frames.sort((a, b) => a.sequence - b.sequence);
  return {
    schemaVersion: 1,
    requestId,
    systemSessionId,
    frameId,
    sequence: record.sequence,
    inputGlbPath: path.relative(DATA_DIR, inputPath).split(path.sep).join('/'),
    inputGlbSha256: record.frameGlbSha256,
    frames,
  };
}

function queueAggregation(job, record, buffer) {
  const inputHash = crypto.createHash('sha256').update(buffer).digest('hex');
  const requestId = crypto.createHash('sha256')
    .update(`${job.systemSessionId}:${job.frameId}:${job.attempts}:${inputHash}`)
    .digest('hex').slice(0, 32);
  const directory = outboxPath(job.systemSessionId, requestId);
  fs.mkdirSync(directory, { recursive: true, mode: 0o750 });
  syncDirectory(path.dirname(directory));
  syncDirectory(sessionDir(job.systemSessionId));
  const inputPath = path.join(directory, 'input.glb');
  if (!fs.existsSync(inputPath)) {
    writeBinaryAtomic(inputPath, buffer);
  } else {
    const savedInput = readOutboxFile(directory, 'input.glb', 512 * 1024 * 1024);
    if (!validGlb(savedInput) || crypto.createHash('sha256').update(savedInput).digest('hex') !== inputHash) {
      throw new Error('Existing durable outbox input does not match the worker output.');
    }
  }
  record.frameGlbSha256 = inputHash;
  const metadata = buildAggregationMetadata(job.systemSessionId, job.frameId, record, requestId, inputPath);
  const metadataPath = path.join(directory, 'metadata.json');
  if (!fs.existsSync(metadataPath)) {
    writeJson(metadataPath, metadata);
  } else {
    const existing = JSON.parse(readOutboxFile(directory, 'metadata.json', 1024 * 1024).toString('utf8'));
    if (canonicalJson(existing) !== canonicalJson(metadata)) {
      throw new Error('Existing durable outbox metadata differs from the current frame snapshot.');
    }
  }
  const metadataSha256 = crypto.createHash('sha256').update(canonicalJson(metadata)).digest('hex');
  const statePath = path.join(directory, 'state.json');
  const existingState = readJson(statePath);
  if (existingState) {
    if (existingState.requestId !== requestId || existingState.systemSessionId !== job.systemSessionId
      || existingState.frameId !== job.frameId || existingState.inputGlbSha256 !== inputHash
      || existingState.metadataSha256 !== metadataSha256) {
      throw new Error('Existing durable outbox state does not match this stable request.');
    }
  } else {
    writeJson(path.join(directory, 'state.json'), {
      requestId,
      systemSessionId: job.systemSessionId,
      frameId: job.frameId,
      inputGlbSha256: inputHash,
      metadataSha256,
      status: 'staging',
      createdAt: Date.now(),
    });
  }
  record.requestId = requestId;
  return requestId;
}

function reconcileOutbox() {
  if (!fs.existsSync(ROOT)) return;
  for (const systemSessionId of safeReadDir(ROOT).filter((name) => SESSION_ID.test(name))) {
    const directory = sessionDir(systemSessionId);
    const outbox = path.join(directory, 'outbox');
    for (const requestId of safeReadDir(outbox).filter((name) => /^[a-f0-9]{32}$/.test(name))) {
      const state = readJson(outboxPath(systemSessionId, requestId) + path.sep + 'state.json');
      if (!state || state.requestId !== requestId || state.systemSessionId !== systemSessionId
        || !FRAME_ID.test(state.frameId || '')) continue;
      if (state.status === 'committed'
        && (!Number.isSafeInteger(state.version) || state.version < 1 || state.version > 999999999)) continue;
      if (!safeReadDir(path.join(directory, 'frames')).includes(state.frameId)) continue;
      const recordPath = frameJsonPath(systemSessionId, state.frameId);
      const record = readJson(recordPath);
      if (!record || record.requestId !== requestId) continue;
      if (state.status === 'staging' && record.status === 'aggregator_pending') {
        state.status = 'pending';
        state.updatedAt = Date.now();
        writeJson(outboxPath(systemSessionId, requestId) + path.sep + 'state.json', state);
        continue;
      }
      if (!['committed', 'rejected'].includes(state.status)) continue;
      if (state.status === 'committed') {
        record.status = 'complete';
        record.progress = 100;
        record.aggregateVersion = state.version;
        record.completedAt = record.completedAt || state.updatedAt || Date.now();
        delete record.error;
      } else {
        record.status = 'failed';
        record.progress = 0;
        const safeError = String(state.error || 'unspecified rejection').replace(/[\u0000-\u001f\u007f]/g, ' ');
        record.error = `Aggregation publisher rejected the frame: ${safeError}`.slice(0, 1000);
      }
      writeJson(recordPath, record);
      updateSessionProgress(directory, state.status === 'rejected' ? 'error' : undefined);
    }
    updateSessionProgress(directory);
  }
}

function dispatchNextAggregation(agent) {
  reconcileOutbox();
  if (!agent || agent.role !== 'aggregator' || !agent.ws || agent.ws.readyState !== 1
    || agent.activeRequestId || !fs.existsSync(ROOT)) return false;
  const requests = [];
  for (const systemSessionId of safeReadDir(ROOT).filter((name) => SESSION_ID.test(name)).sort()) {
    const outbox = path.join(sessionDir(systemSessionId), 'outbox');
    for (const requestId of safeReadDir(outbox).filter((name) => /^[a-f0-9]{32}$/.test(name))) {
      const directory = outboxPath(systemSessionId, requestId);
      const state = readJson(path.join(directory, 'state.json'));
      if (state && state.requestId === requestId && state.systemSessionId === systemSessionId
        && FRAME_ID.test(state.frameId || '')
        && /^[a-f0-9]{64}$/.test(state.inputGlbSha256 || '')
        && /^[a-f0-9]{64}$/.test(state.metadataSha256 || '')
        && ['pending', 'durable-accepted'].includes(state.status)) {
        requests.push({ systemSessionId, requestId, directory, state });
      }
    }
  }
  requests.sort((a, b) => (a.state.createdAt || 0) - (b.state.createdAt || 0)
    || a.requestId.localeCompare(b.requestId));
  const next = requests[0];
  if (!next) return false;
  try {
    const metadataBytes = readOutboxFile(next.directory, 'metadata.json', 1024 * 1024);
    const input = readOutboxFile(next.directory, 'input.glb', 512 * 1024 * 1024);
    if (!validGlb(input) || input.length > 512 * 1024 * 1024
      || crypto.createHash('sha256').update(input).digest('hex') !== next.state.inputGlbSha256
      || crypto.createHash('sha256').update(canonicalJson(JSON.parse(metadataBytes.toString('utf8')))).digest('hex')
        !== next.state.metadataSha256) {
      throw new Error('Durable aggregation request failed integrity verification.');
    }
    const metadata = JSON.parse(metadataBytes.toString('utf8'));
    if (!metadata || metadata.requestId !== next.requestId
      || metadata.systemSessionId !== next.systemSessionId
      || metadata.frameId !== next.state.frameId
      || !Number.isSafeInteger(metadata.sequence) || metadata.sequence < 0
      || metadata.inputGlbSha256 !== next.state.inputGlbSha256) {
      throw new Error('Aggregation request identity does not match its durable outbox path.');
    }
    agent.activeRequestId = next.requestId;
    agent.activeRequestSessionId = next.systemSessionId;
    agent.ws.send(JSON.stringify({
      type: 'aggregate_request',
      requestId: next.requestId,
      systemSessionId: next.systemSessionId,
      frameId: next.state.frameId,
      sequence: metadata.sequence,
      size: input.length,
      inputGlbSha256: next.state.inputGlbSha256,
      metadataSha256: next.state.metadataSha256,
      metadata,
    }));
    agent.ws.send(input, { binary: true });
    return true;
  } catch (error) {
    agent.activeRequestId = null;
    agent.activeRequestSessionId = null;
    logError(`Unable to dispatch durable aggregation request ${next.requestId}:`, error.message);
    return false;
  }
}

function handleAggregationAck(agent, data) {
  if (!agent || agent.role !== 'aggregator' || !data || data.type !== 'aggregation_ack'
    || !/^[a-f0-9]{32}$/.test(data.requestId || '')
    || !/^[a-f0-9]{32}$/.test(data.systemSessionId || '')
    || !FRAME_ID.test(data.frameId || '')
    || !['durable-accepted', 'committed', 'rejected'].includes(data.status)
    || agent.activeRequestId !== data.requestId
    || agent.activeRequestSessionId !== data.systemSessionId) return false;
  const directory = outboxPath(data.systemSessionId, data.requestId);
  const statePath = path.join(directory, 'state.json');
  const state = readJson(statePath);
  if (!state || state.frameId !== data.frameId
    || data.inputGlbSha256 !== state.inputGlbSha256
    || data.metadataSha256 !== state.metadataSha256) return false;
  const recordPath = frameJsonPath(data.systemSessionId, data.frameId);
  const record = readJson(recordPath);
  if (!record || record.requestId !== data.requestId) return false;
  if (['committed', 'rejected'].includes(state.status)) {
    return state.status === data.status;
  }
  if (data.status === 'committed'
    && (!Number.isSafeInteger(data.version) || data.version < 1 || data.version > 999999999)) return false;
  if (data.status === 'rejected'
    && (typeof data.error !== 'string' || data.error.length > 1000)) return false;
  state.status = data.status;
  state.updatedAt = Date.now();
  if (data.status === 'committed') state.version = data.version;
  if (data.status === 'rejected') state.error = data.error;
  writeJson(statePath, state);
  if (data.status === 'durable-accepted') {
    record.status = 'aggregating';
    record.progress = 97;
  } else if (data.status === 'committed') {
    record.status = 'complete';
    record.progress = 100;
    record.aggregateVersion = data.version;
    record.completedAt = Date.now();
    delete record.error;
  } else {
    record.status = 'failed';
    record.progress = 0;
    const safeError = data.error.replace(/[\u0000-\u001f\u007f]/g, ' ');
    record.error = `Aggregation publisher rejected the frame: ${safeError}`.slice(0, 1000);
  }
  writeJson(recordPath, record);
  updateSessionProgress(sessionDir(data.systemSessionId), data.status === 'rejected' ? 'error' : undefined);
  if (data.status !== 'durable-accepted') {
    agent.activeRequestId = null;
    agent.activeRequestSessionId = null;
    dispatchNextAggregation(agent);
  }
  return true;
}

function finishFrame(job, buffer, systemJobs, scan) {
  const directory = sessionDir(job.systemSessionId);
  const dir = frameDir(job.systemSessionId, job.frameId);
  const recordPath = frameJsonPath(job.systemSessionId, job.frameId);
  const record = readJson(recordPath);
  if (!record || record.status !== 'processing') return;
  const agent = agentPool().getAgent(job.agentId);
  try {
    if (!validGlb(buffer)) throw new Error('Worker returned an invalid GLB.');
    if (job.conventionError) throw new Error(job.conventionError);
    const glbSha256 = crypto.createHash('sha256').update(buffer).digest('hex');
    validateConventionSidecar(job.conventionSidecar, glbSha256, record.sha256);
    const frameGlbName = `frame.attempt-${job.attempts}.glb`;
    const frameGlb = path.join(dir, frameGlbName);
    writeBinaryAtomic(frameGlb, buffer);
    writeJson(`${frameGlb}.convention.json`, job.conventionSidecar);
    record.frameGlb = frameGlbName;
    record.frameGlbSha256 = glbSha256;
    const requestId = queueAggregation(job, record, buffer);
    record.status = 'aggregator_pending';
    record.progress = 96;
    record.handoffAt = Date.now();
    writeJson(recordPath, record);
    const requestStatePath = path.join(outboxPath(job.systemSessionId, requestId), 'state.json');
    const requestState = readJson(requestStatePath);
    if (!requestState) throw new Error('Durable outbox state is missing after frame handoff.');
    requestState.status = 'pending';
    requestState.updatedAt = Date.now();
    writeJson(requestStatePath, requestState);
    updateSessionProgress(directory);
    systemJobs.delete(job.jobId);
    if (agent && agent.jobId === job.jobId) {
      agent.busy = false;
      agent.jobId = null;
      notifyAgent(agent, {
        type: 'job_complete',
        jobId: job.jobId,
        jobType: 'system_frame',
        systemSessionId: job.systemSessionId,
        frameId: job.frameId,
        status: 'aggregator_pending',
        requestId,
      });
    }
    log(`Durably staged frame ${job.systemSessionId}/${job.frameId} for aggregation.`);
    const aggregator = agentPool().getAggregatorAgent();
    if (aggregator) dispatchNextAggregation(aggregator);
    setImmediate(scan);
  } catch (error) {
    record.status = 'failed';
    record.progress = 0;
    record.error = `Frame handoff failed: ${error.message}`.slice(0, 1000);
    writeJson(recordPath, record);
    try { updateSessionProgress(directory, 'error'); } catch (statusError) {
      logError(`Unable to persist session status for ${job.systemSessionId}:`, statusError.message);
    }
    systemJobs.delete(job.jobId);
    if (agent && agent.jobId === job.jobId) {
      agent.busy = false;
      agent.jobId = null;
      notifyAgent(agent, {
        type: 'job_error',
        jobId: job.jobId,
        jobType: 'system_frame',
        systemSessionId: job.systemSessionId,
        frameId: job.frameId,
        status: 'failed',
        error: 'Frame GLB could not be durably handed to the aggregator service.',
      });
    }
    logError(`Durable aggregation handoff failed for ${job.systemSessionId}/${job.frameId}:`, error.message);
    setImmediate(scan);
  }
}

function failFrame(job, message, systemJobs, scan) {
  const { agents } = agentPool();
  const agent = agents.get(job.agentId);
  systemJobs.delete(job.jobId);
  if (agent && agent.jobId === job.jobId) {
    agent.busy = false;
    agent.jobId = null;
  }
  retryFrame(job, systemJobs, String(message || 'Worker failed').slice(0, 500));
  setImmediate(scan);
}

function disconnectAgent(job, systemJobs, scan) {
  if (!job || job.jobType !== 'system_frame') return false;
  systemJobs.delete(job.jobId);
  retryFrame(job, systemJobs, 'Worker disconnected while processing this frame.');
  setImmediate(scan);
  return true;
}

module.exports = {
  configureScan,
  scanPending,
  updateProgress,
  finishFrame,
  dispatchNextAggregation,
  handleAggregationAck,
  reconcileOutbox,
  failFrame,
  disconnectAgent,
  validGlb,
  validateConventionSidecar,
  validateCaptureTransform,
  manifestFrame,
  frameDir,
  retryStatus,
};
