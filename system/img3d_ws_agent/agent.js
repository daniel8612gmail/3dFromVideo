require("dotenv").config();
const runPython = require("./runPython");

const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");
const { spawn } = require("child_process");

// ============================================================
// KONFIGURACJA
// ============================================================

const DOMAIN = process.env.DOMAIN;
const AGENT_ID = process.env.AGENT_ID;
const AGENT_TOKEN = process.env.AGENT_TOKEN;
const AGENT_DATA_DIR = path.join(process.env.WORKING_DIR || __dirname, "data");

const RECONNECT_DELAY = 5000;

if (!DOMAIN || !AGENT_ID || !AGENT_TOKEN) {
  console.error("Brakuje konfiguracji w pliku .env");
  console.error("");
  console.error("Wymagane zmienne:");
  console.error("  DOMAIN");
  console.error("  AGENT_ID");
  console.error("  AGENT_TOKEN");
  process.exit(1);
}

const WS_URL = `wss://${DOMAIN}/ws`;

// ============================================================
// STAN AGENTA
// ============================================================

let ws = null;
let reconnectTimer = null;

let currentJob = null;

// ============================================================
// POŁĄCZENIE Z SERWEREM
// ============================================================

function connect() {
  console.log("");
  console.log(`Łączenie z: ${WS_URL}`);
  console.log(`Agent: ${AGENT_ID}`);
  console.log("");

  ws = new WebSocket(WS_URL);

  ws.on("open", () => {
    console.log("Połączono z serwerem");

    send({
      type: "auth",
      agentId: AGENT_ID,
      token: AGENT_TOKEN,
    });
  });

  ws.on("message", async (data, isBinary) => {
    try {
      // ------------------------------------------------
      // WIADOMOŚĆ JSON
      // ------------------------------------------------

      if (!isBinary) {
        const message = JSON.parse(data.toString());

        await handleMessage(message);

        return;
      }

      // ------------------------------------------------
      // DANE BINARNE — POWINNO BYĆ TO ZDJĘCIE
      // ------------------------------------------------

      if (!currentJob) {
        console.error("Otrzymano dane binarne, ale nie ma aktywnego zadania.");

        return;
      }

      const imageBuffer = Buffer.from(data);

      console.log("");
      console.log(`Otrzymano zdjęcie: ${imageBuffer.length} bajtów`);

      const job = currentJob;

      // Zabezpieczenie przed przyjęciem drugiego zadania
      // podczas przetwarzania pierwszego.
      currentJob = {
        ...job,
        imageBuffer,
      };

      try {
        await processJob(job.jobId, imageBuffer, job.sessionId, job.filename);
      } catch (error) {
        console.error("");
        console.error(`Błąd podczas wykonywania job ${job.jobId}:`);

        console.error(error);

        send({
          type: "error",
          jobId: job.jobId,
          error: error.message || String(error),
        });
      } finally {
        currentJob = null;
      }
    } catch (error) {
      console.error("Błąd obsługi wiadomości:", error);
    }
  });

  ws.on("close", (code, reason) => {
    console.log("");
    console.log(
      `Połączenie zamknięte: ${code}` + (reason ? ` (${reason})` : ""),
    );

    ws = null;

    scheduleReconnect();
  });

  ws.on("error", (error) => {
    console.error("Błąd WebSocket:", error.message);
  });
}

// ============================================================
// OBSŁUGA WIADOMOŚCI OD SERWERA
// ============================================================

async function handleMessage(message) {
  switch (message.type) {
    // ----------------------------------------------------
    // AUTORYZACJA
    // ----------------------------------------------------

    case "auth_ok":
      console.log(`Autoryzacja OK: ${message.agentId}`);

      break;

    // ----------------------------------------------------
    // NOWE ZADANIE
    // ----------------------------------------------------

    case "job":
      if (currentJob) {
        console.error("");
        console.error(
          "BŁĄD: serwer wysłał nowe zadanie, " + "mimo że agent jest zajęty.",
        );

        console.error(`Aktualne zadanie: ${currentJob.jobId}`);

        console.error(`Nowe zadanie: ${message.jobId}`);

        return;
      }

      currentJob = {
        jobId: message.jobId,
        sessionId: message.sessionId,
        filename: message.filename,
        size: message.size,
        imageBuffer: null,
      };

      console.log("");
      console.log("========================================");
      console.log("NOWE ZADANIE");
      console.log("========================================");
      console.log(`Job:      ${message.jobId}`);
      console.log(`Session:  ${message.sessionId}`);
      console.log(`Filename: ${message.filename}`);
      console.log(`Size:     ${message.size}`);
      console.log("Oczekiwanie na zdjęcie...");
      console.log("========================================");

      break;

    // ----------------------------------------------------
    // INNE WIADOMOŚCI
    // ----------------------------------------------------

    default:
      console.log("Serwer:", message);

      break;
  }
}

// ============================================================
// WYSYŁANIE JSON DO SERWERA
// ============================================================

function send(message) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    throw new Error("WebSocket nie jest połączony.");
  }

  ws.send(JSON.stringify(message));
}

// ============================================================
// RAPORTOWANIE PROGRESSU
// ============================================================

async function setProgress(jobId, progress, stage = null, text = "") {
  const message = {
    type: "progress",
    jobId,
    progress,
  };

  if (stage !== null) {
    message.stage = stage;
  }
  if (text !== "") {
    message.text = text;
  }

  send(message);

  console.log(`[${jobId}] ${progress}%` + (stage ? ` — ${stage}` : ""));
}

