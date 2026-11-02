"use strict";

function pythonInputArgs(sessionDir, context) {
  const args = ["-i", sessionDir];
  if (context && context.jobType === "system_frame") {
    args.push("--require-provenance");
  }
  return args;
}

module.exports = pythonInputArgs;
