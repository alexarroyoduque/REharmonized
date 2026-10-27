/**
 * Harmony of Dissonance - ROM Injector (Phase 5)
 *
 * Executes modules.injection via Pyodide to inject custom songs
 * into the ROM based on user selections.
 */

import { loadPyodideRuntime } from './pyodide-wrapper.js';
import creditsPipeline from './credits-pipeline.py?raw';

let reharmonizedPresetsPromise = null;

/**
 * Load the packaged preset manifest, mapping song_id -> preset.
 * Cached after the first call.
 */
async function loadReharmonizedPresets() {
  if (!reharmonizedPresetsPromise) {
    reharmonizedPresetsPromise = (async () => {
      const resp = await fetch(
        `${import.meta.env.BASE_URL}presets.json`
      );
      if (!resp.ok) {
        throw new Error('Could not load packaged REharmonized presets');
      }
      return resp.json();
    })();
  }
  return reharmonizedPresetsPromise;
}

/**
 * Inject all selected songs into the ROM
 *
 * @param {Blob} romFile - Original ROM file
 * @param {string} romFileName - ROM filename (for naming output)
 * @param {Array} selections - Array of {song_id, mode, wav_file, tempo, volume}
 * @param {function} onProgress - Callback: (message, progress) where progress is 0-100
 * @returns {Promise<Blob>} The injected ROM file
 */
export async function injectSongsToRom(
  romFile,
  romFileName,
  selections,
  onProgress = () => {}
) {
  try {
    onProgress("[1/5] Loading Python runtime...", 10);
    console.log("[Injector] Loading Pyodide...");

    const pyodide = await loadPyodideRuntime();

    // Write ROM to filesystem
    onProgress("[2/5] Writing ROM to memory...", 25);
    const romBytes = new Uint8Array(await romFile.arrayBuffer());
    const romPath = `/tmp/harmony-${Date.now()}.gba`;
    pyodide.FS.writeFile(romPath, romBytes);
    console.log(
      `[Injector] ROM written (${(romBytes.length / 1024 / 1024).toFixed(1)} MB)`
    );

    // Write WAV files and build config
    onProgress("[3/5] Writing song files...", 35);
    const configLines = [];

    for (let i = 0; i < selections.length; i++) {
      const sel = selections[i];
      const songId = parseInt(sel.song_id, 10); // strip leading zeros (base.parse_int uses base 0 / octal)
      if (sel.mode === 'custom' && sel.wav_file) {
        const wavBytes = new Uint8Array(await sel.wav_file.arrayBuffer());
        const wavPath = `/tmp/song_${songId}_${Date.now()}.wav`;
        pyodide.FS.writeFile(wavPath, wavBytes);

        // Config line: SONG_ID WAV_PATH TEMPO [VOLUME]
        const tempo = sel.tempo === 'auto' ? 'auto' : sel.tempo;
        const volume = sel.volume || 'auto';
        configLines.push(`${songId}\t${wavPath}\t${tempo}\t${volume}`);

        console.log(
          `[Injector] Song ${songId}: ${sel.wav_file.name} (${(wavBytes.length / 1024).toFixed(1)} KB)`
        );
      } else if (sel.mode === 'reharmonized') {
        // Fetch the official preset .wav + tempo/volume for this song
        const presets = await loadReharmonizedPresets();
        const preset = presets[songId];
        if (!preset) {
          throw new Error(`No REharmonized preset available for song ${songId}`);
        }

        const wavUrl = `${import.meta.env.BASE_URL}${preset.wavPath}`;

        const wavResp = await fetch(wavUrl);
        if (!wavResp.ok) {
          throw new Error(`Could not load packaged preset .wav for song ${songId}: ${preset.wavPath}`);
        }
        const wavBytes = new Uint8Array(await wavResp.arrayBuffer());
        const wavPath = `/tmp/song_${songId}_${Date.now()}.wav`;
        pyodide.FS.writeFile(wavPath, wavBytes);

        configLines.push(`${songId}\t${wavPath}\t${preset.tempo}\t${preset.volume}\t${preset.loopStart ?? 0}\t${preset.crossfade ?? 0}`);
        console.log(
          `[Injector] Song ${songId}: REharmonized preset (${preset.wavPath}, tempo ${preset.tempo})`
        );
      }
    }

    if (configLines.length === 0) {
      throw new Error('No songs selected for injection');
    }

    const configContent = configLines.join('\n');
    const configPath = `/tmp/config_${Date.now()}.txt`;
    pyodide.FS.writeFile(configPath, new TextEncoder().encode(configContent));

    console.log(
      `[Injector] Config written with ${configLines.length} songs`
    );

    // Fetch injection scripts and dependencies
    onProgress("[4/5] Fetching injection scripts...", 50);

    const creditsScriptUrl = `${import.meta.env.BASE_URL}credits-assets.json`;

    const creditsScriptResp = await fetch(creditsScriptUrl);

    if (!creditsScriptResp.ok) {
      throw new Error('Could not load packaged credits assets');
    }

    const creditsAssets = await creditsScriptResp.json();

    onProgress("[5/5] Loading credits dependencies...", 65);
    await pyodide.loadPackage('pillow');

    // Execute injection + credits screen
    onProgress("[5/5] Processing songs and credits...", 70);

    const injectedPath = `/tmp/harmony-injected-${Date.now()}.gba`;
    const outputPath = `/tmp/harmony-final-${Date.now()}.gba`;

    pyodide.globals.set('credits_job_json', JSON.stringify({
      assets: creditsAssets,
      romPath,
      configPath,
      injectedPath,
      outputPath,
    }));
    await pyodide.runPythonAsync(creditsPipeline);
    console.log(`[Injector] Injection and credits screen completed`);

    // Verify output ROM was created
    if (!pyodide.FS.analyzePath(outputPath).exists) {
      throw new Error('Final ROM was not created by injection pipeline');
    }

    // Read output ROM
    onProgress("[Done] Reading injected ROM...", 90);

    const injectedRomBytes = pyodide.FS.readFile(outputPath);
    const injectedRomBlob = new Blob([injectedRomBytes], {
      type: 'application/octet-stream',
    });

    onProgress("✓ ROM injection complete!", 100);

    return injectedRomBlob;
  } catch (error) {
    console.error('[Injector] Error:', error);
    throw new Error(`ROM injection failed: ${error.message}`);
  }
}

/**
 * Trigger browser download of the injected ROM
 *
 * @param {Blob} romBlob - The injected ROM blob
 * @param {string} originalName - Original ROM filename (used to generate output name)
 */
export function downloadRom(romBlob, originalName) {
  const name = originalName.replace(/\.gba$/i, '');
  const outputName = `${name}-custom-REharmonized.gba`;

  const url = URL.createObjectURL(romBlob);
  const link = document.createElement('a');
  link.href = url;
  link.download = outputName;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);

  console.log(`[Injector] Downloaded: ${outputName}`);
}
