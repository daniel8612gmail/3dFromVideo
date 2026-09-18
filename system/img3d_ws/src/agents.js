'use strict';

const WebSocket = require('ws');

const { readJson, safeTokenCompare, AGENTS_FILE, log, logError } = require('./config');

const agents = new Map();

function loadAgents() {
  try {
    const config = readJson(AGENTS_FILE);

    if (!config || typeof config.agents !== 'object' || config.agents === null) {
      throw new Error('Nieprawidłowy format agents.json.');
    }

    return config.agents;
  } catch (error) {
    logError('Nie można załadować agents.json:', error.message);

    process.exit(1);
  }
}

let authorizedAgents = loadAgents();

function reloadAgents() {
  authorizedAgents = loadAgents();
  log('Przeładowano listę autoryzowanych agentów.');
}

function authenticateAgent(agentId, token) {
  const config = authorizedAgents[agentId];

  if (!config || typeof config.token !== 'string') {
    return false;
  }

  return safeTokenCompare(token, config.token);
}

function getIdleAgent() {
  for (const [agentId, agent] of agents) {
    if (agent.authenticated && !agent.busy && agent.ws.readyState === WebSocket.OPEN) {
      return {
        agentId,
        agent,
      };
    }
  }

  return null;
}

function addAgent(agentId, ws) {
  agents.set(agentId, {
    ws,
    authenticated: true,
    busy: false,
    jobId: null,
  });
}

function getAgent(agentId) {
  return agents.get(agentId);
}

function removeAgent(agentId) {
  agents.delete(agentId);
}

function getAgents() {
  return agents;
}

module.exports = {
  agents,
  authenticateAgent,
  reloadAgents,
  getIdleAgent,
  addAgent,
  getAgent,
  removeAgent,
  getAgents,
  getAuthorizedAgentCount: () => Object.keys(authorizedAgents).length,
};
