"use strict";

const { spawn } = require("child_process");
const activeChildren = new Set();

function runPython(context, script, args = []) {
  return new Promise((resolve, reject) => {
    context.log(`Uruchamiam ${script}`);

    const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");
    const child = spawn(python, [script, ...args], {
      cwd: __dirname,
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true,
    });
    activeChildren.add(child);

    const maxOutputBytes = 256 * 1024;
    let capturedBytes = 0;
    let truncated = false;
    let timedOut = false;
    let settled = false;
    let escalationTimer = null;
    const requestedTimeoutMs = Number(process.env.PYTHON_STEP_TIMEOUT_MS);
    const timeoutMs = Number.isFinite(requestedTimeoutMs) && requestedTimeoutMs > 0
      ? Math.min(Math.max(1000, requestedTimeoutMs), 6 * 60 * 60 * 1000)
      : 45 * 60 * 1000;
    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
      escalationTimer = setTimeout(() => child.kill("SIGKILL"), 5000);
    }, timeoutMs);

    function consume(chunk) {
      const available = Math.max(0, maxOutputBytes - capturedBytes);
      const bounded = chunk.subarray(0, available);
      capturedBytes += bounded.length;
      const text = bounded.toString("utf8").trim();
      if (text) {
        console.log(`[${script}] ${text}`);
        context.log(`[${script}] ${text}`);
      }
      if (bounded.length < chunk.length && !truncated) {
        truncated = true;
        const warning = `[${script}] output truncated after ${maxOutputBytes} bytes`;
        console.warn(warning);
        context.log(warning);
      }
      // The stream remains consumed after the cap to avoid blocking the child.
    }

    child.stdout.on("data", consume);
    child.stderr.on("data", consume);

    child.on("error", (error) => {
      if (settled) return;
      settled = true;
      activeChildren.delete(child);
      clearTimeout(timeout);
      if (escalationTimer) clearTimeout(escalationTimer);
      reject(new Error(`Nie udało się uruchomić ${script}: ${error.message}`));
    });

    child.on("close", (code, signal) => {
      if (settled) return;
      settled = true;
      activeChildren.delete(child);
      clearTimeout(timeout);
      if (escalationTimer) clearTimeout(escalationTimer);
      if (timedOut) {
        reject(new Error(`${script} przekroczył limit czasu ${timeoutMs} ms i został zatrzymany.`));
      } else if (code === 0) {
        console.log(`${script} zakończył działanie`);
        context.log(`${script} zakończył działanie`);
        resolve();
      } else {
        reject(new Error(`${script} zakończył działanie kodem ${code === null ? signal : code}`));
      }
    });
  });
}

function terminateAll() {
  const children = [...activeChildren];
  for (const child of children) child.kill("SIGTERM");
  return Promise.all(children.map((child) => new Promise((resolve) => {
    if (child.exitCode !== null || child.signalCode !== null) {
      resolve();
      return;
    }
    const timer = setTimeout(() => {
      child.kill("SIGKILL");
      resolve();
    }, 5000);
    child.once("close", () => {
      clearTimeout(timer);
      resolve();
    });
  })));
}

module.exports = runPython;
module.exports.terminateAll = terminateAll;
