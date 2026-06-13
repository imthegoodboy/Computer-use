'use strict';

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const wrapper = require('../bin/desktop-control.js');

const repoRoot = path.resolve(__dirname, '..', '..');

test('findPackageRoot resolves from the npm bin directory', () => {
  assert.equal(wrapper.findPackageRoot(path.join(repoRoot, 'npm', 'bin')), repoRoot);
});

test('buildPythonInvocation passes arguments through without shell parsing', () => {
  const invocation = wrapper.buildPythonInvocation(['list-windows', '--query', 'hello world'], {
    root: repoRoot,
    env: {
      DESKTOP_CONTROL_PYTHON: 'python-custom',
      DESKTOP_CONTROL_PYTHON_ARGS: '-X utf8',
    },
    python: { command: 'python-custom', args: ['-X', 'utf8'], source: 'test' },
  });

  assert.equal(invocation.command, 'python-custom');
  assert.deepEqual(invocation.args, ['-X', 'utf8', '-m', 'desktop_control', 'list-windows', '--query', 'hello world']);
});

test('buildEnv prepends the local src directory to PYTHONPATH by default', () => {
  const env = wrapper.buildEnv(repoRoot, { PYTHONPATH: 'existing' });
  assert.equal(env.DESKTOP_CONTROL_NPM_WRAPPER, '1');
  assert.equal(env.PYTHONPATH, [path.join(repoRoot, 'src'), 'existing'].join(path.delimiter));
});

test('mergePythonPath supports append, replace, and preserve modes', () => {
  assert.equal(
    wrapper.mergePythonPath(repoRoot, { PYTHONPATH: 'existing', DESKTOP_CONTROL_PYTHONPATH_MODE: 'append' }),
    ['existing', path.join(repoRoot, 'src')].join(path.delimiter),
  );
  assert.equal(
    wrapper.mergePythonPath(repoRoot, { PYTHONPATH: 'existing', DESKTOP_CONTROL_PYTHONPATH_MODE: 'replace' }),
    path.join(repoRoot, 'src'),
  );
  assert.equal(
    wrapper.mergePythonPath(repoRoot, { PYTHONPATH: 'existing', DESKTOP_CONTROL_PYTHONPATH_MODE: 'preserve' }),
    'existing',
  );
});

test('splitPathList keeps paths with spaces intact', () => {
  const first = path.join('C:', 'Program Files', 'desktop-control');
  const second = path.join('D:', 'deps');
  assert.deepEqual(wrapper.splitPathList([first, second].join(path.delimiter)), [first, second]);
});

test('package bin aliases point at the same executable', () => {
  const packageJson = JSON.parse(fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'));
  assert.equal(packageJson.bin['desktop-control'], './npm/bin/desktop-control.js');
  assert.equal(packageJson.bin['desktop-control-tool'], './npm/bin/desktop-control.js');
});
