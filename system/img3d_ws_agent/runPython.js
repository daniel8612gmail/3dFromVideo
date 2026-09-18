const { spawn } = require("child_process");

function runPython(context, script, args = []) {
  return new Promise((resolve, reject) => {
    context.log(`Uruchamiam ${script}`);

    const process = spawn("python3", [script, ...args], {
      cwd: __dirname,
      stdio: ["ignore", "pipe", "pipe"],
    });

    process.stdout.on("data", (chunk) => {
      const text = chunk.toString().trim();

      if (text) {
        console.log(`[${script}] ${text}`);
        context.log(`[${script}] ${text}`);
      }
    });

    process.stderr.on("data", (chunk) => {
      const text = chunk.toString().trim();

      if (text) {
        console.log(`[${script}] ${text}`);
        context.log(`[${script}] ${text}`);
      }
    });

    process.on("error", (error) => {
      reject(new Error(`Nie udało się uruchomić ${script}: ${error.message}`));
    });

    process.on("close", (code) => {
      if (code === 0) {
        console.log(`${script} zakończył działanie`);
        context.log(`${script} zakończył działanie`);
        resolve();
      } else {
        reject(new Error(`${script} zakończył działanie kodem ${code}`));
      }
    });
  });
}

module.exports = runPython;
