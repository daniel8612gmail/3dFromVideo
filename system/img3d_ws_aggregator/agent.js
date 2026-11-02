'use strict';

require('dotenv').config();
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const WebSocket = require('ws');
const protocol = require('./protocol');

const WS_URL = process.env.WS_URL
  || (process.env.DOMAIN ? `wss://${process.env.DOMAIN}/ws` : '');
const AGENT_ID = process.env.AGGREGATOR_ID || process.env.AGENT_ID;
const TOKEN = process.env.AGGREGATOR_TOKEN || process.env.AGENT_TOKEN;
const DATA_DIR = path.resolve(process.env.DATA_DIR || path.join(__dirname, 'data'));
const PUBLISHER_CLI = process.env.PUBLISHER_CLI;
const PUBLISHER_SCRIPT = process.env.PUBLISHER_SCRIPT;
const MAX_TIMEOUT_MS = 6 * 60 * 60 * 1000;
const OUTPUT_CAP = 256 * 1024;
const activePublishers = new Map();
const activeChildren = new Set();
let ws = null;
let reconnectDelay = 1000;
let reconnectTimer = null;
let shuttingDown = false;
let incoming = null;

if (!WS_URL || !/^wss?:\/\//.test(WS_URL) || !AGENT_ID || !TOKEN || !PUBLISHER_CLI) {
  console.error('Required: WS_URL (or DOMAIN), AGGREGATOR_ID, AGGREGATOR_TOKEN, DATA_DIR, PUBLISHER_CLI.');
  process.exit(1);
}

function log(message) {
  console.log(new Date().toISOString(), message);
}

