'use strict';

const { EventEmitter } = require('node:events');
const { spawn } = require('node:child_process');

const { buildPythonInvocation } = require('../bin/desktop-control.js');

class DesktopControlRpcError extends Error {
  constructor(error, request) {
    super(error?.message || 'Desktop control RPC request failed');
    this.name = 'DesktopControlRpcError';
    this.code = error?.code;
    this.data = error?.data;
    this.request = request;
  }
}

class DesktopControlClient extends EventEmitter {
  constructor(options = {}) {
    super();
    this.options = { ...options };
    this.spawn = options.spawn || spawn;
    this.nextId = 1;
    this.pending = new Map();
    this.buffer = '';
    this.closed = false;
    this.child = null;
  }

  start() {
    if (this.closed) {
      throw new Error('DesktopControlClient is closed');
    }
    if (this.child) {
      return this;
    }

    const invocation = this.options.invocation || buildPythonInvocation(['serve-stdio'], this.options);
    const child = this.spawn(invocation.command, invocation.args, {
      cwd: invocation.root,
      env: invocation.env,
      stdio: ['pipe', 'pipe', 'pipe'],
      windowsHide: true,
    });
    this.child = child;

    if (child.stdout) {
      child.stdout.setEncoding?.('utf8');
      child.stdout.on('data', (chunk) => this._onStdout(chunk));
    }
    if (child.stderr) {
      child.stderr.setEncoding?.('utf8');
      child.stderr.on('data', (chunk) => this.emit('stderr', chunk));
    }
    child.on('error', (error) => this._rejectAll(error));
    child.on('close', (code, signal) => {
      this.child = null;
      const reason = signal ? `signal ${signal}` : `exit code ${code}`;
      this._rejectAll(new Error(`desktop-control serve-stdio closed with ${reason}`));
      this.emit('close', { code, signal });
    });
    return this;
  }

  request(method, params = {}, options = {}) {
    if (!method || typeof method !== 'string') {
      return Promise.reject(new TypeError('method must be a non-empty string'));
    }
    if (params == null) {
      params = {};
    }
    if (typeof params !== 'object' || Array.isArray(params)) {
      return Promise.reject(new TypeError('params must be an object'));
    }

    this.start();
    const id = this.nextId++;
    const payload = { jsonrpc: '2.0', id, method, params };
    const timeoutMs = options.timeoutMs ?? this.options.timeoutMs ?? 30000;

    return new Promise((resolve, reject) => {
      const timer = timeoutMs > 0
        ? setTimeout(() => {
          this.pending.delete(id);
          reject(new Error(`desktop-control RPC request timed out after ${timeoutMs} ms: ${method}`));
        }, timeoutMs)
        : null;
      this.pending.set(id, { resolve, reject, timer, request: payload });

      const line = `${JSON.stringify(payload)}\n`;
      this.child.stdin.write(line, 'utf8', (error) => {
        if (!error) {
          return;
        }
        const pending = this.pending.get(id);
        if (!pending) {
          return;
        }
        this.pending.delete(id);
        if (pending.timer) {
          clearTimeout(pending.timer);
        }
        reject(error);
      });
    });
  }

  close() {
    this.closed = true;
    if (this.child) {
      this.child.kill();
      this.child = null;
    }
    this._rejectAll(new Error('DesktopControlClient closed'));
  }

  listApps(params = {}, options) { return this.request('list_apps', params, options); }
  listWindows(params = {}, options) { return this.request('list_windows', params, options); }
  launchApp(params = {}, options) { return this.request('launch_app', params, options); }
  getWindow(params = {}, options) { return this.request('get_window', params, options); }
  activateWindow(params = {}, options) { return this.request('activate_window', params, options); }
  getWindowState(params = {}, options) { return this.request('get_window_state', params, options); }
  observe(params = {}, options) { return this.request('observe', params, options); }
  view(params = {}, options) { return this.request('view', params, options); }
  agentRun(params = {}, options) { return this.request('agent_run', params, options); }
  run(params = {}, options) { return this.agentRun(params, options); }
  agentStep(params = {}, options) { return this.request('agent_step', params, options); }
  act(params = {}, options) { return this.agentStep(params, options); }
  batch(actions, options = {}) {
    const params = Array.isArray(actions) ? { actions } : actions;
    return this.request('batch', params, options);
  }
  click(params = {}, options) { return this.request('click', params, options); }
  doubleClick(params = {}, options) { return this.request('double_click', params, options); }
  move(params = {}, options) { return this.request('move', params, options); }
  scroll(params = {}, options) { return this.request('scroll', params, options); }
  drag(params = {}, options) { return this.request('drag', params, options); }
  typeText(params = {}, options) { return this.request('type_text', params, options); }
  key(params = {}, options) { return this.request('key', params, options); }
  pressKey(params = {}, options) { return this.request('press_key', params, options); }
  findElements(params = {}, options) { return this.request('find_elements', params, options); }
  clickElement(params = {}, options) { return this.request('click_element', params, options); }
  invokeElement(params = {}, options) { return this.request('invoke_element', params, options); }
  setValue(params = {}, options) { return this.request('set_value', params, options); }
  wait(params = {}, options) { return this.request('wait', params, options); }
  waitWindow(params = {}, options) { return this.request('wait_window', params, options); }
  waitElement(params = {}, options) { return this.request('wait_element', params, options); }
  recoverWindow(params = {}, options) { return this.request('recover_window', params, options); }
  screenshot(params = {}, options) { return this.request('screenshot', params, options); }

  _onStdout(chunk) {
    this.buffer += String(chunk);
    while (true) {
      const newline = this.buffer.indexOf('\n');
      if (newline < 0) {
        return;
      }
      const line = this.buffer.slice(0, newline).trim();
      this.buffer = this.buffer.slice(newline + 1);
      if (!line) {
        continue;
      }
      let message;
      try {
        message = JSON.parse(line);
      } catch (error) {
        this.emit('protocolError', error, line);
        continue;
      }
      this._handleMessage(message);
    }
  }

  _handleMessage(message) {
    const pending = this.pending.get(message.id);
    if (!pending) {
      this.emit('unhandledMessage', message);
      return;
    }
    this.pending.delete(message.id);
    if (pending.timer) {
      clearTimeout(pending.timer);
    }
    if (message.error) {
      pending.reject(new DesktopControlRpcError(message.error, pending.request));
      return;
    }
    pending.resolve(message.result);
  }

  _rejectAll(error) {
    for (const [id, pending] of this.pending) {
      if (pending.timer) {
        clearTimeout(pending.timer);
      }
      pending.reject(error);
      this.pending.delete(id);
    }
  }
}

function createClient(options = {}) {
  return new DesktopControlClient(options);
}

module.exports = {
  DesktopControlClient,
  DesktopControlRpcError,
  createClient,
};
