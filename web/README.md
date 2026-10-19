# REharmonized Web

Browser-based tool for applying REharmonized presets or custom music to a **Castlevania: Harmony of Dissonance** Game Boy Advance ROM. Audio processing and ROM modification run locally in the browser; the ROM and custom WAV files are not uploaded to a server.

## Features

- Validates European (`ACHP`) and US (`ACHE`) ROMs.
- Choose whether to keep, replace with a REharmonized preset, or customize each of 31 tracks.
- Upload custom WAV files, set tempo and volume, and request tempo suggestions.
- Download the patched ROM, with a `-custom` version suffix on its credits screen.

## Requirements

- Node.js and npm.
- Python 3 with Pillow for generating the credits assets.
- `arm-none-eabi-as` and `arm-none-eabi-objcopy` for assembling the credits code.
- The font configured by `scripts/add_credits_screen.py` (currently macOS Menlo).

Vite uses `python3` by default, or the repository's `.venv/bin/python3` if present. Set `CREDITS_PYTHON` to use a different interpreter.

## Develop

Run from this directory:

```sh
npm install
npm run dev
```

Vite serves the app at `http://localhost:5173`.

## Build

Run from this directory, inside the repository checkout:

```sh
npm run build -- --minify esbuild
```

The deployable site is written to `dist/`. The build bundles the Python injection scripts and generates `credits-assets.json` and `presets.json`. It packages only WAV files referenced by `../scripts/config_wav_reharmonized.txt`; shared tracks are included once, and missing files fail the build. The current preset assets total about 351 MiB. The full `music/` directory is not copied.

To test the production build locally:

```sh
npm run preview -- --host 127.0.0.1
```

## Deploy to Firebase Hosting

Initialize Firebase Hosting in this directory if it is not configured yet. Set the Hosting public directory to `dist` and enable the single-page app rewrite. Then build and deploy:

```sh
npm run build -- --minify esbuild
firebase deploy --only hosting
```

## Runtime Dependencies

The app no longer downloads scripts, preset configuration, or preset audio from GitHub. Pyodide 0.24.0 and the Pillow Python package are still loaded from jsDelivr, so an internet connection is required for tempo analysis and ROM injection. ROM processing remains in the browser.