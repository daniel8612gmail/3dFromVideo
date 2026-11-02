'use strict';

const WebSocket = require('ws');
const chokidar = require('chokidar');

const { DATA_DIR, PORT, HOST, log, logError, isValidSessionId } = require('./config');
const { authenticateAgent, reloadAgents, getAgent, addAgent, getAgents } = require('./agents');
const { jobs, scanPendingJobs, finishJob, failJob, handleAgentDisconnect } = require('./jobs');

// ==================================================
// WEBSOCKET SERVER
// ==================================================
const wss = new WebSocket.Server({
  host: HOST,
  port: PORT,
  maxPayload: (() => {
    const configured = Number(process.env.MAX_WS_PAYLOAD_BYTES);
    return Number.isSafeInteger(configured) && configured >= 1024 * 1024
      ? Math.min(configured, 1024 * 1024 * 1024)
      : 600 * 1024 * 1024;
  })(),
});

log(`WebSocket server uruchomiony na ws://${HOST}:${PORT} v20240919.2131`);

// ==================================================
// POŁĄCZENIE AGENTA
// ==================================================

wss.on('connection', (ws) => {
  let authenticated = false;
  let agentId = null;
  let agentRole = null;
  let currentBinaryJob = null;

  const authTimeout = setTimeout(() => {
    if (!authenticated) {
      log('Połączenie zamknięte: brak autoryzacji.');

      ws.close(1008, 'Authentication timeout');
    }
  }, 10000);

  // ==================================================
  // WIADOMOŚCI
  // ==================================================

  ws.on('message', (message, isBinary) => {
    // --------------------------------------------------
    // DANE BINARNE
    // --------------------------------------------------

    if (isBinary) {
      if (!authenticated || agentRole !== 'worker') {
        ws.close(1008, 'Not authenticated');
        return;
      }

      if (!currentBinaryJob) {
        logError(`Agent ${agentId} wysłał dane binarne ` + 'bez oczekującego zadania.');

        return;
      }

      const job = jobs.get(currentBinaryJob);

      if (!job) {
        currentBinaryJob = null;
        return;
      }

      job.outputReceived = true;
      finishJob(job, Buffer.from(message));

      currentBinaryJob = null;

      return;
    }

    // --------------------------------------------------
    // JSON
    // --------------------------------------------------

    let data;

    try {
      data = JSON.parse(message.toString());
    } catch (error) {
      ws.send(
        JSON.stringify({
          type: 'error',
          error: 'Nieprawidłowy JSON.',
        }),
      );

      return;
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) {
      ws.send(JSON.stringify({ type: 'error', error: 'Wiadomość JSON musi być obiektem.' }));
      return;
    }

    // --------------------------------------------------
    // AUTH
    // --------------------------------------------------

    if (data.type === 'auth') {
      if (authenticated) {
        return;
      }

      const requestedAgentId = data.agentId;
      const token = data.token;
      const requestedRole = require('./agents').getAgentRole(requestedAgentId);

      if (!authenticateAgent(requestedAgentId, token)
        || !requestedRole
        || (data.role !== undefined && data.role !== requestedRole)) {
        log('Odrzucono autoryzację agenta: ' + `${requestedAgentId || '(brak ID)'}`);

        ws.close(1008, 'Unauthorized');

        return;
      }

      clearTimeout(authTimeout);

      // ----------------------------------------------
      // Jeden agent = jedno połączenie
      // ----------------------------------------------

      const existing = getAgent(requestedAgentId);

      if (existing) {
        log(`Agent ${requestedAgentId} jest już połączony.`);

        ws.close(1008, 'Agent already connected');

        return;
      }

      authenticated = true;
      agentId = requestedAgentId;
      agentRole = requestedRole;

      addAgent(agentId, ws, agentRole);

      log(`Agent ${agentId} został autoryzowany.`);

      ws.send(
        JSON.stringify({
          type: 'auth_ok',
          agentId,
          role: agentRole,
        }),
      );

      if (agentRole === 'aggregator') {
        try {
          require('./system-session-jobs').dispatchNextAggregation(getAgent(agentId));
        } catch (error) {
          logError('Unable to dispatch durable aggregation outbox:', error.message);
        }
      } else {
        scanPendingJobs();
      }

      return;
    }

    // --------------------------------------------------
    // WSZYSTKO PONIŻEJ WYMAGA AUTORYZACJI
    // --------------------------------------------------

    if (!authenticated) {
      ws.close(1008, 'Not authenticated');
      return;
    }

    const agent = getAgent(agentId);

    if (!agent) {
      return;
    }
    if (agentRole === 'aggregator') {
      try {
        if (!require('./system-session-jobs').handleAggregationAck(agent, data)) {
          logError(`Rejected invalid aggregation acknowledgement from ${agentId}.`);
        }
      } catch (error) {
        logError(`Aggregation acknowledgement handler failed for ${agentId}:`, error.message);
      }
      return;
    }

    // --------------------------------------------------
    // PROGRESS
    // --------------------------------------------------

    if (data.type === 'progress') {
      const job = jobs.get(data.jobId);

      if (!job || job.agentId !== agentId) {
        return;
      }
      if (job.jobType === 'system_frame'
        && (data.jobType !== 'system_frame'
          || data.systemSessionId !== job.systemSessionId
          || data.frameId !== job.frameId)) {
        return;
      }

      if (!Number.isInteger(data.progress) || data.progress < 0 || data.progress > 100) {
        return;
      }

      if (job.jobType === 'system_frame') {
        require('./system-session-jobs').updateProgress(job, data.progress, data);
        log(`Agent ${agentId}: ${job.systemSessionId}/${job.frameId}: ${data.progress}%`);
        return;
      }

      const { readState, writeState } = require('./config');

      const state = readState(job.sessionId);

      if (!state) {
        return;
      }

      state.status = 'processing';
      state.progress = data.progress;

      writeState(job.sessionId, state);

      log(`Agent ${agentId}: ` + `zadanie ${job.jobId}: ` + `${data.progress}%`);

      return;
    }

    // --------------------------------------------------
    // AGENT CZEKA NA GLB
    // --------------------------------------------------

    if (data.type === 'ready_for_glb' || data.type === 'ready_for_frame_glb') {
      const job = jobs.get(data.jobId);

      if (!job || job.agentId !== agentId) {
        return;
      }
      if ((job.jobType === 'system_frame'
          && (data.type !== 'ready_for_frame_glb'
            || data.jobType !== 'system_frame'
            || data.systemSessionId !== job.systemSessionId
            || data.frameId !== job.frameId))
        || (job.jobType !== 'system_frame' && data.type !== 'ready_for_glb')) {
        return;
      }

      if (job.jobType === 'system_frame') {
        try {
          if (Buffer.byteLength(JSON.stringify(data.conventionSidecar), 'utf8') > 64 * 1024) {
            throw new Error('Worker convention sidecar exceeds the size limit.');
          }
          job.conventionSidecar = require('./system-session-jobs')
            .validateConventionSidecar(data.conventionSidecar);
          delete job.conventionError;
        } catch (error) {
          job.conventionSidecar = null;
          job.conventionError = `Worker convention sidecar rejected: ${error.message}`;
        }
      }

      currentBinaryJob = data.jobId;

      return;
    }

    // --------------------------------------------------
    // ERROR
    // --------------------------------------------------

    if (data.type === 'error') {
      const job = jobs.get(data.jobId);

      if (!job || job.agentId !== agentId) {
        return;
      }
      if (job.jobType === 'system_frame'
        && (data.jobType !== 'system_frame'
          || data.systemSessionId !== job.systemSessionId
          || data.frameId !== job.frameId)) {
        return;
      }

      failJob(job, typeof data.error === 'string' ? data.error : 'Nieznany błąd agenta.');

      return;
    }

    // --------------------------------------------------
    // UNKNOWN MESSAGE
    // --------------------------------------------------

    log(`Nieznany komunikat od agenta ${agentId}:`, data.type);
  });

  // ==================================================
  // ROZŁĄCZENIE
  // ==================================================

  ws.on('close', () => {
    clearTimeout(authTimeout);

    if (!authenticated) {
      return;
    }

    const agent = getAgent(agentId);

    if (!agent) {
      return;
    }

    // Nie obsługuj starego połączenia,
    // jeśli agent został zastąpiony.

    if (agent.ws !== ws) {
      return;
    }

    handleAgentDisconnect(agentId, agent);
  });

  // ==================================================
  // BŁĄD WEBSOCKET
  // ==================================================

  ws.on('error', (error) => {
    logError(`Błąd WebSocket agenta ${agentId || '?'}:`, error.message);
  });
});

