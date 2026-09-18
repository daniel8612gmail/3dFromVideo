require('dotenv').config();

const WebSocket = require('ws');

const DOMAIN = process.env.DOMAIN;
const AGENT_ID = process.env.AGENT_ID;
const AGENT_TOKEN = process.env.AGENT_TOKEN;

if (!DOMAIN || !AGENT_ID || !AGENT_TOKEN) {
    console.error('Brakuje konfiguracji w pliku .env');
    process.exit(1);
}

const URL = `wss://${DOMAIN}/ws`;

let ws = null;
let reconnectTimer = null;
let currentJob = null;
let waitingForGlb = false;

console.log('');
console.log('Image 3D Agent');
console.log('==============');
console.log(`Domain:  ${DOMAIN}`);
console.log(`Agent:   ${AGENT_ID}`);
console.log(`URL:     ${URL}`);
console.log('');

function connect() {
    console.log(`Connecting to ${URL}...`);


    ws = new WebSocket(URL);

    ws.on('open', () => {
        console.log('✓ WebSocket connection established');

        sendAuth();
    });

    ws.on('message', async (data, isBinary) => {
        try {
            if (isBinary) {
                await handleBinaryMessage(data);
                return;
            }

            handleJsonMessage(data.toString());
        } catch (error) {
            console.error('Message handling error:', error.message);
        }
    });

    ws.on('error', (error) => {
        console.error(`✗ WebSocket error: ${error.message} `);
    });

    ws.on('close', (code, reason) => {
        console.log(`Connection closed: ${code}${reason ? ` (${reason})` : ''} `);

        ws = null;
        currentJob = null;
        waitingForGlb = false;

        scheduleReconnect();
    });

}

function sendAuth() {
    sendJson({
        type: 'auth',
        agentId: AGENT_ID,
        token: AGENT_TOKEN
    });
}

function sendJson(message) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        throw new Error('WebSocket is not connected');
    }


    ws.send(JSON.stringify(message));

}

function handleJsonMessage(message) {
    let data;

    try {
        data = JSON.parse(message);
    } catch {
        console.error('Received invalid JSON:', message);
        return;
    }

    switch (data.type) {
        case 'auth_ok':
            handleAuthOk(data);
            break;

        case 'job':
            handleJob(data);
            break;

        case 'ready_for_glb':
            handleReadyForGlb(data);
            break;

        default:
            console.log('Received:', data);
    }

}

function handleAuthOk(data) {
    console.log(`✓ Authentication successful: ${data.agentId}`);
    console.log('Waiting for jobs...');
}

function handleJob(job) {
    if (currentJob) {
        console.error('Received a new job while another job is active.');
        return;
    }

    currentJob = {
        jobId: job.jobId,
        sessionId: job.sessionId,
        filename: job.filename,
        size: job.size,
        photo: null
    };

    waitingForGlb = false;

    console.log('');
    console.log('New job received');
    console.log('----------------');
    console.log(`Job ID:     ${job.jobId} `);
    console.log(`Session ID: ${job.sessionId} `);
    console.log(`Filename:   ${job.filename} `);
    console.log(`Size:       ${job.size} bytes`);
    console.log('');


}

async function handleBinaryMessage(data) {
    if (!currentJob) {
        console.error('Received binary data without an active job.');
        return;
    }


    if (waitingForGlb) {
        console.error('Received unexpected binary data while waiting for GLB.');
        return;
    }

    currentJob.photo = Buffer.from(data);

    console.log(`Photo received: ${currentJob.photo.length} bytes`);

    await processJob();


}

async function setProgress(jobId, progress, stage = null) {
    const message = {
        type: 'progress',
        jobId,
        progress
    };

    if (stage) {
        message.stage = stage;
    }

    ws.send(JSON.stringify(message));
}

async function processJob() {
    console.log('Starting image processing...');


    try {
        for (let progress = 0; progress <= 100; progress += 10) {
            if (!currentJob || !ws || ws.readyState !== WebSocket.OPEN) {
                throw new Error('Connection lost during processing');
            }

            sendJson({
                type: 'progress',
                jobId: currentJob.jobId,
                progress
            });

            console.log(`Progress: ${progress}% `);

            if (progress < 100) {
                await sleep(500);
            }
        }

        /*
         * Tell the server that the next binary message
         * will contain the GLB.
         */
        sendJson({
            type: 'ready_for_glb',
            jobId: currentJob.jobId
        });

        waitingForGlb = true;

        const glb = createTestGlb();

        console.log(`Sending test GLB: ${glb.length} bytes`);

        ws.send(glb);

        console.log('✓ GLB sent');

        currentJob = null;
        waitingForGlb = false;

        console.log('');
        console.log('Waiting for next job...');
    } catch (error) {
        console.error(`Processing failed: ${error.message} `);

        if (currentJob && ws && ws.readyState === WebSocket.OPEN) {
            sendJson({
                type: 'error',
                jobId: currentJob.jobId,
                error: error.message
            });
        }

        currentJob = null;
        waitingForGlb = false;
    }


}

function createTestGlb() {
    /*
    * Minimal GLB-like buffer for protocol testing.
    *
    * The server currently validates only the first
    * four bytes ("glTF") before saving the file.
    *
    * This is NOT a valid 3D model yet.
    */
    const buffer = Buffer.alloc(32);


    buffer.write('glTF', 0, 4, 'ascii');

    // GLB version 2
    buffer.writeUInt32LE(2, 4);

    // Total length
    buffer.writeUInt32LE(buffer.length, 8);

    return buffer;

}

function scheduleReconnect() {
    if (reconnectTimer) {
        return;
    }

    console.log('Reconnecting in 5 seconds...');

    reconnectTimer = setTimeout(() => {
        reconnectTimer = null;
        connect();
    }, 5000);


}

function sleep(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
}

process.on('SIGINT', () => {
    console.log('');
    console.log('Stopping agent...');


    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }

    if (ws) {
        ws.close();
    }

    process.exit(0);


});

connect();
