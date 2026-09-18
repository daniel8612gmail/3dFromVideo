'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const WebSocket = require('ws');
const chokidar = require('chokidar');
require('dotenv').config();

// ==================================================
// KONFIGURACJA
// ==================================================

const DATA_DIR = path.resolve(
    process.env.DATA_DIR || '../public_html/data'
);

const PORT = Number(process.env.PORT || 8443);

const AGENTS_FILE = path.resolve(
    process.env.AGENTS_FILE || './agents.json'
);

const HOST = '127.0.0.1';

// ==================================================
// POMOCNICZE
// ==================================================

function log(...args) {
    console.log(new Date().toISOString(), ...args);
}

function logError(...args) {
    console.error(new Date().toISOString(), ...args);
}

function readJson(filePath) {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
}

function writeJsonAtomic(filePath, data) {
    const tmpPath = `${ filePath }.${ process.pid }.tmp`;

    fs.writeFileSync(
        tmpPath,
        JSON.stringify(data, null, 4),
        'utf8'
    );

    fs.renameSync(tmpPath, filePath);
}

function readState(sessionId) {
    const statePath = path.join(
        DATA_DIR,
        sessionId,
        'state.json'
    );

    try {
        return readJson(statePath);
    } catch (error) {
        logError(
            `Nie można odczytać state.json dla ${ sessionId }: `,
            error.message
        );

        return null;
    }
}

function writeState(sessionId, state) {
    const sessionDir = path.join(
        DATA_DIR,
        sessionId
    );

    const statePath = path.join(
        sessionDir,
        'state.json'
    );

    writeJsonAtomic(statePath, state);
}

function isValidSessionId(sessionId) {
    return (
        typeof sessionId === 'string' &&
        /^[a-f0-9]{32}$/.test(sessionId)
    );
}

function isValidPhotoFilename(filename) {
    return (
        typeof filename === 'string' &&
        /^photo\.(jpg|jpeg|png|webp)$/i.test(filename)
    );
}

function isValidProgress(value) {
    return (
        Number.isInteger(value) &&
        value >= 0 &&
        value <= 100
    );
}

// ==================================================
// AGENTY
// ==================================================

function loadAgents() {
    try {
        const config = readJson(AGENTS_FILE);

        if (
            !config ||
            typeof config.agents !== 'object' ||
            config.agents === null
        ) {
            throw new Error(
                'Nieprawidłowy format agents.json.'
            );
        }

        return config.agents;

    } catch (error) {

        logError(
            'Nie można załadować agents.json:',
            error.message
        );

        process.exit(1);
    }
}

let authorizedAgents = loadAgents();

/*
 * agents:
 *
 * {
 *   "agent-01": {
 *      "token": "..."
 *   },
 *   "agent-02": {
 *      "token": "..."
 *   }
 * }
 */

function reloadAgents() {
    authorizedAgents = loadAgents();
    log('Przeładowano listę autoryzowanych agentów.');
}

// ==================================================
// PODŁĄCZONE AGENTY
// ==================================================

/*
 * Map:
 *
 * agentId -> {
 *     ws,
 *     authenticated,
 *     busy,
 *     jobId
 * }
 */

const agents = new Map();

// ==================================================
// ZADANIA
// ==================================================

/*
 * jobId -> {
 *     jobId,
 *     sessionId,
 *     agentId
 * }
 */

const jobs = new Map();

// ==================================================
// AUTORYZACJA
// ==================================================

function safeTokenCompare(received, expected) {

    if (
        typeof received !== 'string' ||
        typeof expected !== 'string'
    ) {
        return false;
    }

    const receivedBuffer = Buffer.from(received);
    const expectedBuffer = Buffer.from(expected);

    if (
        receivedBuffer.length !== expectedBuffer.length
    ) {
        return false;
    }

    return crypto.timingSafeEqual(
        receivedBuffer,
        expectedBuffer
    );
}

