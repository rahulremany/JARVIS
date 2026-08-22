#!/usr/bin/env node
// src/mcp/server.ts
//
// Tier-3 agentic layer: exposes the same actions DeviceActions/ToolExecutor
// already run for tier-2 fast commands, but through the Model Context
// Protocol so a reasoning model (a mesh facet, or Claude, or any other MCP
// client) can chain several of them together with judgment in between --
// "get the enclosure ready, slice it, queue the print" -- instead of only
// ever executing one matched command at a time.
//
// Run: tsx src/mcp/server.ts   (stdio transport; point an MCP client at it)
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { z } from 'zod';
import { ToolExecutor } from '../tools/ToolExecutor.js';
import { DeviceActions } from '../tools/DeviceActions.js';
import { logger } from '../utils/logging.js';

const toolExecutor = new ToolExecutor();
const deviceActions = new DeviceActions();

const server = new McpServer({
  name: 'jarvis-workshop-tools',
  version: '0.1.0'
});

server.registerTool(
  'open_app',
  {
    description: 'Open a named application on the local machine',
    inputSchema: { name: z.string().describe('Application name, e.g. "VS Code" or "Terminal"') }
  },
  async ({ name }) => {
    const result = await toolExecutor.execute({ action: 'open_app', params: { name } });
    return { content: [{ type: 'text', text: result.output }] };
  }
);

server.registerTool(
  'run_shell',
  {
    description: 'Run a whitelisted, read-only shell command (ls, pwd, ps, df, ...)',
    inputSchema: { command: z.string() }
  },
  async ({ command }) => {
    const result = await toolExecutor.execute({ action: 'run_shell', params: { command } });
    return { content: [{ type: 'text', text: result.output }], isError: !result.success };
  }
);

server.registerTool(
  'device_command',
  {
    description:
      'Execute a smart-home/workshop device action (lights, thermostat, security). ' +
      'Placeholder handlers today -- this is the hook real equipment control ' +
      '(printer, CNC, laser) will register into once the physical safety ' +
      'interlocks in front of it are built.',
    inputSchema: {
      type: z.enum(['lights', 'thermostat', 'music', 'security', 'general']),
      action: z.string(),
      parameters: z.record(z.string(), z.any()).optional()
    }
  },
  async ({ type, action, parameters }) => {
    const output = await deviceActions.executeCommand({ type, action, parameters });
    return { content: [{ type: 'text', text: output }] };
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  logger.info('MCP tool server listening on stdio (jarvis-workshop-tools)');
}

main().catch(error => {
  logger.error('MCP server failed to start:', error);
  process.exit(1);
});
