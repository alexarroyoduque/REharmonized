import { createHash } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdir, readFile, rename, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';

const version = '0.24.0';
const baseURL = `https://cdn.jsdelivr.net/pyodide/v${version}/full/`;
const directory = new URL('../desktop/runtime/pyodide/', import.meta.url);
await mkdir(directory, { recursive: true });

const localPython = fileURLToPath(new URL('../../.venv/bin/python3', import.meta.url));
const python = process.env.CREDITS_PYTHON || (existsSync(localPython) ? localPython : 'python3');
const icon = spawnSync(python, [fileURLToPath(new URL('./build-desktop-icon.py', import.meta.url))], { encoding: 'utf8' });
if (icon.error || icon.status !== 0) {
  throw new Error(`Desktop icon generation failed: ${icon.error?.message || icon.stderr}`);
}

async function download(name, checksum) {
  const destination = new URL(name, directory);
  let bytes;
  try {
    bytes = await readFile(destination);
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
  }
  const valid = (data) => data?.length > 0 && (!checksum || createHash('sha256').update(data).digest('hex') === checksum);
  if (valid(bytes)) return bytes;
  console.log(`Downloading Pyodide ${version}: ${name}`);
  const response = await fetch(new URL(name, baseURL), { signal: AbortSignal.timeout(120000) });
  if (!response.ok) throw new Error(`Could not download ${name}: HTTP ${response.status}`);
  bytes = Buffer.from(await response.arrayBuffer());
  if (!valid(bytes)) throw new Error(`Invalid Pyodide asset: ${name}`);
  const temporary = new URL(`${name}.tmp`, directory);
  await writeFile(temporary, bytes);
  await rename(temporary, destination);
  return bytes;
}

const lock = JSON.parse(await download('pyodide-lock.json'));
if (lock.info.version !== version) throw new Error('Unexpected Pyodide runtime version');
for (const name of ['pyodide.js', 'pyodide.asm.js', 'pyodide.asm.wasm', 'python_stdlib.zip']) {
  await download(name);
}
const included = new Set();
async function includePackage(name) {
  if (included.has(name)) return;
  included.add(name);
  const dependency = lock.packages[name];
  if (!dependency) throw new Error(`Unknown Pyodide package: ${name}`);
  for (const child of dependency.depends) await includePackage(child);
  await download(dependency.file_name, dependency.sha256);
}
await includePackage('pillow');
console.log('Offline Pyodide runtime and Pillow ready.');