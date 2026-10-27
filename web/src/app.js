import { LitElement, html, css, unsafeCSS } from 'lit';
if (!import.meta.env.VITE_DESKTOP) import('./firebase.js');
import './components/rom-uploader.js';
import './components/song-list.js';
import { injectSongsToRom, downloadRom } from './utils/rom-injector.js';
import headerArtwork from '../../images/REharmonized_Juste.jpg';

class AppRoot extends LitElement {
  static properties = {
    romLoaded: { type: Boolean },
    romFileName: { type: String },
    romFile: { type: Object },
    injectionInProgress: { type: Boolean },
    injectionProgress: { type: Number }, // 0-100
    injectionMessage: { type: String },
    injectionError: { type: String },
  };

  static styles = css`
    * {
      margin: 0;
      padding: 0;
      box-sizing: border-box;
    }

    :host {
      display: flex;
      flex-direction: column;
      background-color: var(--bg-primary);
      background-image: repeating-linear-gradient(
        135deg,
        var(--pattern-color) 0,
        var(--pattern-color) 1px,
        var(--transparent) 1px,
        var(--transparent) 7px
      );
      color: var(--text-primary);
      font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
      min-height: 100vh;
    }

    header {
      background-color: var(--bg-secondary);
      background-image: linear-gradient(90deg, var(--header-overlay-light), var(--header-overlay-dark)), url(${unsafeCSS(headerArtwork)});
      background-position: center 15%;
      background-size: cover;
      background-repeat: no-repeat;
      border-bottom: 3px solid var(--accent);
      min-height: 230px;
      padding: 3.5rem 2rem;
      text-align: center;
    }

    header h1 {
      font-size: 2.5rem;
      font-weight: bold;
      color: var(--text-highlight);
      text-shadow: 0 2px 4px var(--bg-primary), 0 0 22px var(--glow-accent-text);
      margin-bottom: 0.5rem;
    }
    header .version {
      font-size: 1.8rem;
    }

    header p {
      color: var(--text-primary);
      text-shadow: 0 1px 4px var(--bg-primary);
      font-size: 1rem;
    }

    main {
      flex: 1;
      width: 100%;
      max-width: 1200px;
      margin: 0 auto;
      padding: 2rem;
    }

    .site-footer {
      display: flex;
      align-items: center;
      justify-content: center;
      flex-wrap: wrap;
      gap: 0.5rem 1.25rem;
      padding: 1.1rem 1.5rem;
      border-top: 1px solid var(--accent-dark);
      background: var(--footer-surface);
      color: var(--text-secondary);
      font-size: 0.9rem;
      text-align: center;
    }

    .site-footer a {
      color: var(--accent-light);
    }

    .site-footer a:hover,
    .site-footer a:focus-visible {
      color: var(--text-highlight);
      text-decoration: underline;
    }

    .section {
      background-color: var(--bg-secondary);
      border: 1px solid var(--accent-dark);
      padding: 1.5rem;
      margin-bottom: 2rem;
      border-radius: 4px;
      animation: slideUp 0.3s ease;
    }

    .section h2 {
      color: var(--accent);
      margin-bottom: 1rem;
      font-size: 1.5rem;
    }

    .status-message {
      color: var(--accent);
      font-size: 1.1rem;
      margin-bottom: 1rem;
      padding: 1rem;
      background-color: var(--status-accent-strong);
      border-left: 4px solid var(--accent);
      border-radius: 4px;
    }

    .error-message {
      color: var(--error-text);
      background-color: var(--error-surface);
      border-left: 4px solid var(--error-border);
      padding: 1rem;
      margin-top: 1rem;
      overflow-wrap: anywhere;
    }

    .apply-button {
      background-color: var(--accent);
      color: var(--bg-primary);
      border: none;
      padding: 1rem 2rem;
      border-radius: 4px;
      font-weight: 600;
      font-size: 1rem;
      cursor: pointer;
      transition: all 0.3s ease;
      margin-top: 1.5rem;
      width: 100%;
    }

    .apply-button:hover:not(:disabled) {
      background-color: var(--accent-light);
      box-shadow: 0 0 20px var(--glow-accent-intense);
      transform: scale(1.02);
    }

    .apply-button:disabled {
      background-color: var(--text-secondary);
      cursor: not-allowed;
      opacity: 0.5;
    }

    .progress-dialog {
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background-color: var(--overlay);
      display: flex;
      align-items: center;
      justify-content: center;
      z-index: 1000;
    }

    .progress-content {
      background-color: var(--bg-secondary);
      border: 2px solid var(--accent);
      padding: 2rem;
      border-radius: 8px;
      max-width: 400px;
      text-align: center;
      box-shadow: 0 0 30px var(--glow-accent-medium);
    }

    .progress-content h3 {
      color: var(--accent);
      margin-bottom: 1rem;
    }

    .progress-bar {
      background-color: var(--bg-primary);
      border: 1px solid var(--accent-dark);
      border-radius: 4px;
      height: 30px;
      overflow: hidden;
      margin-bottom: 1rem;
    }

    .progress-fill {
      background: linear-gradient(90deg, var(--accent-dark), var(--accent-light));
      height: 100%;
      width: 0%;
      transition: width 0.3s ease;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--bg-primary);
      font-weight: bold;
      font-size: 0.9rem;
    }

    .progress-message {
      color: var(--text-secondary);
      font-size: 0.95rem;
      margin-top: 1rem;
      min-height: 2.5rem;
    }

    @media (max-width: 600px) {
      header {
        background-position: center, center top;
        background-size: cover, auto 700px;
        padding: 3.5rem 1rem;
      }

      main {
        padding: 1rem;
      }

      .section {
        padding: 1rem;
      }
    }

    @keyframes slideUp {
      from {
        opacity: 0;
        transform: translateY(20px);
      }
      to {
        opacity: 1;
        transform: translateY(0);
      }
    }
  `;

