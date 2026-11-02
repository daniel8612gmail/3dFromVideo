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
    for (const [agentId, agent] of Object.entries(config.agents)) {
      if (!agent || typeof agent !== 'object' || typeof agent.token !== 'string' || !agent.token) {
        throw new Error(`Nieprawidłowe dane autoryzacji agenta ${agentId}.`);
      }
      if (agent.role === 'aggregator'
        && Object.entries(config.agents).some(([otherId, other]) =>
          otherId !== agentId && other && other.token === agent.token)) {
        throw new Error('Token agregatora musi być unikalny i różny od tokenu każdego workera.');
      }
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

function getAgentRole(agentId) {
  const config = authorizedAgents[agentId];
  if (!config) return null;
  return config.role === 'aggregator' ? 'aggregator' : 'worker';
}

function getIdleAgent() {
  for (const [agentId, agent] of agents) {
    if (agent.authenticated && agent.role === 'worker'
      && !agent.busy && agent.ws.readyState === WebSocket.OPEN) {
      return {
        agentId,
        agent,
      };
    }
  }

  return null;
}

function addAgent(agentId, ws, role = 'worker') {
  agents.set(agentId, {
    ws,
    role,
    authenticated: true,
    busy: false,
    jobId: null,
  });
}

function getAggregatorAgent() {
  for (const agent of agents.values()) {
    if (agent.authenticated && agent.role === 'aggregator'
      && agent.ws.readyState === WebSocket.OPEN) return agent;
  }
  return null;
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
  getAgentRole,
  reloadAgents,
  getIdleAgent,
  getAggregatorAgent,
  addAgent,
  getAgent,
  removeAgent,
  getAgents,
  getAuthorizedAgentCount: () => Object.keys(authorizedAgents).length,
};