// ==================================================
// OBSERWATOR DATA
// ==================================================

const photoPattern = `${DATA_DIR}`;

const watcher = chokidar.watch(photoPattern, {
  ignoreInitial: false,

  awaitWriteFinish: {
    stabilityThreshold: 1000,
    pollInterval: 100,
  },
});

watcher.on('add', (filePath) => {
  const normalizedPath = filePath.replace(/\\/g, '/').toLowerCase();
  if (!['.jpg', '.png', '.jpeg', '.webp'].some((ext) => normalizedPath.endsWith(ext))) {
    return;
  }
  const relative = require('path').relative(DATA_DIR, filePath).replace(/\\/g, '/').split('/');
  if (relative[0] === 'system-sessions'
    && isValidSessionId(relative[1])
    && /^[A-Za-z0-9_-]{1,96}$/.test(relative[3] || '')
    && relative[2] === 'frames') {
    log(`Wykryto zdjęcie klatki systemowej: ${relative[1]}/${relative[3]}`);
    setTimeout(scanPendingJobs, 100);
    return;
  }
  console.log(`watcher.on('add' (${filePath})`);
  const sessionDir = require('path').dirname(filePath);
  const sessionId = require('path').basename(sessionDir);

  if (!isValidSessionId(sessionId)) {
    log(`plik nieobsługiwany`);
    return;
  }

  log(`Wykryto zdjęcie: ${filePath}`);

  setTimeout(scanPendingJobs, 100);
});