function authenticateAgent(ws, agentId, token) {

    const config = authorizedAgents[agentId];

    if (!config || typeof config.token !== 'string') {
        return false;
    }

    return safeTokenCompare(
        token,
        config.token
    );
}

// ==================================================
// WYSZUKIWANIE WOLNEGO AGENTA
// ==================================================

function getIdleAgent() {

    for (const [agentId, agent] of agents) {

        if (
            agent.authenticated &&
            !agent.busy &&
            agent.ws.readyState === WebSocket.OPEN
        ) {
            return {
                agentId,
                agent
            };
        }
    }

    return null;
}

// ==================================================
// WYSYŁANIE ZADANIA
// ==================================================

function dispatchJob(sessionId, agentId, agent) {

    const sessionDir = path.join(
        DATA_DIR,
        sessionId
    );

    const state = readState(sessionId);

    if (!state) {
        return false;
    }

    if (state.status !== 'uploaded') {
        return false;
    }

    const files = fs.readdirSync(sessionDir);

    const photoFilename = files.find(
        isValidPhotoFilename
    );

    if (!photoFilename) {
        log(
            `Brak zdjęcia dla sesji ${ sessionId }.`
        );

        return false;
    }

    const photoPath = path.join(
        sessionDir,
        photoFilename
    );

    const stat = fs.statSync(photoPath);

    const jobId = crypto.randomUUID();

    const job = {
        jobId,
        sessionId,
        agentId
    };

    jobs.set(jobId, job);

    agent.busy = true;
    agent.jobId = jobId;

    state.status = 'processing';
    state.progress = 0;
    state.jobId = jobId;

    writeState(
        sessionId,
        state
    );

    try {

        agent.ws.send(
            JSON.stringify({
                type: 'job',
                jobId,
                sessionId,
                filename: photoFilename,
                size: stat.size
            })
        );

        const photoBuffer = fs.readFileSync(
            photoPath
        );

        agent.ws.send(
            photoBuffer,
            {
                binary: true
            }
        );

        log(
            `Wysłano zadanie ${ jobId } ` +
            `dla sesji ${ sessionId } ` +
            `do agenta ${ agentId }.`
        );

        return true;

    } catch (error) {

        logError(
            `Błąd wysyłania zadania ${ jobId }: `,
            error.message
        );

        jobs.delete(jobId);

        agent.busy = false;
        agent.jobId = null;

        state.status = 'uploaded';
        state.progress = 0;
        delete state.jobId;

        writeState(
            sessionId,
            state
        );

        return false;
    }
}

// ==================================================
// PRZESZUKIWANIE OCZEKUJĄCYCH SESJI
// ==================================================

function scanPendingJobs() {

    let entries;

    try {
        entries = fs.readdirSync(
            DATA_DIR,
            {
                withFileTypes: true
            }
        );
    } catch (error) {

        logError(
            'Nie można odczytać DATA_DIR:',
            error.message
        );

        return;
    }

    for (const entry of entries) {

        if (!entry.isDirectory()) {
            continue;
        }

        const sessionId = entry.name;

        if (!isValidSessionId(sessionId)) {
            continue;
        }

        const state = readState(sessionId);

        if (
            !state ||
            state.status !== 'uploaded'
        ) {
            continue;
        }

        const availableAgent =
            getIdleAgent();

        if (!availableAgent) {
            return;
        }

        dispatchJob(
            sessionId,
            availableAgent.agentId,
            availableAgent.agent
        );
    }
}

// ==================================================
// ZAKOŃCZENIE ZADANIA
// ==================================================

