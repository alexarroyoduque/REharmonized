/**
 * Harmony of Dissonance - Tempo Suggestion (via Pyodide)
 *
 * Executes the shared Python tempo logic directly in the browser
 * using Pyodide (CPython 3.11 compiled to WebAssembly).
 *
 * No code duplication - the implementation lives in scripts/modules.
 */

import { installPythonModules } from './python-modules.js';

let pyodideInstance = null;
let pyodideLoading = false;
const pyodideURL = import.meta.env.VITE_DESKTOP
  ? new URL(`${import.meta.env.BASE_URL}pyodide/`, window.location.href).href
  : 'https://cdn.jsdelivr.net/pyodide/v0.24.0/full/';

/**
 * Load Pyodide (happens once per session, cached thereafter)
 */
export async function loadPyodideRuntime() {
  if (pyodideInstance) return pyodideInstance;
  if (pyodideLoading) {
    // Wait for ongoing load
    while (pyodideLoading) {
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    return pyodideInstance;
  }

  pyodideLoading = true;

  try {
    console.log("[Pyodide] Loading Python runtime (~50MB, cached)...");

    // Load Pyodide as a global script
    const script = document.createElement("script");
    script.src = `${pyodideURL}pyodide.js`;
    await new Promise((resolve, reject) => {
      script.onload = resolve;
      script.onerror = reject;
      document.head.appendChild(script);
    });

    // Now loadPyodide should be available globally
    if (typeof window.loadPyodide !== "function") {
      throw new Error("Pyodide failed to load (loadPyodide not found)");
    }

    pyodideInstance = await window.loadPyodide({
      indexURL: pyodideURL,
    });

    installPythonModules(pyodideInstance);
    await pyodideInstance.runPythonAsync("import sys\nif '/tmp' not in sys.path: sys.path.insert(0, '/tmp')");

    console.log("[Pyodide] Runtime loaded");
    return pyodideInstance;
  } catch (error) {
    pyodideLoading = false;
    throw error;
  } finally {
    pyodideLoading = false;
  }
}

/**
 * Main function: process a WAV file and return tempo suggestions
 * using the shared Python modules (no code duplication).
 *
 * @param {File | Blob} wavFile - The WAV file
 * @param {string} songId - Song ID (e.g., "01")
 * @returns {Promise<{song_id, duration_s, best, suggestions}>}
 */
export async function processWavForTempos(wavFile, songId = "01") {
  try {
    console.log(`[Pyodide] Processing Song ${songId}...`);

    // Initialize Pyodide on first use
    const pyodide = await loadPyodideRuntime();

    // Read WAV file into bytes
    const arrayBuffer = await wavFile.arrayBuffer();
    const wavBytes = new Uint8Array(arrayBuffer);

    // Write WAV to Pyodide's virtual filesystem
    const wavPath = `/tmp/${wavFile.name}`;
    pyodide.FS.writeFile(wavPath, wavBytes);

    console.log(
      `[Pyodide] WAV written (${(wavBytes.length / 1024).toFixed(1)} KB)`
    );

    const pythonCode = `
import json
import sys
from pathlib import Path
from modules import base

# Read WAV using the original function
wav_path = Path('${wavPath}')
mono, src_rate = base.read_wav_mono_float(wav_path)

# Resample using the original function
resampled = base.resample_linear(mono, src_rate, base.DEFAULT_SAMPLE_RATE)
if not resampled:
    raise RuntimeError('WAV contains no audio data')

# Calculate duration and tempos using the original functions
duration_s = len(resampled) / base.DEFAULT_SAMPLE_RATE
tempo, holds, hold_s = base.pick_tempo_and_holds(duration_s, None)
suggestions = base.suggest_tempos(duration_s, base.DEFAULT_SUGGEST_GAPS)

result = json.dumps({
    'song_id': '${songId}',
    'wav_path': '${wavFile.name}',
    'source_sample_rate': src_rate,
    'resampled_rate': base.DEFAULT_SAMPLE_RATE,
    'duration_s': round(duration_s, 6),
    'best': {
        'tempo': tempo,
        'holds': holds,
        'hold_s': round(hold_s, 6),
        'gap_s': round(hold_s - duration_s, 6),
    },
    'suggestions': [
        {
            'target_gap_s': t[0],
            'tempo': t[1],
            'holds': t[2],
            'actual_s': round(t[3], 6),
            'gap_s': round(t[4], 6),
        }
        for t in suggestions
    ]
})
`;

    console.log(`[Pyodide] Executing tempo calculation...`);

    // Run the Python code
    await pyodide.runPythonAsync(pythonCode);
    
    // Capture the result variable that was created by the Python code
    const resultJson = pyodide.globals.get('result');
    const result = JSON.parse(resultJson);

    console.log(
      `[Pyodide] ✓ Song ${songId}: ${result.duration_s.toFixed(2)}s → ${result.suggestions.length} suggestions`
    );

    return result;
  } catch (error) {
    console.error(`[Pyodide] Error:`, error);
    throw new Error(`Tempo calculation failed: ${error.message}`);
  }
}
