'use strict';

const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

require('dotenv').config();

const DATA_DIR = path.resolve(process.env.DATA_DIR || '../public_html/data');

const PORT = Number(process.env.PORT || 8443);
const AGENTS_FILE = path.resolve(process.env.AGENTS_FILE || './agents.json');

const HOST = '127.0.0.1';

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
  const tmpPath = `${filePath}.${process.pid}.tmp`;

  fs.writeFileSync(tmpPath, JSON.stringify(data, null, 4), 'utf8');

  fs.renameSync(tmpPath, filePath);
}

function readState(sessionId) {
  const statePath = path.join(DATA_DIR, sessionId, 'state.json');

  try {
    return readJson(statePath);
  } catch (error) {
    logError(`Nie można odczytać state.json dla ${sessionId}:`, error.message);

    return null;
  }
}

function writeState(sessionId, state) {
  const sessionDir = path.join(DATA_DIR, sessionId);
  const statePath = path.join(sessionDir, 'state.json');

  writeJsonAtomic(statePath, state);
}

function isValidSessionId(sessionId) {
  return typeof sessionId === 'string' && /^[a-f0-9]{32}$/.test(sessionId);
}

function isValidPhotoFilename(filename) {
  return typeof filename === 'string' && /^photo\.(jpg|jpeg|png|webp)$/i.test(filename);
}

function isValidProgress(value) {
  return Number.isInteger(value) && value >= 0 && value <= 100;
}

function safeTokenCompare(received, expected) {
  if (typeof received !== 'string' || typeof expected !== 'string') {
    return false;
  }

  const receivedBuffer = Buffer.from(received);
  const expectedBuffer = Buffer.from(expected);

  if (receivedBuffer.length !== expectedBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(receivedBuffer, expectedBuffer);
}

module.exports = {
  fs,
  path,
  crypto,

  DATA_DIR,
  PORT,
  AGENTS_FILE,
  HOST,

  log,
  logError,
  readJson,
  writeJsonAtomic,
  readState,
  writeState,
  isValidSessionId,
  isValidPhotoFilename,
  isValidProgress,
  safeTokenCompare,
};
