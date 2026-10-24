import { LitElement, html, css } from 'lit';
import { processWavForTempos } from '../utils/pyodide-wrapper.js';

class SongItem extends LitElement {
  static properties = {
    song: { type: Object },
    romFile: { type: Object },
    mode: { type: String }, // 'none' | 'reharmonized' | 'custom'
    customWav: { type: Object },
    customTempo: { type: String }, // 'auto' or number
    customVolume: { type: String }, // decimal string
    showCustomFields: { type: Boolean },
    suggestionsLoading: { type: Boolean },
    suggestions: { type: Array },
    tempoInfoOpen: { type: Boolean },
  };

  static styles = css`
    :host {
      display: block;
    }

    .song-item {
      background-color: var(--bg-secondary);
      border: 1px solid var(--accent-dark);
      border-radius: 4px;
      padding: .8rem;
      transition: all 0.2s ease;
    }

    .song-item:hover {
      border-color: var(--accent);
      box-shadow: 0 0 10px var(--glow-accent-subtle);
    }

    .song-header {
      display: flex;
      justify-content: space-between;
      align-items: start;
      margin-bottom: 1.5rem;
      gap: 1rem;
    }

    .song-info {
      flex: 1;
      min-width: 0;
      display: flex;
      align-items: baseline;
      gap: 0.6rem;
    }

    .song-id {
      color: var(--accent);
      font-weight: bold;
      font-size: 0.9rem;
      white-space: nowrap;
    }

    .song-name {
      color: var(--text-primary);
      font-size: 1rem;
      margin: 0;
      min-width: 0;
      word-break: break-word;
    }

    .radio-group {
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
    }

    .radio-option {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      cursor: pointer;
    }

    .radio-option input[type='radio'] {
      cursor: pointer;
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
    }

    .radio-option label {
      cursor: pointer;
      color: var(--text-primary);
      font-size: 0.95rem;
      margin: 0;
    }

    .radio-option input:disabled,
    .radio-option input:disabled + label {
      cursor: not-allowed;
      opacity: 0.5;
    }

    .radio-option input[type='radio']:checked + label {
      color: var(--accent);
      font-weight: 600;
    }

    .custom-fields {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--accent-dark);
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 1rem;
      min-width: 0;
      animation: slideDown 0.3s ease;
    }

    .field-group {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }

    .field-group label {
      color: var(--text-secondary);
      font-size: 0.9rem;
      font-weight: 500;
    }

    .field-row {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
      min-width: 0;
    }

    .field-row .field-group {
      width: 100%;
      min-width: 0;
    }

    input[type='file'],
    input[type='number'] {
      background-color: var(--bg-primary);
      color: var(--text-primary);
      border: 1px solid var(--accent-dark);
      padding: 0.75rem;
      border-radius: 4px;
      font-size: 0.95rem;
      transition: border-color 0.2s ease;
      box-sizing: border-box;
      min-width: 0;
      max-width: 100%;
    }

    input[type='file']:focus,
    input[type='number']:focus {
      outline: none;
      border-color: var(--accent);
      box-shadow: 0 0 10px var(--glow-accent-medium);
    }

    input[type='file']::file-selector-button {
      background-color: var(--accent);
      color: var(--bg-primary);
      border: none;
      padding: 0.5rem 1rem;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 600;
      margin-right: 0.5rem;
      transition: background-color 0.2s ease;
    }

    input[type='file']::file-selector-button:hover {
      background-color: var(--accent-light);
    }

    .file-name {
      color: var(--text-secondary);
      font-size: 0.85rem;
      margin-top: 0.25rem;
    }

    .suggest-actions {
      display: flex;
      align-items: center;
      gap: 0.65rem;
    }

    button.suggest-btn {
      background-color: var(--accent-dark);
      color: var(--text-primary);
      border: 1px solid var(--accent);
      padding: 0.75rem 1.5rem;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 600;
      transition: all 0.2s ease;
      flex: 1;
      min-width: 0;
      font-size: 0.95rem;
    }

    button.suggest-btn:hover {
      background-color: var(--accent);
      color: var(--bg-primary);
      box-shadow: 0 0 15px var(--glow-accent-medium);
    }

    button.suggest-btn:active {
      transform: scale(0.98);
    }

    button.suggest-btn:disabled {
      background-color: var(--text-secondary);
      border-color: var(--text-secondary);
      cursor: not-allowed;
      opacity: 0.5;
    }

    .tempo-info {
      position: relative;
      flex: 0 0 auto;
    }

    .tempo-info-button {
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      padding: 0;
      border: 1px solid var(--accent);
      border-radius: 50%;
      background: var(--bg-primary);
      color: var(--accent-light);
      font-size: 1rem;
      font-weight: 700;
      cursor: pointer;
    }

    .tempo-info-button:hover,
    .tempo-info-button:focus-visible {
      background: var(--accent-dark);
      outline: 2px solid var(--accent-light);
      outline-offset: 2px;
    }

    .tempo-tooltip {
      position: absolute;
      z-index: 5;
      right: 0;
      bottom: calc(100% + 0.65rem);
      box-sizing: border-box;
      width: min(320px, calc(100vw - 3rem));
      padding: 0.85rem 1rem;
      border: 1px solid var(--accent);
      border-radius: 4px;
      background: var(--tooltip-surface);
      box-shadow: 0 8px 24px var(--shadow-tooltip);
      color: var(--text-primary);
      font-size: 0.9rem;
      line-height: 1.5;
    }

    .spinner {
      display: inline-block;
      width: 16px;
      height: 16px;
      border: 2px solid currentColor;
      border-top-color: var(--transparent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
      margin-right: 0.5rem;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    .suggestions {
      margin-top: 1rem;
      padding: 1rem;
      background-color: var(--status-accent);
      border-left: 3px solid var(--accent);
      border-radius: 4px;
    }

    .suggestions-title {
      color: var(--accent);
      font-weight: 600;
      margin-bottom: 0.2rem;
      font-size: 0.95rem;
    }

    .suggestion-item {
      color: var(--text-secondary);
      font-size: 0.9rem;
      font-family: monospace;
    }

    @keyframes slideDown {
      from {
        opacity: 0;
        max-height: 0;
        overflow: hidden;
      }
      to {
        opacity: 1;
        max-height: 500px;
        overflow: visible;
      }
    }
  `;