watcher.on('error', (error) => {
  logError('Błąd obserwatora plików:', error);
});

// ==================================================
// OBSŁUGA SIGHUP
// ==================================================

process.on('SIGHUP', () => {
  log('Otrzymano SIGHUP.');

  reloadAgents();
});

// ==================================================
// ZAMKNIĘCIE
// ==================================================

function shutdown(signal) {
  log(`${signal} - zamykanie serwera...`);

  watcher.close();
  for (const [, agent] of getAgents()) {
    try {
      agent.ws.close(1001, 'Server shutdown');
    } catch (_) {
      // Ignorujemy błąd podczas zamykania.
    }
  }

  wss.close(() => {
    log('WebSocket server zamknięty.');
    process.exit(0);
  });

  setTimeout(() => {
    logError('Serwer nie zamknął się poprawnie.');

    process.exit(1);
  }, 5000);
}

process.on('SIGTERM', () => {
  shutdown('SIGTERM');
});

process.on('SIGINT', () => {
  shutdown('SIGINT');
});

// ==================================================
// INFORMACJE STARTOWE
// ==================================================

log(`DATA_DIR: ${DATA_DIR}`);
log(`PORT: ${PORT}`);
log(`AGENTS_FILE: ${require('./config').AGENTS_FILE}`);
log(`Autoryzowanych agentów: ` + `${require('./agents').getAuthorizedAgentCount()}`);
