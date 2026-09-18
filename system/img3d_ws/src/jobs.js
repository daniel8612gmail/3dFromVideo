'use strict';

const WebSocket = require('ws');

const {
  fs,
  path,
  crypto,
  DATA_DIR,
  log,
  logError,
  readState,
  writeState,
  isValidPhotoFilename,
} = require('./config');

const { agents, getIdleAgent } = require('./agents');

// ==================================================
// ZADANIA
// ==================================================

/*
 * Map:
 *
 * jobId -> {
 *     jobId,
 *     sessionId,
 *     agentId
 * }
 */

const jobs = new Map();

// ==================================================
// WYSYŁANIE ZADANIA
// ==================================================

function dispatchJob(sessionId, agentId, agent) {
  const sessionDir = path.join(DATA_DIR, sessionId);
  const state = readState(sessionId);

  if (!state) {
    return false;
  }

  if (state.status !== 'uploaded') {
    return false;
  }

  let files;

  try {
    files = fs.readdirSync(sessionDir);
  } catch (error) {
    logError(`Nie można odczytać katalogu sesji ${sessionId}:`, error.message);

    return false;
  }

  const photoFilename = files.find(isValidPhotoFilename);

  if (!photoFilename) {
    log(`Brak zdjęcia dla sesji ${sessionId}.`);
    return false;
  }

  const photoPath = path.join(sessionDir, photoFilename);

  let stat;

  try {
    stat = fs.statSync(photoPath);
  } catch (error) {
    logError(`Nie można odczytać zdjęcia ${photoFilename}:`, error.message);

    return false;
  }

  const jobId = crypto.randomUUID();

  const job = {
    jobId,
    sessionId,
    agentId,
  };

  jobs.set(jobId, job);

  agent.busy = true;
  agent.jobId = jobId;

  state.status = 'processing';
  state.progress = 0;
  state.jobId = jobId;

  writeState(sessionId, state);

  try {
    agent.ws.send(
      JSON.stringify({
        type: 'job',
        jobId,
        sessionId,
        filename: photoFilename,
        size: stat.size,
      }),
    );

    const photoBuffer = fs.readFileSync(photoPath);

    agent.ws.send(photoBuffer, {
      binary: true,
    });

    log(`Wysłano zadanie ${jobId} ` + `dla sesji ${sessionId} ` + `do agenta ${agentId}.`);

    return true;
  } catch (error) {
    logError(`Błąd wysyłania zadania ${jobId}:`, error.message);

    jobs.delete(jobId);

    agent.busy = false;
    agent.jobId = null;

    state.status = 'uploaded';
    state.progress = 0;

    delete state.jobId;

    writeState(sessionId, state);

    return false;
  }
}

// ==================================================
// PRZESZUKIWANIE OCZEKUJĄCYCH SESJI
// ==================================================

function scanPendingJobs() {
  let entries;

  try {
    entries = fs.readdirSync(DATA_DIR, {
      withFileTypes: true,
    });
  } catch (error) {
    logError('Nie można odczytać DATA_DIR:', error.message);

    return;
  }

  for (const entry of entries) {
    if (!entry.isDirectory()) {
      continue;
    }

    const sessionId = entry.name;
    const state = readState(sessionId);

    if (!state || state.status !== 'uploaded') {
      continue;
    }

    const availableAgent = getIdleAgent();

    if (!availableAgent) {
      return;
    }

    dispatchJob(sessionId, availableAgent.agentId, availableAgent.agent);
  }
}

// ==================================================
// ZAKOŃCZENIE ZADANIA
// ==================================================