function sendLog(jobId, message) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }

  ws.send(
    JSON.stringify({
      type: "progress",
      jobId,
      message,
    }),
  );
}

// ============================================================
// GŁÓWNY PIPELINE
// ============================================================

async function processJob(jobId, imageBuffer, sessionId, filename) {
  console.log("");
  console.log(`Rozpoczynam przetwarzanie: ${jobId}`);

  const context = {
    jobId,
    sessionId,
    filename,
    log: (message) => sendLog(jobId, message),
  };

  await setProgress(jobId, 0, "starting");

  let data = imageBuffer;

  for (const step of pipeline) {
    console.log("");
    console.log(`[${jobId}] Etap: ${step.stage}`);

    data = await step.run(data, context);

    await setProgress(jobId, step.progress, step.stage);
  }

  if (!Buffer.isBuffer(data)) {
    throw new Error("Pipeline nie zwrócił Buffer z plikiem GLB.");
  }

  send({
    type: "ready_for_glb",
    jobId,
  });

  ws.send(data);

  console.log("");
  console.log(`[${jobId}] Wysłano GLB: ${data.length} bajtów`);
}

// ============================================================
// PIPELINE — TUTAJ DODAJEMY WŁASNE FUNKCJE
// ============================================================
//
// progress = wartość po zakończeniu danego etapu
//
// run = funkcja wykonująca etap
//
// Dane przepływają:
//
// imageBuffer
//     ↓
// prepareImage()
//     ↓
// wynik
//     ↓
// segment()
//     ↓
// wynik
//     ↓
// generate3D()
//     ↓
// wynik
//     ↓
// exportGLB()
//     ↓
// Buffer GLB
//
// ============================================================

const pipeline = [
  {
    progress: 20,
    stage: "prepare_image",
    run: prepareImage,
  },

  {
    progress: 40,
    stage: "moge3",
    run: runMoGe3,
  },

  {
    progress: 60,
    stage: "generate3D",
    run: generate3D,
  },

  {
    progress: 95,
    stage: "export_glb",
    run: exportGLB,
  },
];

// ============================================================
// FUNKCJE PIPELINU
// ============================================================
//
// Tutaj będziemy pisać właściwy kod Image → 3D.
//
// Każda funkcja:
//     przyjmuje wynik poprzedniej
//     wykonuje swój etap
//     zwraca wynik dla następnego etapu
//
// ============================================================

async function prepareImage(imageBuffer, context) {
  console.log(`prepareImage(): ${imageBuffer.length} bajtów`);

  const { sessionId, filename } = context;

  // sessionId z serwera musi być dokładnie 32 znakami hex
  if (!/^[a-f0-9]{32}$/.test(sessionId)) {
    throw new Error(`Nieprawidłowy sessionId: ${sessionId}`);
  }

  // Dopuszczamy tylko nasze rozszerzenia.
  const extension = path.extname(filename).toLowerCase();

  if (![".jpg", ".jpeg", ".png", ".webp"].includes(extension)) {
    throw new Error(`Nieprawidłowe rozszerzenie obrazu: ${extension}`);
  }

  const sessionDir = path.join(AGENT_DATA_DIR, sessionId);

  await fs.promises.mkdir(sessionDir, {
    recursive: true,
  });

  const imagePath = path.join(sessionDir, `photo${extension}`);

  await fs.promises.writeFile(imagePath, imageBuffer);

  console.log(`Zdjęcie zapisane: ${imagePath}`);

  return {
    imageBuffer,
    imagePath,
  };
}

async function runMoGe3(data, context) {
  const sessionDir = path.join(AGENT_DATA_DIR, context.sessionId);
  console.log("Uruchamiam MoGe3:");
  console.log(`Katalog: ${sessionDir}`);

  await runPython(context, "../py/ai_moge3.py", ["-i", sessionDir]);
}

async function generate3D(data, context) {
  const sessionDir = path.join(AGENT_DATA_DIR, context.sessionId);
  console.log("Uruchamiam geom_process.py");
  console.log(`Katalog: ${sessionDir}`);

  await runPython(context, "../py/geom_process.py", ["-i", sessionDir]);
}

async function exportGLB(data, context) {
  const sessionDir = path.join(AGENT_DATA_DIR, context.sessionId);

  const imageName = path.parse(context.filename).name;
  const glbPath = path.join(sessionDir, imageName, `${imageName}_planes.glb`);

  context.log(`Export GLB: ${glbPath} `);

  try {
    const glb = await fs.promises.readFile(glbPath);

    context.log(`GLB wczytany: ${glb.length} bajtów`);

    return glb;
  } catch (error) {
    throw new Error(
      `Nie można odczytać pliku GLB "${glbPath}": ${error.message} `,
    );
  }
}

// ============================================================
// RECONNECT
// ============================================================

function scheduleReconnect() {
  if (reconnectTimer) {
    return;
  }

  console.log(`Ponowne połączenie za ${RECONNECT_DELAY / 1000} s...`);

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;

    connect();
  }, RECONNECT_DELAY);
}

// ============================================================
// ZAMKNIĘCIE CTRL+C
// ============================================================

process.on("SIGINT", () => {
  console.log("");
  console.log("Zamykanie agenta...");

  if (ws) {
    ws.close();
  }

  process.exit(0);
});

// ============================================================
// START
// ============================================================

connect();
