'use strict';

const assert = require('node:assert/strict');
const { EventEmitter } = require('node:events');
const test = require('node:test');

const { DesktopControlClient, DesktopControlRpcError, createClient } = require('../lib/client.js');

function makeFakeSpawn(handler) {
  const calls = [];
  const spawn = (command, args, options) => {
    calls.push({ command, args, options });
    const child = new EventEmitter();
    child.stdout = new EventEmitter();
    child.stderr = new EventEmitter();
    child.stdout.setEncoding = () => {};
    child.stderr.setEncoding = () => {};
    child.stdin = {
      write(line, encoding, callback) {
        callback?.();
        const request = JSON.parse(line);
        const response = handler(request);
        if (response) {
          process.nextTick(() => child.stdout.emit('data', `${JSON.stringify(response)}\n`));
        }
      },
    };
    child.kill = () => process.nextTick(() => child.emit('close', 0, null));
    return child;
  };
  spawn.calls = calls;
  return spawn;
}

const invocation = {
  command: 'python-test',
  args: ['-m', 'desktop_control', 'serve-stdio'],
  env: { PYTHONPATH: 'src' },
  root: process.cwd(),
};

test('DesktopControlClient sends JSON-RPC requests over one warm process', async () => {
  const seen = [];
  const spawn = makeFakeSpawn((request) => {
    seen.push(request);
    return { jsonrpc: '2.0', id: request.id, result: { ok: true, method: request.method, params: request.params } };
  });
  const client = new DesktopControlClient({ invocation, spawn });

  const first = await client.observe({ query: 'notepad' });
  const second = await client.agentRun({ query: 'notepad', actions: [{ type: 'screenshot' }] });
  client.close();

  assert.equal(spawn.calls.length, 1);
  assert.equal(first.method, 'observe');
  assert.equal(second.method, 'agent_run');
  assert.deepEqual(seen.map((request) => request.id), [1, 2]);
  assert.deepEqual(spawn.calls[0].args, ['-m', 'desktop_control', 'serve-stdio']);
});

test('DesktopControlClient maps RPC errors to DesktopControlRpcError', async () => {
  const spawn = makeFakeSpawn((request) => ({
    jsonrpc: '2.0',
    id: request.id,
    error: {
      code: -32000,
      message: 'No window matched',
      data: { desktop_code: 'window_not_found' },
    },
  }));
  const client = createClient({ invocation, spawn });

  await assert.rejects(
    client.listWindows({ query: 'missing' }),
    (error) => {
      assert.ok(error instanceof DesktopControlRpcError);
      assert.equal(error.code, -32000);
      assert.equal(error.data.desktop_code, 'window_not_found');
      assert.equal(error.request.method, 'list_windows');
      return true;
    },
  );
  client.close();
});

test('DesktopControlClient validates request shape before writing', async () => {
  const spawn = makeFakeSpawn(() => {
    throw new Error('unexpected write');
  });
  const client = createClient({ invocation, spawn });

  await assert.rejects(client.request('', {}), /method must be/);
  await assert.rejects(client.request('observe', []), /params must be/);
  assert.equal(spawn.calls.length, 0);
});

test('DesktopControlClient rejects pending requests on close', async () => {
  const spawn = makeFakeSpawn(() => null);
  const client = createClient({ invocation, spawn, timeoutMs: 0 });

  const pending = client.request('observe', {});
  client.close();

  await assert.rejects(pending, /closed/);
});
