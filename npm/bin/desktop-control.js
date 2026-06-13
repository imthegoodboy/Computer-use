#!/usr/bin/env node
'use strict';

const fs = require('node:fs');
const path = require('node:path');
const { spawn, spawnSync } = require('node:child_process');

const DOCTOR_FLAG = '--npm-wrapper-doctor';

function parseArgWords(value) {
  if (!value) {
    return [];
  }

  const words = [];
  let current = '';
  let quote = null;
  let escaping = false;

  for (const char of value) {
    if (escaping) {
      current += char;
      escaping = false;
      continue;
    }
    if (char === '\\') {
      escaping = true;
      continue;
    }
    if (quote) {
      if (char === quote) {
        quote = null;
      } else {
        current += char;
      }
      continue;
    }
    if (char === '"' || char === "'") {
      quote = char;
      continue;
    }
    if (/\s/.test(char)) {
      if (current.length > 0) {
        words.push(current);
        current = '';
      }
      continue;
    }
    current += char;
  }

  if (escaping) {
    current += '\\';
  }
  if (current.length > 0) {
    words.push(current);
  }
  return words;
}

function splitPathList(value) {
  if (!value) {
    return [];
  }
  return value.split(path.delimiter).map((item) => item.trim()).filter(Boolean);
}

function hasDesktopControlModule(root) {
  return fs.existsSync(path.join(root, 'src', 'desktop_control', '__main__.py'));
}

function findPackageRoot(startDir = __dirname, env = process.env) {
  if (env.DESKTOP_CONTROL_PACKAGE_ROOT) {
    const override = path.resolve(env.DESKTOP_CONTROL_PACKAGE_ROOT);
    if (!hasDesktopControlModule(override)) {
      throw new Error(`DESKTOP_CONTROL_PACKAGE_ROOT does not contain src/desktop_control: ${override}`);
    }
    return override;
  }

  let current = path.resolve(startDir);
  while (true) {
    if (hasDesktopControlModule(current) && fs.existsSync(path.join(current, 'pyproject.toml'))) {
      return current;
    }
    const parent = path.dirname(current);
    if (parent === current) {
      throw new Error(`Could not locate desktop-control package root from ${startDir}`);
    }
    current = parent;
  }
}

function pythonCandidates(env = process.env, platform = process.platform) {
  const extraArgs = parseArgWords(env.DESKTOP_CONTROL_PYTHON_ARGS);
  if (env.DESKTOP_CONTROL_PYTHON) {
    return [{ command: env.DESKTOP_CONTROL_PYTHON, args: extraArgs, source: 'DESKTOP_CONTROL_PYTHON' }];
  }

  if (platform === 'win32') {
    return [
      { command: 'python', args: [], source: 'PATH' },
      { command: 'py', args: ['-3'], source: 'Windows py launcher' },
      { command: 'python3', args: [], source: 'PATH' },
    ];
  }

  return [
    { command: 'python3', args: [], source: 'PATH' },
    { command: 'python', args: [], source: 'PATH' },
  ];
}

function selectPython(env = process.env, platform = process.platform) {
  const candidates = pythonCandidates(env, platform);
  for (const candidate of candidates) {
    const result = spawnSync(candidate.command, [...candidate.args, '--version'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    });
    if (!result.error && result.status === 0) {
      return {
        ...candidate,
        version: `${result.stdout || result.stderr}`.trim(),
      };
    }
  }
  return candidates[0];
}

function mergePythonPath(root, env = process.env) {
  const srcPath = path.join(root, 'src');
  const extra = splitPathList(env.DESKTOP_CONTROL_PYTHONPATH_EXTRA);
  const existing = splitPathList(env.PYTHONPATH);
  const mode = (env.DESKTOP_CONTROL_PYTHONPATH_MODE || 'prepend').toLowerCase();

  if (mode === 'preserve') {
    return existing.join(path.delimiter);
  }
  if (mode === 'replace') {
    return [srcPath, ...extra].join(path.delimiter);
  }
  if (mode === 'append') {
    return [...existing, srcPath, ...extra].join(path.delimiter);
  }
  return [srcPath, ...extra, ...existing].join(path.delimiter);
}