  constructor() {
    super();
    this.romLoaded = false;
    this.romFileName = '';
    this.romFile = null;
    this.injectionInProgress = false;
    this.injectionProgress = 0;
    this.injectionMessage = '';
    this.injectionError = '';
  }

  connectedCallback() {
    super.connectedCallback();
    this.addEventListener('rom-loaded', this._handleRomLoaded);
  }

  disconnectedCallback() {
    super.disconnectedCallback();
    this.removeEventListener('rom-loaded', this._handleRomLoaded);
  }

  render() {
    return html`
      <header>
        <h1>REharmonized <span class="version">${import.meta.env.VITE_APP_VERSION}</span></h1>
        <p>Inject custom songs into Castlevania: Harmony of Dissonance</p>
      </header>

      <main>
        <section class="section">
          ${!this.romLoaded
            ? html`<rom-uploader></rom-uploader>`
            : html`
                <div class="status-message">
                  ✓ ROM loaded successfully: <strong>${this.romFileName}</strong><br />
                </div>
                <song-list .romFile=${this.romFile}></song-list>

                ${this.injectionError
                  ? html`<div class="error-message" role="alert" tabindex="-1">${this.injectionError}</div>`
                  : ''}

                <button class="apply-button" @click=${this._applyREharmonized} ?disabled=${this.injectionInProgress}>
                  ${this.injectionInProgress
                    ? html`Injecting...`
                    : html`APPLY REHARMONIZED`}
                </button>
              `}
        </section>
      </main>

      <footer class="site-footer">
        <span>Developed by AlexArroyoDuque</span>
        <a href="https://www.romhacking.net/hacks/9975" target="_blank" rel="noopener noreferrer">Patch</a>
        <a href="https://github.com/alexarroyoduque/REharmonized" target="_blank" rel="noopener noreferrer">GitHub</a>
        <a href="https://www.patreon.com/cw/AlexArroyoDuque" target="_blank" rel="noopener noreferrer">Patreon</a>
      </footer>

      ${this.injectionInProgress
        ? html`
            <div class="progress-dialog">
              <div class="progress-content">
                <h3>Injecting Songs...</h3>
                <div class="progress-bar">
                  <div class="progress-fill" style="width: ${this.injectionProgress}%">
                    ${this.injectionProgress}%
                  </div>
                </div>
                <div class="progress-message">${this.injectionMessage}</div>
              </div>
            </div>
          `
        : ''}
    `;
  }

  _applyREharmonized = async () => {
    this.injectionError = '';
    try {
      this.injectionInProgress = true;
      this.injectionProgress = 0;

      // Get song-list component and collect selections
      const songList = this.shadowRoot.querySelector('song-list');
      if (!songList) {
        throw new Error('Song list not found');
      }

      const selections = songList.getSelections();

      // Check if any songs are selected
      const selectedSongs = selections.filter(
        (s) => s.mode === 'custom' && s.wav_file || s.mode === 'reharmonized'
      );
      if (selectedSongs.length === 0) {
        throw new Error('Please select at least one song to inject');
      }

      this.injectionMessage = 'Preparing...';

      // Execute injection with progress callback
      const injectedRom = await injectSongsToRom(
        this.romFile,
        this.romFileName,
        selections,
        (message, progress) => {
          this.injectionMessage = message;
          this.injectionProgress = progress;
        }
      );

      // Download the result
      downloadRom(injectedRom, this.romFileName);

      this.injectionInProgress = false;
      alert(
        `✓ REharmonized ROM created successfully!\n\nDownloading: ${this.romFileName.replace(/\.gba$/i, '')}-custom-REharmonized.gba`
      );
    } catch (error) {
      console.error('[App] Injection error:', error);
      this.injectionError = this._getInjectionErrorMessage(error);
      this.injectionInProgress = false;
      this.injectionProgress = 0;
      this.injectionMessage = '';
      await this.updateComplete;
      this.shadowRoot.querySelector('.error-message')?.focus();
    }
  };

  _getInjectionErrorMessage(error) {
    const message = String(error?.message || error);
    const sizeMatch = message.match(/Output ROM would exceed (\d+) bytes \((\d+) bytes\)/);
    if (sizeMatch) {
      const limit = Number(sizeMatch[1]) / (1024 * 1024);
      const size = Number(sizeMatch[2]) / (1024 * 1024);
      const excess = size - limit;
      return `The selected songs would create a ${size.toFixed(2)} MiB ROM, exceeding the ${limit} MiB GBA limit by ${excess.toFixed(2)} MiB before credits are added. Shorten your audio files or replace fewer tracks, then try again.`;
    }
    if (message.includes('32 MiB ROM limit')) {
      return 'The ROM exceeds the 32 MiB GBA limit after adding credits. Shorten your audio files or replace fewer tracks, then try again.';
    }
    if (message.includes('MemoryError')) {
      return 'There is not enough browser memory to process the selected audio. Try shorter audio files or fewer tracks. Reload the page before trying again.';
    }
    if (message.includes('Please select at least one song')) {
      return 'Please select at least one song to replace before applying REharmonized.';
    }
    return 'The ROM could not be created. Check your selected audio files and internet connection, then try again. Your original ROM has not been changed.';
  }

  _handleRomLoaded = (e) => {
    this.injectionError = '';
    this.romLoaded = true;
    this.romFileName = e.detail.name;
    this.romFile = e.detail.file;
  };
}

customElements.define('app-root', AppRoot);
