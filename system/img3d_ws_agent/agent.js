require("dotenv").config();
const runPython = require("./runPython");
const glbOutputPath = require("./glbOutputPath");
const pythonInputArgs = require("./pipelineArgs");

const WebSocket = require("ws");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");
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
        if (imageBuffer.length !== job.size) {
          throw new Error("Odebrany rozmiar obrazu nie odpowiada metadanym joba.");
        }
        if (job.jobType === "system_frame"
          && crypto.createHash("sha256").update(imageBuffer).digest("hex") !== job.sha256) {
          throw new Error("SHA-256 obrazu nie odpowiada zadaniu systemowemu.");
        }
        await processJob(
          job.jobId,
          imageBuffer,
          job.sessionId,
          job.filename,
          job.jobType || "legacy",
          job.systemSessionId,
          job.frameId,
        );
      } catch (error) {
        console.error("");
        console.error(`Błąd podczas wykonywania job ${job.jobId}:`);

        console.error(error);

        send({
          type: "error",
          jobId: job.jobId,
          ...(job.jobType === "system_frame" ? {
            jobType: "system_frame",
            systemSessionId: job.systemSessionId,
            frameId: job.frameId,
          } : {}),
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

      if (message.jobType === "system_frame"
        && (!/^[a-f0-9]{32}$/.test(message.systemSessionId || "")
          || !/^[A-Za-z0-9_-]{1,96}$/.test(message.frameId || ""))) {
        console.error("Odrzucono nieprawidłowy identyfikator zadania systemowego.");
        return;
      }
      if (message.jobType !== undefined && message.jobType !== "system_frame") {
        console.error("Odrzucono nieznany jobType.");
        return;
      }
      if (!Number.isSafeInteger(message.size) || message.size < 1 || message.size > 20 * 1024 * 1024) {
        console.error("Odrzucono nieprawidłowy rozmiar obrazu.");
        return;
      }
      currentJob = {
        jobId: message.jobId,
        sessionId: message.sessionId,
        jobType: message.jobType || "legacy",
        systemSessionId: message.systemSessionId,
        frameId: message.frameId,
        filename: message.filename,
        sha256: message.sha256,
        size: message.size,
        imageBuffer: null,
      };

      console.log("");
      console.log("========================================");
      console.log("NOWE ZADANIE");
      console.log("========================================");
      console.log(`Job:      ${message.jobId}`);
      console.log(`Session:  ${message.systemSessionId || message.sessionId}`);
      if (message.jobType === "system_frame") {
        console.log(`Frame:    ${message.frameId}`);
      }
      console.log(`Filename: ${message.filename}`);
      console.log(`Size:     ${message.size}`);
      console.log("Oczekiwanie na zdjęcie...");
      console.log("========================================");

      break;

    case "aggregation_started":
      if (message.jobType === "system_frame"
        && /^[a-f0-9]{32}$/.test(message.systemSessionId || "")
        && /^[A-Za-z0-9_-]{1,96}$/.test(message.frameId || "")) {
        console.log(
          `Serwer agreguje ${message.systemSessionId}/${message.frameId}`
          + ` przez ${message.aggregator || "nieznany agregator"}.`,
        );
      }

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

async function setProgress(jobId, progress, stage = null, text = "", jobContext = null) {
  const message = {
    type: "progress",
    jobId,
    progress,
  };
  if (jobContext && jobContext.jobType === "system_frame") {
    message.jobType = "system_frame";
    message.systemSessionId = jobContext.systemSessionId;
    message.frameId = jobContext.frameId;
  }

  if (stage !== null) {
    message.stage = stage;
  }
  if (text !== "") {
    message.text = text;
  }

  send(message);

  console.log(`[${jobId}] ${progress}%` + (stage ? ` — ${stage}` : ""));
}

function sendLog(jobId, message, context = null) {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return;
  }

  ws.send(
    JSON.stringify({
      type: "progress",
      jobId,
      ...(context && context.jobType === "system_frame" ? {
        jobType: "system_frame",
        systemSessionId: context.systemSessionId,
        frameId: context.frameId,
      } : {}),
      message,
    }),
  );
}

// ============================================================
// GŁÓWNY PIPELINE
// ============================================================

async function processJob(jobId, imageBuffer, sessionId, filename, jobType = "legacy", systemSessionId = null, frameId = null) {
  console.log("");
  console.log(`Rozpoczynam przetwarzanie: ${jobId}`);

  const context = {
    jobId,
    sessionId,
    filename,
    jobType,
    systemSessionId,
    frameId,
    log: (message) => sendLog(jobId, message, { jobType, systemSessionId, frameId }),
  };

  await setProgress(jobId, 0, "starting", "", context);

  let data = imageBuffer;

  for (const step of pipeline) {
    console.log("");
    console.log(`[${jobId}] Etap: ${step.stage}`);

    data = await step.run(data, context);

    await setProgress(jobId, step.progress, step.stage, "", context);
  }

  if (!Buffer.isBuffer(data)) {
    throw new Error("Pipeline nie zwrócił Buffer z plikiem GLB.");
  }

  send({
    type: jobType === "system_frame" ? "ready_for_frame_glb" : "ready_for_glb",
    jobId,
    ...(jobType === "system_frame" ? {
      jobType,
      systemSessionId,
      frameId,
      conventionSidecar: context.conventionSidecar,
    } : {}),
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

function workingSessionDir(context) {
  if (context.jobType === "system_frame") {
    if (!/^[a-f0-9]{32}$/.test(context.systemSessionId || "")
      || !/^[A-Za-z0-9_-]{1,96}$/.test(context.frameId || "")) {
      throw new Error("Nieprawidłowy identyfikator systemSessionId/frameId.");
    }
    return path.join(AGENT_DATA_DIR, "system-sessions", context.systemSessionId, "frames", context.frameId);
  }
  if (!/^[a-f0-9]{32}$/.test(context.sessionId || "")) {
    throw new Error(`Nieprawidłowy sessionId: ${context.sessionId}`);
  }
  return path.join(AGENT_DATA_DIR, context.sessionId);
}

async function prepareImage(imageBuffer, context) {
  console.log(`prepareImage(): ${imageBuffer.length} bajtów`);

  const { sessionId, filename } = context;

  // Dopuszczamy tylko nasze rozszerzenia.
  const extension = path.extname(filename).toLowerCase();

  if (![".jpg", ".jpeg", ".png", ".webp"].includes(extension)) {
    throw new Error(`Nieprawidłowe rozszerzenie obrazu: ${extension}`);
  }

  const sessionDir = workingSessionDir(context);

  await fs.promises.mkdir(sessionDir, {
    recursive: true,
  });

  const imageName = context.jobType === "system_frame" ? "frame" : "photo";
  const imagePath = path.join(sessionDir, `${imageName}${extension}`);

  await fs.promises.writeFile(imagePath, imageBuffer);

  console.log(`Zdjęcie zapisane: ${imagePath}`);

  return {
    imageBuffer,
    imagePath,
  };
}

async function runMoGe3(data, context) {
  const sessionDir = workingSessionDir(context);
  console.log("Uruchamiam MoGe3:");
  console.log(`Katalog: ${sessionDir}`);

  await runPython(context, "../py/ai_moge3.py", pythonInputArgs(sessionDir, context));
}

async function generate3D(data, context) {
  const sessionDir = workingSessionDir(context);
  console.log("Uruchamiam geom_process.py");
  console.log(`Katalog: ${sessionDir}`);

  await runPython(context, "../py/geom_process.py", pythonInputArgs(sessionDir, context));
}

async function exportGLB(data, context) {
  const sessionDir = workingSessionDir(context);

  const glbPath = glbOutputPath(sessionDir, context.filename, context.jobType);

  context.log(`Export GLB: ${glbPath} `);

  try {
    const glb = await fs.promises.readFile(glbPath);

    context.log(`GLB wczytany: ${glb.length} bajtów`);

    if (context.jobType === "system_frame") {
      const sidecarPath = `${glbPath}.convention.json`;
      const sidecarStat = await fs.promises.lstat(sidecarPath);
      if (!sidecarStat.isFile() || sidecarStat.size < 1 || sidecarStat.size > 64 * 1024) {
        throw new Error("Brak prawidłowego sidecara konwencji GLB.");
      }
      const [glbRealPath, sidecarRealPath] = await Promise.all([
        fs.promises.realpath(glbPath),
        fs.promises.realpath(sidecarPath),
      ]);
      if (path.dirname(glbRealPath) !== path.dirname(sidecarRealPath)) {
        throw new Error("Sidecar konwencji nie znajduje się obok pliku GLB.");
      }
      let sidecar;
      try {
        sidecar = JSON.parse(await fs.promises.readFile(sidecarPath, "utf8"));
      } catch (error) {
        throw new Error(`Nie można odczytać sidecara konwencji GLB: ${error.message}`);
      }
      const glbSha256 = crypto.createHash("sha256").update(glb).digest("hex");
      if (!sidecar || typeof sidecar !== "object" || Array.isArray(sidecar)
        || sidecar.glbSha256 !== glbSha256) {
        throw new Error("Sidecar konwencji nie odpowiada dokładnemu GLB.");
      }
      context.conventionSidecar = sidecar;
    }

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

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log("");
  console.log(`Zamykanie agenta (${signal})...`);

  if (ws) {
    ws.close();
  }

  await Promise.race([
    runPython.terminateAll(),
    new Promise((resolve) => setTimeout(resolve, 6000)),
  ]);
  process.exit(0);
}

let shuttingDown = false;
process.on("SIGINT", () => shutdown("SIGINT"));
process.on("SIGTERM", () => shutdown("SIGTERM"));

// ============================================================
// START
// ============================================================

connect();