  constructor() {
    super();
    this.song = null;
    this.romFile = null;
    this.mode = 'none';
    this.customWav = null;
    this.customTempo = 'auto';
    this.customVolume = '0.4';
    this.showCustomFields = false;
    this.suggestionsLoading = false;
    this.suggestions = [];
    this.tempoInfoOpen = false;
  }

  render() {
    return html`
      <div class="song-item">
        <div class="song-header">
          <div class="song-info">
            <div class="song-id">${this.song.id}</div>
            <p class="song-name">${this.song.name}</p>
          </div>
        </div>

        <div class="radio-group">
          <div class="radio-option">
            <input
              type="radio"
              id="mode-none-${this.song.id}"
              name="mode-${this.song.id}"
              value="none"
              .checked=${this.mode === 'none'}
              @change=${this._handleModeChange}
            />
            <label for="mode-none-${this.song.id}">No modification</label>
          </div>

          ${this.song.preset === true
            ? html`
                <div class="radio-option">
                  <input
                    type="radio"
                    id="mode-reharmonized-${this.song.id}"
                    name="mode-${this.song.id}"
                    value="reharmonized"
                    disabled
                    .checked=${this.mode === 'reharmonized'}
                    @change=${this._handleModeChange}
                  />
                  <label for="mode-reharmonized-${this.song.id}">REharmonized preset</label>
                </div>
              `
            : ''}

          <div class="radio-option">
            <input
              type="radio"
              id="mode-custom-${this.song.id}"
              name="mode-${this.song.id}"
              value="custom"
              .checked=${this.mode === 'custom'}
              @change=${this._handleModeChange}
            />
            <label for="mode-custom-${this.song.id}">Custom</label>
          </div>
        </div>

        ${this.showCustomFields
          ? html`
              <div class="custom-fields">
                <div class="field-group">
                  <label for="wav-${this.song.id}">Upload .wav file</label>
                  <input
                    type="file"
                    id="wav-${this.song.id}"
                    accept=".wav"
                    @change=${this._handleWavSelect}
                  />
                  ${this.customWav
                    ? html`<div class="file-name">📁 ${this.customWav.name}</div>`
                    : html`<div class="file-name">No file selected</div>`}
                </div>

                <div class="field-row">
                  <div class="field-group">
                    <label for="tempo-${this.song.id}">Tempo (leave empty for "auto")</label>
                    <input
                      type="number"
                      id="tempo-${this.song.id}"
                      min="1"
                      max="255"
                      placeholder="auto"
                      .value=${this.customTempo === 'auto' ? '' : this.customTempo}
                      @change=${this._handleTempoChange}
                    />
                    <div class="file-name">Range: 1–255 (integers only)</div>
                  </div>

                  <div class="field-group">
                    <label for="volume-${this.song.id}">Volume normalization (RMS target)</label>
                    <input
                      type="number"
                      id="volume-${this.song.id}"
                      min="0.01"
                      max="1"
                      step="0.01"
                      placeholder="0.4"
                      .value=${this.customVolume}
                      @change=${this._handleVolumeChange}
                    />
                    <div class="file-name">Default: 0.4 (range: 0.01–1)</div>
                  </div>
                </div>

                <div class="suggest-actions">
                  <button class="suggest-btn" @click=${this._suggestTempos} ?disabled=${!this.customWav || this.suggestionsLoading}>
                    ${this.suggestionsLoading ? html`<span class="spinner"></span>` : ''} SUGGEST TEMPOS
                  </button>
                  <div class="tempo-info">
                    <button
                      class="tempo-info-button"
                      type="button"
                      aria-label="About tempo"
                      aria-expanded=${this.tempoInfoOpen ? 'true' : 'false'}
                      aria-describedby=${this.tempoInfoOpen ? `tempo-info-${this.song.id}` : ''}
                      @click=${this._toggleTempoInfo}
                      @keydown=${this._handleTempoInfoKeydown}
                    >
                      <span aria-hidden="true">i</span>
                    </button>
                    ${this.tempoInfoOpen
                      ? html`
                          <div class="tempo-tooltip" id="tempo-info-${this.song.id}" role="tooltip">
                            Each song repeats in a loop. Tempo controls how long each loop lasts and helps the next loop begin more smoothly. In practice, a negative gap means the loops overlap, which often makes the transition smoother.
                          </div>
                        `
                      : ''}
                  </div>
                </div>

                <div class="suggestions" ?hidden=${this.suggestions.length === 0}>
                  <div class="suggestions-title">Suggested tempos for different gaps:</div>
                  ${this.suggestions.map((sug) => html`
                    <div class="suggestion-item">
                      gap = ${sug.target_gap_s > 0 ? '+' : ''}${sug.target_gap_s.toFixed(1)}s → tempo = <strong>0x${sug.tempo.toString(16).toUpperCase().padStart(2, '0')} (${sug.tempo})</strong>
                    </div>
                  `)}
                </div>
              </div>
            `
          : ''}
      </div>
    `;
  }