function finishJob(job, glbBuffer) {
  const { jobId, sessionId, agentId } = job;

  const agent = agents.get(agentId);

  if (!agent) {
    logError(`Agent ${agentId} nie istnieje ` + `przy zakończeniu zadania.`);

    return;
  }

  // --------------------------------------------------
  // WALIDACJA GLB
  // --------------------------------------------------

  if (!Buffer.isBuffer(glbBuffer) || glbBuffer.length < 4) {
    logError(`Nieprawidłowy GLB dla zadania ${jobId}.`);

    return failJob(job, 'Odebrano nieprawidłowy plik GLB.');
  }

  const magic = glbBuffer.subarray(0, 4).toString('ascii');

  if (magic !== 'glTF') {
    logError(`Nieprawidłowy nagłówek GLB dla ${jobId}.`);

    return failJob(job, 'Odebrany plik nie jest poprawnym GLB.');
  }

  // --------------------------------------------------
  // ZAPIS ATOMOWY
  // --------------------------------------------------

  const sessionDir = path.join(DATA_DIR, sessionId);

  const modelPath = path.join(sessionDir, 'model.glb');

  const tmpPath = `${modelPath}.${process.pid}.tmp`;

  try {
    fs.writeFileSync(tmpPath, glbBuffer);

    fs.renameSync(tmpPath, modelPath);

    const state = readState(sessionId);

    if (state) {
      state.status = 'ready';
      state.progress = 100;
      state.glb = 'model.glb';

      delete state.jobId;

      writeState(sessionId, state);
    }

    jobs.delete(jobId);

    agent.busy = false;
    agent.jobId = null;

    if (agent.ws.readyState === WebSocket.OPEN) {
      agent.ws.send(
        JSON.stringify({
          type: 'job_complete',
          jobId,
          sessionId,
        }),
      );
    }

    log(`Zadanie ${jobId} zakończone. ` + `Model zapisany dla sesji ${sessionId}.`);

    // Sprawdź, czy nie czeka kolejne zadanie.
    setImmediate(scanPendingJobs);
  } catch (error) {
    try {
      if (fs.existsSync(tmpPath)) {
        fs.unlinkSync(tmpPath);
      }
    } catch (_) {
      // Ignorujemy błąd usuwania pliku tymczasowego.
    }

    logError(`Nie można zapisać GLB dla ${jobId}:`, error.message);

    failJob(job, 'Nie można zapisać pliku GLB na serwerze.');
  }
}

// ==================================================
// BŁĄD ZADANIA
// ==================================================

function failJob(job, errorMessage) {
  const { jobId, sessionId, agentId } = job;

  const agent = agents.get(agentId);
  const state = readState(sessionId);

  if (state) {
    state.status = 'error';
    state.progress = 0;
    state.error = errorMessage;

    delete state.jobId;

    writeState(sessionId, state);
  }

  jobs.delete(jobId);

  if (agent && agent.jobId === jobId) {
    agent.busy = false;
    agent.jobId = null;
  }

  if (agent && agent.ws.readyState === WebSocket.OPEN) {
    try {
      agent.ws.send(
        JSON.stringify({
          type: 'job_error',
          jobId,
          sessionId,
          error: errorMessage,
        }),
      );
    } catch (_) {
      // Agent mógł rozłączyć się w międzyczasie.
    }
  }

  logError(`Zadanie ${jobId} zakończone błędem:`, errorMessage);

  setImmediate(scanPendingJobs);
}

// ==================================================
// DISCONNECT AGENTA
// ==================================================

function handleAgentDisconnect(agentId, agent) {
  log(`Agent ${agentId} rozłączony.`);

  if (agent.jobId) {
    const jobId = agent.jobId;
    const job = jobs.get(jobId);

    if (job) {
      const state = readState(job.sessionId);

      if (state) {
        state.status = 'uploaded';
        state.progress = 0;

        delete state.jobId;
        delete state.error;

        writeState(job.sessionId, state);
      }

      jobs.delete(jobId);

      log(`Zadanie ${jobId} wróciło do kolejki.`);
    }
  }

  agents.delete(agentId);

  setImmediate(scanPendingJobs);
}

// ==================================================
// EKSPORT
// ==================================================

module.exports = {
  jobs,
  dispatchJob,
  scanPendingJobs,
  finishJob,
  failJob,
  handleAgentDisconnect,
};