function buildEnv(root, env = process.env) {
  return {
    ...env,
    PYTHONPATH: mergePythonPath(root, env),
    DESKTOP_CONTROL_NPM_WRAPPER: '1',
  };
}

function buildPythonInvocation(argv, options = {}) {
  const env = options.env || process.env;
  const root = options.root || findPackageRoot(options.startDir || __dirname, env);
  const python = options.python || selectPython(env, options.platform || process.platform);
  return {
    root,
    env: buildEnv(root, env),
    command: python.command,
    args: [...python.args, '-m', 'desktop_control', ...argv],
    python,
  };
}

function runDoctor(env = process.env) {
  const root = findPackageRoot(__dirname, env);
  const python = selectPython(env, process.platform);
  const wrapperEnv = buildEnv(root, env);
  const versionCheck = spawnSync(python.command, [...python.args, '--version'], {
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', 'pipe'],
    windowsHide: true,
  });
  const importCheck = spawnSync(
    python.command,
    [...python.args, '-c', 'from desktop_control import __version__; from desktop_control.cli import build_parser; build_parser(); print(__version__)'],
    {
      encoding: 'utf8',
      env: wrapperEnv,
      stdio: ['ignore', 'pipe', 'pipe'],
      windowsHide: true,
    },
  );

  return {
    ok: !versionCheck.error && versionCheck.status === 0 && importCheck.status === 0,
    package_root: root,
    module_path: path.join(root, 'src', 'desktop_control'),
    python: {
      command: python.command,
      args: python.args,
      source: python.source,
      version: `${versionCheck.stdout || versionCheck.stderr}`.trim(),
      error: versionCheck.error ? versionCheck.error.message : null,
    },
    pythonpath: wrapperEnv.PYTHONPATH,
    desktop_control_version: importCheck.status === 0 ? importCheck.stdout.trim() : null,
    import_error: importCheck.status === 0 ? null : `${importCheck.stderr || importCheck.stdout}`.trim(),
  };
}

function run(argv = process.argv.slice(2), options = {}) {
  const stdout = options.stdout || process.stdout;
  const stderr = options.stderr || process.stderr;

  try {
    if (argv.includes(DOCTOR_FLAG)) {
      stdout.write(`${JSON.stringify(runDoctor(options.env || process.env), null, 2)}\n`);
      return Promise.resolve(0);
    }

    const invocation = buildPythonInvocation(argv, options);
    return new Promise((resolve) => {
      const child = spawn(invocation.command, invocation.args, {
        env: invocation.env,
        stdio: 'inherit',
        windowsHide: false,
      });

      child.on('error', (error) => {
        stderr.write(`desktop-control: failed to launch Python: ${error.message}\n`);
        stderr.write('Set DESKTOP_CONTROL_PYTHON to a Python executable or run desktop-control --npm-wrapper-doctor.\n');
        resolve(127);
      });
      child.on('close', (code, signal) => {
        if (signal) {
          stderr.write(`desktop-control: Python exited from signal ${signal}\n`);
          resolve(1);
          return;
        }
        resolve(code === null ? 1 : code);
      });
    });
  } catch (error) {
    stderr.write(`desktop-control: ${error.message}\n`);
    return Promise.resolve(1);
  }
}

if (require.main === module) {
  run().then((code) => {
    process.exitCode = code;
  });
}

module.exports = {
  DOCTOR_FLAG,
  buildEnv,
  buildPythonInvocation,
  findPackageRoot,
  mergePythonPath,
  parseArgWords,
  pythonCandidates,
  runDoctor,
  selectPython,
  splitPathList,
};
