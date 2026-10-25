# REharmonized Web

Browser-based tool for applying REharmonized presets or custom music to a **Castlevania: Harmony of Dissonance** Game Boy Advance ROM. Audio processing and ROM modification run locally in the browser; the ROM and custom WAV files are not uploaded to a server.

## Features

- Validates European (`ACHP`) and US (`ACHE`) ROMs.
- Keep or customize each of 31 tracks. REharmonized presets are disabled on the hosted web version and enabled in the desktop build.
- Upload custom WAV files, set tempo and volume, and request tempo suggestions.
- Download the patched ROM, with a `-custom` version suffix on its credits screen.

## Requirements

- Node.js 24.12 or newer and npm.
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

## macOS Desktop App

The Electron build reuses the web interface and original Python scripts. It includes the selected preset WAVs, Pyodide 0.24.0, its Python standard library, and Pillow. ROM injection and tempo analysis work offline; end users do not need Python, Node.js, or the build tools installed. Analytics is not initialized in the desktop build, and HTTP(S) requests from the application are blocked. Footer links open in the external browser only when clicked.

Generated ROMs are saved to the user's Downloads folder as `<original-name>-custom-REharmonized.gba`. Existing files are preserved by adding a numbered suffix, such as ` (1)`, before `.gba`.

Build on macOS from this directory:

```sh
npm ci
npm run desktop:mac
```

The first build downloads Electron and the offline Pyodide assets. Later builds reuse the local cache. The build-time Python, Pillow, ARM binutils, and Menlo requirements above still apply when generating credits assets.

The application's release version and installer filenames are read from `VERSION` in `../scripts/add_credits_screen.py` via the generated credits assets, not from the npm package version. Update that Python constant and rebuild to release a new version. The ROM credits retain their `-custom` suffix; the application version does not include that suffix.

Outputs are in `app/`: a `.app` under `mac-arm64/` on Apple Silicon (or `mac/` on Intel), plus a DMG installer and ZIP archive. The application icon is generated from `favicon.ico` as an ICNS file for macOS. The target architecture defaults to the build Mac's architecture; this does not generate a universal binary. `dist-desktop/` and `desktop/runtime/` are separate from the Firebase `dist/` output and are not deployed to Hosting. Intermediate runtime assets and `dist-desktop/` are ignored by Git; `app/` is not ignored. Generated installers exceed GitHub's 100 MiB regular Git file limit, so use Git LFS to commit them or distribute them through GitHub Releases instead. This setup does not configure LFS or upload artifacts.

For local development without packaging:

```sh
npm run desktop:build
npm run desktop:start
```

Run the Electron smoke test after building:

```sh
npm run desktop:test
```

It uses a synthetic ROM, selects a real bundled preset, runs Python and Pillow locally, checks the injected pause patch and credits entry point, verifies the ROM download, and rejects external HTTP(S) requests. It also checks bulk selection and the custom-mode controls. No commercial ROM is required. To test a packaged Apple Silicon app:

```sh
DESKTOP_EXECUTABLE="$PWD/app/mac-arm64/REharmonized.app/Contents/MacOS/REharmonized" npm run desktop:test
```

Builds are not Developer ID signed or notarized. macOS Gatekeeper may warn or block downloaded copies; only open builds from a trusted source using macOS's normal security approval flow. No Apple developer account is needed for local packaging. These commands do not generate or validate a Windows executable.

## Deploy to Firebase Hosting

Initialize Firebase Hosting in this directory if it is not configured yet. Set the Hosting public directory to `dist` and enable the single-page app rewrite. Then build and deploy:

```sh
npm run build -- --minify esbuild
firebase deploy --only hosting
```

## Runtime Dependencies

The app no longer downloads scripts, preset configuration, or preset audio from GitHub. The hosted web build loads Pyodide 0.24.0 and Pillow from jsDelivr, so an internet connection is required for tempo analysis and ROM injection there. The desktop build packages those dependencies locally. ROM processing remains local in both versions.