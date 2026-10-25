import { defineConfig } from 'vite';
import { spawnSync } from 'node:child_process';
import { createReadStream, existsSync, readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

function presetAssets() {
  let assets;
  function generate() {
    if (assets) return assets;
    const localPython = fileURLToPath(new URL('../.venv/bin/python3', import.meta.url));
    const python = process.env.CREDITS_PYTHON || (existsSync(localPython) ? localPython : 'python3');
    const result = spawnSync(python, [fileURLToPath(new URL('./tools/build-presets.py', import.meta.url))], {
      encoding: 'utf8',
    });
    if (result.error || result.status !== 0) {
      throw new Error(`Preset packaging failed: ${result.error?.message || result.stderr}`);
    }
    assets = JSON.parse(result.stdout);
    return assets;
  }
  return {
    name: 'preset-assets',
    configureServer(server) {
      const { files, presets } = generate();
      server.middlewares.use((request, response, next) => {
        const pathname = new URL(request.url, 'http://localhost').pathname.slice(1);
        if (pathname === 'presets.json') {
          response.setHeader('Content-Type', 'application/json');
          response.end(JSON.stringify(presets));
        } else if (Object.hasOwn(files, pathname)) {
          response.setHeader('Content-Type', 'audio/wav');
          const stream = createReadStream(files[pathname]);
          stream.on('error', next);
          stream.pipe(response);
        } else {
          next();
        }
      });
    },
    generateBundle() {
      const { files, presets } = generate();
      this.emitFile({ type: 'asset', fileName: 'presets.json', source: JSON.stringify(presets) });
      for (const [fileName, source] of Object.entries(files)) {
        this.emitFile({ type: 'asset', fileName, source: readFileSync(source) });
      }
    },
  };
}

function creditsAssets() {
  let assets;
  function generate() {
    if (assets) return assets;
    const localPython = fileURLToPath(new URL('../.venv/bin/python3', import.meta.url));
    const python = process.env.CREDITS_PYTHON || (existsSync(localPython) ? localPython : 'python3');
    const result = spawnSync(python, [fileURLToPath(new URL('./tools/build-credits.py', import.meta.url))], {
      encoding: 'utf8',
      maxBuffer: 4 * 1024 * 1024,
    });
    if (result.error || result.status !== 0) {
      throw new Error(`Credits precompilation failed: ${result.error?.message || result.stderr}`);
    }
    JSON.parse(result.stdout);
    assets = result.stdout;
    return assets;
  }
  return {
    name: 'credits-assets',
    configureServer(server) {
      generate();
      server.middlewares.use('/credits-assets.json', (request, response) => {
        response.setHeader('Content-Type', 'application/json');
        response.end(generate());
      });
    },
    generateBundle() {
      this.emitFile({ type: 'asset', fileName: 'credits-assets.json', source: generate() });
    },
  };
}

export default defineConfig(({ mode }) => ({
  define: {
    'import.meta.env.VITE_DESKTOP': JSON.stringify(mode === 'desktop'),
  },
  publicDir: mode === 'desktop' ? 'desktop/runtime' : 'public',
  plugins: [creditsAssets(), presetAssets()],
  server: {
    port: 5173,
    open: true,
  },
  build: {
    outDir: mode === 'desktop' ? 'dist-desktop' : 'dist',
    minify: 'terser',
  },
}));