function finishJob(
    job,
    glbBuffer
) {

    const {
        jobId,
        sessionId,
        agentId
    } = job;

    const agent = agents.get(agentId);

    if (!agent) {
        logError(
            `Agent ${ agentId } nie istnieje przy zakończeniu zadania.`
        );
        return;
    }

    // ----------------------------------------------
    // Walidacja GLB
    // ----------------------------------------------

    if (
        !Buffer.isBuffer(glbBuffer) ||
        glbBuffer.length < 4
    ) {

        logError(
            `Nieprawidłowy GLB dla zadania ${ jobId }.`
        );

        return failJob(
            job,
            'Odebrano nieprawidłowy plik GLB.'
        );
    }

    const magic = glbBuffer
        .subarray(0, 4)
        .toString('ascii');

    if (magic !== 'glTF') {

        logError(
            `Nieprawidłowy nagłówek GLB dla ${ jobId }.`
        );

        return failJob(
            job,
            'Odebrany plik nie jest poprawnym GLB.'
        );
    }

    // ----------------------------------------------
    // Zapis atomowy
    // ----------------------------------------------

    const sessionDir = path.join(
        DATA_DIR,
        sessionId
    );

    const modelPath = path.join(
        sessionDir,
        'model.glb'
    );

    const tmpPath = `${ modelPath }.${ process.pid }.tmp`;

    try {

        fs.writeFileSync(
            tmpPath,
            glbBuffer
        );

        fs.renameSync(
            tmpPath,
            modelPath
        );

        const state = readState(
            sessionId
        );

        if (state) {

            state.status = 'ready';
            state.progress = 100;
            state.glb = 'model.glb';

            delete state.jobId;

            writeState(
                sessionId,
                state
            );
        }

        jobs.delete(jobId);

        agent.busy = false;
        agent.jobId = null;

        agent.ws.send(
            JSON.stringify({
                type: 'job_complete',
                jobId,
                sessionId
            })
        );

        log(
            `Zadanie ${ jobId } zakończone. ` +
            `Model zapisany dla sesji ${ sessionId }.`
        );

        // Sprawdź czy nie czeka kolejne zadanie.
        setImmediate(
            scanPendingJobs
        );

    } catch (error) {

        try {
            if (fs.existsSync(tmpPath)) {
                fs.unlinkSync(tmpPath);
            }
        } catch (_) {}

        logError(
            `Nie można zapisać GLB dla ${ jobId }: `,
            error.message
        );

        failJob(
            job,
            'Nie można zapisać pliku GLB na serwerze.'
        );
    }
}

// ==================================================
// BŁĄD ZADANIA
// ==================================================

function failJob(
    job,
    errorMessage
) {

    const {
        jobId,
        sessionId,
        agentId
    } = job;

    const agent = agents.get(agentId);

    const state = readState(
        sessionId
    );

    if (state) {

        state.status = 'error';
        state.progress = 0;
        state.error = errorMessage;

        delete state.jobId;

        writeState(
            sessionId,
            state
        );
    }

    jobs.delete(jobId);

    if (
        agent &&
        agent.jobId === jobId
    ) {
        agent.busy = false;
        agent.jobId = null;
    }

    if (
        agent &&
        agent.ws.readyState === WebSocket.OPEN
    ) {

        try {

            agent.ws.send(
                JSON.stringify({
                    type: 'job_error',
                    jobId,
                    sessionId,
                    error: errorMessage
                })
            );

        } catch (_) {}
    }

    logError(
        `Zadanie ${ jobId } zakończone błędem: `,
        errorMessage
    );

    setImmediate(
        scanPendingJobs
    );
}

// ==================================================
// DISCONNECT AGENTA
// ==================================================

function handleAgentDisconnect(
    agentId,
    agent
) {

    log(
        `Agent ${ agentId } rozłączony.`
    );

    if (agent.jobId) {

        const jobId = agent.jobId;

        const job = jobs.get(
            jobId
        );

        if (job) {

            const state = readState(
                job.sessionId
            );

            if (state) {

                state.status = 'uploaded';
                state.progress = 0;

                delete state.jobId;
                delete state.error;

                writeState(
                    job.sessionId,
                    state
                );
            }

            jobs.delete(
                jobId
            );

            log(
                `Zadanie ${ jobId } ` +
                `wróciło do kolejki.`
            );
        }
    }

    agents.delete(
        agentId
    );

    setImmediate(
        scanPendingJobs
    );
}

