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
  maxPayload: 200 * 1024 * 1024,
});

log(`WebSocket server uruchomiony na ws://${HOST}:${PORT} v20240919.2131`);

// ==================================================
// POŁĄCZENIE AGENTA
// ==================================================

wss.on('connection', (ws) => {
  let authenticated = false;
  let agentId = null;
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
      if (!authenticated) {
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

    // --------------------------------------------------
    // AUTH
    // --------------------------------------------------

    if (data.type === 'auth') {
      if (authenticated) {
        return;
      }

      const requestedAgentId = data.agentId;
      const token = data.token;

      if (!authenticateAgent(requestedAgentId, token)) {
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

      addAgent(agentId, ws);

      log(`Agent ${agentId} został autoryzowany.`);

      ws.send(
        JSON.stringify({
          type: 'auth_ok',
          agentId,
        }),
      );

      scanPendingJobs();

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

    // --------------------------------------------------
    // PROGRESS
    // --------------------------------------------------

    if (data.type === 'progress') {
      const job = jobs.get(data.jobId);

      if (!job || job.agentId !== agentId) {
        return;
      }

      if (!Number.isInteger(data.progress) || data.progress < 0 || data.progress > 100) {
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

    if (data.type === 'ready_for_glb') {
      const job = jobs.get(data.jobId);

      if (!job || job.agentId !== agentId) {
        return;
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