function readJson(filePath) {
  try {
    const stat = fs.lstatSync(filePath);
    if (!stat.isFile() || stat.size > 1024 * 1024) return null;
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (_) {
    return null;
  }
}

function writeJson(filePath, value) {
  protocol.durableWrite(filePath, Buffer.from(JSON.stringify(value, null, 2), 'utf8'));
}

function requestFiles(systemSessionId, requestId) {
  const { root, session, destination } = protocol.requestDirectory(DATA_DIR, systemSessionId, requestId);
  const rootStat = protocol.lstatIfPresent(root);
  const sessionStat = protocol.lstatIfPresent(session);
  const inboxParent = path.dirname(destination);
  const inboxStat = protocol.lstatIfPresent(inboxParent);
  if (!rootStat || !rootStat.isDirectory() || rootStat.isSymbolicLink()
    || !sessionStat || !sessionStat.isDirectory() || sessionStat.isSymbolicLink()
    || (inboxStat && (!inboxStat.isDirectory() || inboxStat.isSymbolicLink()))) {
    throw new Error('Inbox storage root/session is missing or is a symlink.');
  }
  const realRoot = fs.realpathSync(root);
  const realSession = fs.realpathSync(session);
  if (path.dirname(realSession) !== realRoot
    || (inboxStat && path.dirname(fs.realpathSync(inboxParent)) !== realSession)) {
    throw new Error('Inbox storage path escaped the shared session directory.');
  }
  const destinationStat = protocol.lstatIfPresent(destination);
  if (destinationStat && (!destinationStat.isDirectory() || destinationStat.isSymbolicLink())) {
    throw new Error('Inbox request is a symlink.');
  }
  if (destinationStat) {
    for (const name of ['state.json', 'input.glb', 'input.glb.convention.json', 'request.json']) {
      const file = path.join(destination, name);
      if (fs.existsSync(file) && !fs.lstatSync(file).isFile()) {
        throw new Error(`Inbox ${name} is not a regular file.`);
      }
    }
  }
  return {
    directory: destination,
    state: path.join(destination, 'state.json'),
    input: path.join(destination, 'input.glb'),
    metadata: path.join(destination, 'request.json'),
    publisherMetadata: path.join(destination, 'publisher-metadata.json'),
    result: path.join(destination, 'publisher-result.json'),
  };
}

function sendAck(context, status, extra = {}) {
  const socket = ws;
  if (!socket || socket.readyState !== WebSocket.OPEN) return false;
  try {
    socket.send(JSON.stringify({
      type: 'aggregation_ack',
      requestId: context.requestId,
      systemSessionId: context.systemSessionId,
      frameId: context.frameId,
      status,
      inputGlbSha256: context.inputGlbSha256,
      metadataSha256: context.metadataSha256,
      ...extra,
    }));
    return true;
  } catch (_) {
    return false;
  }
}

function publisherMetadata(metadata, files, requestId) {
  const copy = JSON.parse(JSON.stringify(metadata));
  const sessionRelative = `system-sessions/${metadata.systemSessionId}/aggregator-inbox/${requestId}/input.glb`;
  copy.inputGlbPath = sessionRelative;
  for (const frame of copy.frames) {
    if (frame.frameId === metadata.frameId && frame.sequence === metadata.sequence) {
      frame.glbPath = sessionRelative;
      frame.conventionSidecarPath = `${sessionRelative}.convention.json`;
    }
  }
  return copy;
}

function scheduleRetry(context, files, metadata, error) {
  const state = readJson(files.state);
  if (state && !['committed', 'rejected'].includes(state.status)) {
    state.status = 'durable-accepted';
    state.lastError = String(error.message || error).slice(0, 1000);
    state.retryAt = Date.now() + 5000;
    try { writeJson(files.state, state); } catch (_) { /* A later broker replay retries persistence. */ }
  }
  log(`Publisher retry scheduled for ${context.requestId}: ${String(error.message || error).slice(0, 300)}`);
  setTimeout(() => {
    processStaged(context, files, metadata).catch((retryError) => {
      scheduleRetry(context, files, metadata, retryError);
    });
  }, 5000);
}

function runPublisher(context, files, metadata) {
  if (activePublishers.has(context.requestId)) return activePublishers.get(context.requestId);
  const task = new Promise((resolve) => {
    const args = [
      ...(PUBLISHER_SCRIPT ? [PUBLISHER_SCRIPT] : []),
      '--request-id', context.requestId,
      '--system-session-id', context.systemSessionId,
      '--frame-id', context.frameId,
      '--input-glb', files.input,
      '--metadata-json', files.publisherMetadata,
      '--data-dir', DATA_DIR,
      '--result-json', files.result,
    ];
    try { fs.unlinkSync(files.result); } catch (error) {
      if (error.code !== 'ENOENT') {
        resolve({ ok: false, error: `Cannot clear publisher result file: ${error.message}` });
        return;
      }
    }
    const child = spawn(PUBLISHER_CLI, args, {
      cwd: DATA_DIR,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    activeChildren.add(child);
    let captured = '';
    let capturedBytes = 0;
    let timedOut = false;
    let settled = false;
    const timeoutValue = Number(process.env.PUBLISHER_TIMEOUT_MS);
    const timeoutMs = Number.isFinite(timeoutValue) && timeoutValue > 0
      ? Math.min(Math.max(1000, timeoutValue), MAX_TIMEOUT_MS)
      : 1200000;
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
    }, timeoutMs);
    const escalation = setTimeout(() => {
      if (timedOut && child.exitCode === null) child.kill('SIGKILL');
    }, timeoutMs + 5000);
    function consume(chunk) {
      const available = Math.max(0, OUTPUT_CAP - capturedBytes);
      const part = chunk.subarray(0, available);
      capturedBytes += part.length;
      if (part.length) captured += part.toString('utf8');
      if (part.length < chunk.length) capturedBytes = OUTPUT_CAP;
    }
    child.stdout.on('data', consume);
    child.stderr.on('data', consume);
    child.on('error', (error) => {
      if (settled) return;
      settled = true;
      activeChildren.delete(child);
      clearTimeout(timeout);
      clearTimeout(escalation);
      resolve({ ok: false, error: `Publisher could not start: ${error.message}` });
    });
    child.on('close', (code, signal) => {
      if (settled) return;
      settled = true;
      activeChildren.delete(child);
      clearTimeout(timeout);
      clearTimeout(escalation);
      if (timedOut || code !== 0) {
        resolve({
          ok: false,
          error: timedOut ? `Publisher timeout after ${timeoutMs} ms.` :
            `Publisher exited ${code === null ? signal : code}: ${captured.slice(-4000)}`,
        });
        return;
      }
      const result = readJson(files.result);
      if (!result || result.requestId !== context.requestId) {
        resolve({ ok: false, error: 'Publisher exited successfully without a valid matching result JSON.' });
      } else if (result.status === 'committed' && Number.isSafeInteger(result.version) && result.version > 0) {
        resolve({ ok: true, version: result.version });
      } else if (result.status === 'rejected' && typeof result.error === 'string') {
        resolve({ rejected: true, error: result.error.slice(0, 1000) });
      } else {
        resolve({ ok: false, error: 'Publisher result must be committed or rejected with the documented fields.' });
      }
    });
  });
  activePublishers.set(context.requestId, task);
  task.finally(() => activePublishers.delete(context.requestId));
  return task;
}

async function processStaged(context, files, metadata) {
  if (activePublishers.has(context.requestId)) return;
  let state = readJson(files.state);
  if (!state) return;
  if (state.status === 'committed') {
    sendAck(context, 'committed', { version: state.version });
    return;
  }
  if (state.status === 'rejected') {
    sendAck(context, 'rejected', { error: state.error });
    return;
  }
  try {
    state.status = 'publishing';
    state.lastAttemptAt = Date.now();
    writeJson(files.state, state);
    const mappedMetadata = publisherMetadata(metadata, files, context.requestId);
    writeJson(files.publisherMetadata, mappedMetadata);

    const result = await runPublisher(context, files, mappedMetadata);
    state = readJson(files.state) || state;
    if (result.ok) {
      state.status = 'committed';
      state.version = result.version;
      state.committedAt = Date.now();
      delete state.lastError;
      writeJson(files.state, state);
      sendAck(context, 'committed', { version: result.version });
    } else if (result.rejected) {
      state.status = 'rejected';
      state.error = result.error.slice(0, 1000);
      state.completedAt = Date.now();
      writeJson(files.state, state);
      sendAck(context, 'rejected', { error: state.error });
    } else {
      scheduleRetry(context, files, metadata, result.error);
    }
  } catch (error) {
    scheduleRetry(context, files, metadata, error);
  }
}

function envelopeFrom(message) {
  if (!message || message.type !== 'aggregate_request'
    || !protocol.REQUEST_ID.test(message.requestId || '')
    || !protocol.SESSION_ID.test(message.systemSessionId || '')
    || !protocol.FRAME_ID.test(message.frameId || '')
    || !Number.isSafeInteger(message.size) || message.size < 20 || message.size > protocol.MAX_GLB_BYTES
    || !protocol.SHA256.test(message.inputGlbSha256 || '')
    || !protocol.SHA256.test(message.metadataSha256 || '')
    || !message.metadata || typeof message.metadata !== 'object' || Array.isArray(message.metadata)
    || message.sequence !== message.metadata.sequence) {
    throw new Error('Invalid aggregation request envelope.');
  }
  return {
    requestId: message.requestId,
    systemSessionId: message.systemSessionId,
    frameId: message.frameId,
    sequence: message.metadata.sequence,
    size: message.size,
    inputGlbSha256: message.inputGlbSha256,
    metadataSha256: message.metadataSha256,
  };
}

function handleJson(message) {
  if (!message || typeof message !== 'object' || Array.isArray(message)) {
    throw new Error('WebSocket control message must be a JSON object.');
  }
  if (message.type !== 'aggregate_request') {
    throw new Error('Unexpected control message from broker.');
  }
  if (incoming) throw new Error('Received a second aggregation request before its binary payload.');
  const envelope = envelopeFrom(message);
  protocol.validateMetadata(message.metadata, envelope);
  incoming = { envelope, metadata: message.metadata };
}

async function handleBinary(buffer) {
  if (!incoming) throw new Error('Received binary payload without a request envelope.');
  const { envelope, metadata } = incoming;
  incoming = null;
  const context = {
    requestId: envelope.requestId,
    systemSessionId: envelope.systemSessionId,
    frameId: envelope.frameId,
    inputGlbSha256: envelope.inputGlbSha256,
    metadataSha256: envelope.metadataSha256,
  };
  const files = requestFiles(context.systemSessionId, context.requestId);
  const staged = protocol.stageRequest(DATA_DIR, envelope, metadata, buffer);
  if (staged.state.status === 'committed') {
    sendAck(context, 'committed', { version: staged.state.version });
    return;
  }
  if (staged.state.status === 'rejected') {
    sendAck(context, 'rejected', { error: staged.state.error });
    return;
  }
  sendAck(context, 'durable-accepted');
  processStaged(context, files, metadata).catch((error) => scheduleRetry(context, files, metadata, error));
}

function connect() {
  if (shuttingDown) return;
  ws = new WebSocket(WS_URL, { maxPayload: protocol.MAX_GLB_BYTES + 2 * 1024 * 1024 });
  ws.on('open', () => {
    reconnectDelay = 1000;
    ws.send(JSON.stringify({ type: 'auth', agentId: AGENT_ID, token: TOKEN, role: 'aggregator' }));
  });
  ws.on('message', (data, isBinary) => {
    if (isBinary) {
      handleBinary(Buffer.isBuffer(data) ? data : Buffer.from(data)).catch((error) => {
        log(`Rejected aggregator binary payload: ${error.message}`);
        if (ws && ws.readyState === WebSocket.OPEN) ws.close(1008, 'Invalid aggregation payload');
      });
      return;
    }
    try {
      const message = JSON.parse(data.toString());
      if (message.type === 'auth_ok') {
        if (message.role !== 'aggregator') throw new Error('Broker did not authorize aggregator role.');
        log('Authenticated as aggregator service.');
        return;
      }
      handleJson(message);
    } catch (error) {
      log(`Rejected broker control message: ${error.message}`);
      if (ws && ws.readyState === WebSocket.OPEN) ws.close(1008, 'Invalid control message');
    }
  });
  ws.on('close', () => {
    ws = null;
    if (!shuttingDown) {
      const delay = Math.min(reconnectDelay, 30000) + Math.floor(Math.random() * 500);
      reconnectDelay = Math.min(reconnectDelay * 2, 30000);
      reconnectTimer = setTimeout(connect, delay);
    }
  });
  ws.on('error', (error) => {
    log(`WebSocket error: ${error.message}`);
  });
}

function recoverInbox() {
  const root = path.join(DATA_DIR, 'system-sessions');
  let sessions = [];
  try {
    const rootStat = protocol.lstatIfPresent(root);
    if (!rootStat || !rootStat.isDirectory() || rootStat.isSymbolicLink()) return;
    sessions = fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && protocol.SESSION_ID.test(entry.name))
      .map((entry) => entry.name);
  } catch (_) {
    return;
  }
  for (const systemSessionId of sessions) {
    const inbox = path.join(root, systemSessionId, 'aggregator-inbox');
    let requests = [];
    try {
      const inboxStat = protocol.lstatIfPresent(inbox);
      if (!inboxStat || !inboxStat.isDirectory() || inboxStat.isSymbolicLink()) continue;
      requests = fs.readdirSync(inbox, { withFileTypes: true })
        .filter((entry) => entry.isDirectory() && protocol.REQUEST_ID.test(entry.name))
        .map((entry) => entry.name);
    } catch (_) {
      continue;
    }
    for (const requestId of requests) {
      try {
        const files = requestFiles(systemSessionId, requestId);
        const state = readJson(files.state);
        const metadata = readJson(files.metadata);
        const input = fs.readFileSync(files.input);
        const sidecarBytes = fs.readFileSync(`${files.input}.convention.json`);
        if (!state || !metadata || !protocol.validGlb(input)
          || protocol.sha256(input) !== state.inputGlbSha256
          || protocol.sha256(sidecarBytes) !== state.conventionSidecarSha256) continue;
        const sidecar = JSON.parse(sidecarBytes.toString('utf8'));
        if (sidecar.glbSha256 !== state.inputGlbSha256) continue;
        const context = {
          requestId,
          systemSessionId,
          frameId: state.frameId,
          sequence: state.sequence,
          inputGlbSha256: state.inputGlbSha256,
          metadataSha256: state.metadataSha256,
        };
        protocol.validateMetadata(metadata, context);
        if (state.status === 'publishing') {
          state.status = 'durable-accepted';
          state.recoveredAt = Date.now();
          writeJson(files.state, state);
        }
        if (['durable-accepted', 'publishing'].includes(state.status)) {
          processStaged(context, files, metadata).catch((error) => scheduleRetry(context, files, metadata, error));
        }
      } catch (error) {
        log(`Skipped invalid inbox item ${requestId}: ${error.message}`);
      }
    }
  }
}

process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
function shutdown() {
  shuttingDown = true;
  if (reconnectTimer) clearTimeout(reconnectTimer);
  if (ws) ws.close(1001, 'Aggregator shutdown');
  for (const child of activeChildren) {
    child.kill('SIGTERM');
    const escalation = setTimeout(() => {
      if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL');
    }, 5000);
    child.once('close', () => clearTimeout(escalation));
  }
  setTimeout(() => process.exit(0), 6000);
}

recoverInbox();
connect();