  _handleModeChange(e) {
    this.mode = e.target.value;
    this.showCustomFields = this.mode === 'custom';
    this.tempoInfoOpen = false;
    this.dispatchEvent(new CustomEvent('mode-changed', {
      bubbles: true,
      composed: true,
    }));
  }

  _toggleTempoInfo() {
    this.tempoInfoOpen = !this.tempoInfoOpen;
  }

  _handleTempoInfoKeydown(e) {
    if (e.key === 'Escape') {
      this.tempoInfoOpen = false;
    }
  }

  _handleWavSelect(e) {
    this.customWav = e.target.files?.[0] || null;
  }

  _handleTempoChange(e) {
    const input = e.target;
    const value = input.value;

    if (value === '') {
      input.setCustomValidity('');
      this.customTempo = 'auto';
      return;
    }

    const tempo = Number(value);
    if (!Number.isInteger(tempo) || tempo < 1 || tempo > 255) {
      input.setCustomValidity('Tempo must be an integer between 1 and 255.');
      input.reportValidity();
      input.value = this.customTempo === 'auto' ? '' : this.customTempo;
      return;
    }

    input.setCustomValidity('');
    this.customTempo = String(tempo);
  }

  _handleVolumeChange(e) {
    const input = e.target;
    const value = input.value;

    if (value === '') {
      input.setCustomValidity('');
      this.customVolume = '0.4';
      return;
    }

    const volume = Number(value);
    if (!Number.isFinite(volume) || volume < 0.01 || volume > 1) {
      input.setCustomValidity('Volume must be between 0.01 and 1.');
      input.reportValidity();
      input.value = this.customVolume;
      return;
    }

    input.setCustomValidity('');
    this.customVolume = value;
  }

  async _suggestTempos() {
    if (!this.customWav) {
      alert('Please select a .wav file');
      return;
    }

    this.suggestionsLoading = true;
    this.suggestions = [];

    try {
      console.log(`[Song ${this.song.id}] Processing WAV file locally...`);

      // Process WAV locally using JS (no backend needed!)
      const result = await processWavForTempos(this.customWav, this.song.id);

      console.log(`[Song ${this.song.id}] Duration: ${result.duration_s}s`);
      console.log(`[Song ${this.song.id}] Got ${result.suggestions.length} suggestions`);

      this.suggestions = result.suggestions;

      if (this.suggestions.length === 0) {
        alert('No tempo suggestions available');
      }
    } catch (error) {
      console.error(`[Song ${this.song.id}] Error:`, error);
      alert(`Error calculating tempos: ${error.message}`);
      this.suggestions = [];
    } finally {
      this.suggestionsLoading = false;
    }
  }

  _hasSuggestions() {
    // Deprecated - kept for reference
    return false;
  }
}

customElements.define('song-item', SongItem);