// ==================================================
// WEBSOCKET SERVER
// ==================================================

const wss = new WebSocket.Server({
    host: HOST,
    port: PORT,
    maxPayload: 200 * 1024 * 1024
});

log(
    `WebSocket server uruchomiony na ` +
    `ws://${HOST}:${PORT}`
);

// ==================================================
// POŁĄCZENIE
// ==================================================

wss.on('connection', (ws) => {

    let authenticated = false;
    let agentId = null;

    let currentBinaryJob = null;

    const authTimeout = setTimeout(() => {

        if (!authenticated) {

            log(
                'Połączenie zamknięte: ' +
                'brak autoryzacji.'
            );

            ws.close(
                1008,
                'Authentication timeout'
            );
        }

    }, 10000);

    ws.on('message', (message, isBinary) => {

        // ------------------------------------------
        // Dane binarne
        // ------------------------------------------

        if (isBinary) {

            if (!authenticated) {
                ws.close(
                    1008,
                    'Not authenticated'
                );
                return;
            }

            if (!currentBinaryJob) {

                logError(
                    `Agent ${agentId} ` +
                    `wysłał dane binarne bez oczekującego zadania.`
                );

                return;
            }

            const job =
                jobs.get(
                    currentBinaryJob
                );

            if (!job) {

                currentBinaryJob = null;
                return;
            }

            finishJob(
                job,
                Buffer.from(message)
            );

            currentBinaryJob = null;

            return;
        }

        // ------------------------------------------
        // JSON
        // ------------------------------------------

        let data;

        try {

            data = JSON.parse(
                message.toString()
            );

        } catch (error) {

            ws.send(
                JSON.stringify({
                    type: 'error',
                    error: 'Nieprawidłowy JSON.'
                })
            );

            return;
        }

        // ------------------------------------------
        // AUTH
        // ------------------------------------------

        if (data.type === 'auth') {

            if (authenticated) {
                return;
            }

            const requestedAgentId =
                data.agentId;

            const token =
                data.token;

            if (
                !authenticateAgent(
                    ws,
                    requestedAgentId,
                    token
                )
            ) {

                log(
                    `Odrzucono autoryzację agenta: ` +
                    `${requestedAgentId || '(brak ID)'}`
                );

                ws.close(
                    1008,
                    'Unauthorized'
                );

                return;
            }

            clearTimeout(
                authTimeout
            );

            // --------------------------------------
            // Jeden agent = jedno połączenie
            // --------------------------------------

            const existing =
                agents.get(
                    requestedAgentId
                );

            if (existing) {

                log(
                    `Agent ${requestedAgentId} ` +
                    `jest już połączony.`
                );

                ws.close(
                    1008,
                    'Agent already connected'
                );

                return;
            }

            authenticated = true;
            agentId = requestedAgentId;

            agents.set(
                agentId,
                {
                    ws,
                    authenticated: true,
                    busy: false,
                    jobId: null
                }
            );

            log(
                `Agent ${agentId} ` +
                `został autoryzowany.`
            );

            ws.send(
                JSON.stringify({
                    type: 'auth_ok',
                    agentId
                })
            );

            scanPendingJobs();

            return;
        }

        // ------------------------------------------
        // Wszystko poniżej wymaga autoryzacji
        // ------------------------------------------

        if (!authenticated) {

            ws.close(
                1008,
                'Not authenticated'
            );

            return;
        }

        const agent =
            agents.get(agentId);

        if (!agent) {
            return;
        }

        // ------------------------------------------
        // PROGRESS
        // ------------------------------------------

        if (data.type === 'progress') {

            const job =
                jobs.get(
                    data.jobId
                );

            if (
                !job ||
                job.agentId !== agentId
            ) {
                return;
            }

            if (
                !isValidProgress(
                    data.progress
                )
            ) {
                return;
            }

            const state =
                readState(
                    job.sessionId
                );

            if (!state) {
                return;
            }

            state.status = 'processing';
            state.progress = data.progress;

            writeState(
                job.sessionId,
                state
            );

            log(
                `Agent ${agentId}: ` +
                `zadanie ${job.jobId}: ` +
                `${data.progress}%`
            );

            return;
        }

        // ------------------------------------------
        // AGENT CZEKA NA GLB
        // ------------------------------------------

        if (data.type === 'ready_for_glb') {

            const job =
                jobs.get(
                    data.jobId
                );

            if (
                !job ||
                job.agentId !== agentId
            ) {
                return;
            }

            currentBinaryJob =
                data.jobId;

            return;
        }

        // ------------------------------------------
        // ERROR
        // ------------------------------------------

        if (data.type === 'error') {

            const job =
                jobs.get(
                    data.jobId
                );

            if (
                !job ||
                job.agentId !== agentId
            ) {
                return;
            }

            failJob(
                job,
                typeof data.error === 'string'
                    ? data.error
                    : 'Nieznany błąd agenta.'
            );

            return;
        }

        // ------------------------------------------
        // UNKNOWN MESSAGE
        // ------------------------------------------

        log(
            `Nieznany komunikat od agenta ${agentId}:`,
            data.type
        );
    });

    ws.on('close', () => {

        clearTimeout(
            authTimeout
        );

        if (!authenticated) {
            return;
        }

        const agent =
            agents.get(agentId);

        if (!agent) {
            return;
        }

        // Nie obsługuj starego połączenia,
        // jeśli agent został zastąpiony.
        if (agent.ws !== ws) {
            return;
        }

        handleAgentDisconnect(
            agentId,
            agent
        );
    });

    ws.on('error', (error) => {

        logError(
            `Błąd WebSocket agenta ${agentId || '?'}:`,
            error.message
        );
    });
});

