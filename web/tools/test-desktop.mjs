import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { _electron } from 'playwright';

const root = fileURLToPath(new URL('../', import.meta.url));
const temporary = await mkdtemp(path.join(os.tmpdir(), 'reharmonized-desktop-'));
const executablePath = process.env.DESKTOP_EXECUTABLE;
const allPresets = process.env.DESKTOP_TEST_ALL_PRESETS === '1';
const application = await _electron.launch({
  args: executablePath ? [] : [root],
  executablePath,
  timeout: 60000,
});
try {
  if (executablePath) {
    const { version } = JSON.parse(await readFile(path.join(root, 'dist-desktop/credits-assets.json'), 'utf8'));
    assert.equal(await application.evaluate(({ app }) => app.getVersion()), version);
  }
  const page = await application.firstWindow();
  const externalRequests = [];
  const errors = [];
  page.on('request', (request) => {
    if (/^https?:/.test(request.url())) externalRequests.push(request.url());
  });
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error') console.error(message.text());
  });
  page.on('dialog', (dialog) => dialog.accept());
  await page.waitForFunction(() => customElements.get('app-root'));
  const { version } = JSON.parse(await readFile(path.join(root, 'dist-desktop/credits-assets.json'), 'utf8'));
  assert.equal(await page.locator('app-root').locator('header .version').textContent(), version);
  assert.equal(await page.evaluate(() => typeof window.require), 'undefined');
  const rom = Buffer.alloc(8 * 1024 * 1024);
  rom.write('ACHE', 0xAC);
  rom.writeUInt32LE(0xEA00002E, 0);
  Buffer.from('286800f043fb', 'hex').copy(rom, 0xBC458);
  await page.locator('rom-uploader input[type=file]').setInputFiles({
    name: 'synthetic.gba', mimeType: 'application/octet-stream', buffer: rom,
  });
  await page.locator('song-list').waitFor();
  assert.equal(await page.getByText('"REharmonized preset" is unavailable in web').count(), 0);
  const presets = page.locator('song-item input[value=reharmonized]');
  const presetCount = await presets.count();
  assert.ok(presetCount > 0);
  for (const preset of await presets.all()) assert.equal(await preset.isEnabled(), true);
  const bulkPreset = page.locator('song-list input[name=bulk-mode][value=reharmonized]');
  await bulkPreset.check();
  assert.equal(await page.locator('song-item input[value=reharmonized]:checked').count(), presetCount);
  await page.locator('song-list input[name=bulk-mode][value=none]').check();
  assert.equal(await page.locator('song-item input[value=none]:checked').count(), 31);
  await page.locator('song-item input[value=custom]').first().check();
  assert.equal(await page.locator('song-item input[type=file]').count(), 1);
  const wav = Buffer.alloc(44 + 11025 * 2);
  wav.write('RIFF', 0);
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write('WAVEfmt ', 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(11025, 24);
  wav.writeUInt32LE(22050, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write('data', 36);
  wav.writeUInt32LE(wav.length - 44, 40);
  for (let sample = 0; sample < 11025; sample++) {
    wav.writeInt16LE(Math.round(10000 * Math.sin(sample / 10)), 44 + sample * 2);
  }
  await page.locator('song-item input[type=file]').setInputFiles({
    name: 'synthetic.wav', mimeType: 'audio/wav', buffer: wav,
  });
  await page.locator('.suggest-btn').click();
  await page.waitForFunction((item) => item.suggestions.length > 0,
    await page.locator('song-item').first().elementHandle(), { timeout: 180000 });
  await page.locator('song-list input[name=bulk-mode][value=none]').check();
  if (allPresets) await bulkPreset.check();
  else await presets.first().check();

  const existing = path.join(temporary, 'synthetic-custom-REharmonized.gba');
  await writeFile(existing, 'existing download');
  const destination = path.join(temporary, 'synthetic-custom-REharmonized (1).gba');
  await application.evaluate(({ app, session }, directory) => {
    app.setPath('downloads', directory);
    globalThis.desktopDownload = new Promise((resolve, reject) => {
      session.defaultSession.once('will-download', (_event, item) => {
        item.once('done', (_doneEvent, state) => {
          if (state === 'completed') resolve({ filename: item.getFilename(), savePath: item.getSavePath() });
          else reject(new Error(`Download ${state}`));
        });
      });
    });
  }, temporary);
  await page.locator('.apply-button').click();
  await page.waitForFunction(() => {
    const application = document.querySelector('app-root');
    return application.injectionError || application.injectionProgress === 100;
  }, null, { timeout: 180000 });
  assert.equal(await page.evaluate(() => document.querySelector('app-root').injectionError), '');
  const download = await application.evaluate(() => globalThis.desktopDownload);
  assert.equal(download.filename, 'synthetic-custom-REharmonized.gba');
  assert.equal(download.savePath, destination);
  assert.equal(await readFile(existing, 'utf8'), 'existing download');
  assert.deepEqual((await readdir(temporary)).sort(), [path.basename(existing), path.basename(destination)].sort());
  const patched = await readFile(destination);
  assert.ok(patched.length > rom.length && patched.length <= 32 * 1024 * 1024);
  assert.notEqual(patched.readUInt32LE(0), rom.readUInt32LE(0));
  assert.equal(patched.subarray(0xBC458, 0xBC45E).toString('hex'), '0af06cfc0000');
  assert.equal(patched.subarray(0xC6D34, 0xC6D44).toString('hex'), '042c04d000b52868f5f7d2fe00bd7047');
  assert.deepEqual(errors, []);
  assert.deepEqual(externalRequests, []);
  console.log(`Desktop OK: ${presetCount} presets enabled, custom WAV tempo suggestions, offline Python/Pillow, patched ROM (${patched.length} bytes), download, no external requests.`);
} finally {
  await application.close();
  await rm(temporary, { recursive: true, force: true });
}