// ==================================================
// OBSERWATOR DATA
// ==================================================

const photoPattern =
    path.join(
        DATA_DIR,
        '*',
        'photo.{jpg,jpeg,png,webp}'
    );

const watcher = chokidar.watch(
    photoPattern,
    {
        ignoreInitial: false,

        awaitWriteFinish: {
            stabilityThreshold: 1000,
            pollInterval: 100
        }
    }
);

watcher.on(
    'add',
    (photoPath) => {

        const sessionDir =
            path.dirname(photoPath);

        const sessionId =
            path.basename(sessionDir);

        if (
            !isValidSessionId(
                sessionId
            )
        ) {
            return;
        }

        log(
            `Wykryto zdjęcie: ${photoPath}`
        );

        setTimeout(
            scanPendingJobs,
            100
        );
    }
);

watcher.on(
    'error',
    (error) => {

        logError(
            'Błąd obserwatora plików:',
            error
        );
    }
);

// ==================================================
// OBSŁUGA SIGHUP
// ==================================================

process.on('SIGHUP', () => {

    log(
        'Otrzymano SIGHUP.'
    );

    reloadAgents();
});

// ==================================================
// ZAMKNIĘCIE
// ==================================================

function shutdown(signal) {

    log(
        `Otrzymano ${signal}. Zamykanie...`
    );

    watcher.close();

    for (const [, agent] of agents) {

        try {
            agent.ws.close(
                1001,
                'Server shutdown'
            );
        } catch (_) { }
    }

    wss.close(
        () => {
            process.exit(0);
        }
    );

    setTimeout(
        () => process.exit(1),
        5000
    );
}

process.on(
    'SIGTERM',
    () => shutdown('SIGTERM')
);

process.on(
    'SIGINT',
    () => shutdown('SIGINT')
);

// ==================================================
// INFORMACJE STARTOWE
// ==================================================

log(
    `DATA_DIR: ${DATA_DIR}`
);

log(
    `AGENTS_FILE: ${AGENTS_FILE}`
);

log(
    `Autoryzowanych agentów: ` +
    `${Object.keys(authorizedAgents).length}`
);
