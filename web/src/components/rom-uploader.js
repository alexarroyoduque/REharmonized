import { LitElement, html, css } from 'lit';
import { validateOriginalRom } from '../utils/rom-validation.js';

class RomUploader extends LitElement {
  static properties = {
    romFile: { type: Object },
    validationState: { type: String }, // 'idle' | 'validating' | 'valid' | 'invalid'
    errorMessage: { type: String },
    romName: { type: String },
  };

  static styles = css`
    :host {
      display: block;
    }

    .upload-section {
      background-color: var(--bg-secondary);
      border: 2px dashed var(--accent-dark);
      border-radius: 8px;
      padding: 2rem;
      text-align: center;
      transition: all 0.3s ease;
    }

    .upload-section:hover {
      border-color: var(--accent);
      background-color: var(--status-accent-subtle);
    }

    .upload-section.dragging {
      border-color: var(--accent);
      background-color: var(--status-accent);
    }

    .upload-icon {
      font-size: 3rem;
      margin-bottom: 1rem;
      display: block;
    }

    .upload-text h3 {
      color: var(--accent);
      margin-bottom: 0.5rem;
    }

    .upload-text p {
      color: var(--text-secondary);
      margin-bottom: 1.5rem;
    }

    .file-input-wrapper {
      display: inline-flex;
      max-width: 100%;
    }

    input[type='file'] {
      display: none;
    }

    .file-button {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      background-color: var(--accent);
      color: var(--bg-primary);
      border: none;
      padding: 0.75rem 1rem;
      border-radius: 4px;
      cursor: pointer;
      font-weight: 600;
      font-size: 1rem;
      white-space: nowrap;
      transition: all 0.2s ease;
    }

    .file-button:hover {
      background-color: var(--accent-light);
      box-shadow: 0 0 15px var(--glow-accent-strong);
    }

    .file-button:active {
      transform: scale(0.98);
    }

    .validation-message {
      margin-top: 1.5rem;
      padding: 1rem;
      border-radius: 4px;
      display: flex;
      align-items: center;
      gap: 0.75rem;
    }

    .validation-message.loading {
      background-color: var(--status-accent);
      color: var(--accent);
    }

    .validation-message.error {
      background-color: var(--status-error);
      color: var(--error);
      border: 1px solid var(--error);
    }

    .validation-message.success {
      background-color: var(--status-success);
      color: var(--success);
      border: 1px solid var(--success);
    }

    .spinner {
      display: inline-block;
      width: 18px;
      height: 18px;
      border: 3px solid currentColor;
      border-top-color: var(--transparent);
      border-radius: 50%;
      animation: spin 0.8s linear infinite;
    }

    @keyframes spin {
      to {
        transform: rotate(360deg);
      }
    }

    .icon {
      font-size: 1.2rem;
    }

    .file-name {
      margin-top: 1rem;
      color: var(--text-secondary);
      font-size: 0.9rem;
    }
  `;

  constructor() {
    super();
    this.romFile = null;
    this.validationState = 'idle';
    this.errorMessage = '';
    this.romName = '';
  }

  render() {
    return html`
      <div class="upload-section ?dragging=${false}>
        <span class="upload-icon"></span>
        <div class="upload-text">
          <h3>Upload Harmony of Dissonance ROM</h3>
          <p>You can use the USA or EUR version</p>
        </div>

        <div class="file-input-wrapper">
          <input
            type="file"
            id="rom-input"
            accept=".gba"
            @change=${this._handleFileSelect}
            @dragover=${this._handleDragOver}
            @dragleave=${this._handleDragLeave}
            @drop=${this._handleDrop}
          />
          <label for="rom-input" class="file-button">SELECT ROM FILE</label>
        </div>

        ${this.validationState !== 'idle'
          ? html`
              <div class="validation-message ${this.validationState}">
                ${this.validationState === 'validating'
                  ? html`<div class="spinner"></div><span>Validating ROM...</span>`
                  : this.validationState === 'success'
                    ? html`<span class="icon">✓</span><span>ROM valid! Ready to proceed.</span>`
                    : html`<span class="icon">✗</span><span>${this.errorMessage}</span>`}
              </div>
            `
          : ''}

        ${this.romName ? html`<div class="file-name">File: <strong>${this.romName}</strong></div>` : ''}
      </div>
    `;
  }

  _handleFileSelect(e) {
    const file = e.target.files?.[0];
    if (file) {
      this._validateRom(file);
    }
  }

  _handleDragOver(e) {
    e.preventDefault();
    e.stopPropagation();
    this.uploadSection?.classList.add('dragging');
  }

  _handleDragLeave(e) {
    e.preventDefault();
    e.stopPropagation();
    this.uploadSection?.classList.remove('dragging');
  }

  _handleDrop(e) {
    e.preventDefault();
    e.stopPropagation();
    this.uploadSection?.classList.remove('dragging');

    const file = e.dataTransfer?.files?.[0];
    if (file && file.name.toLowerCase().endsWith('.gba')) {
      this._validateRom(file);
    } else {
      this.validationState = 'invalid';
      this.errorMessage = 'Please select a .gba ROM file';
    }
  }

  async _validateRom(file) {
    this.romFile = file;
    this.romName = file.name;
    this.validationState = 'validating';

    try {
      await new Promise((resolve) => setTimeout(resolve, 500));

      const gameCode = await validateOriginalRom(file);
      this.validationState = 'success';
      this.dispatchEvent(
        new CustomEvent('rom-loaded', {
          detail: { file, name: file.name, gameCode },
          bubbles: true,
          composed: true,
        })
      );
    } catch (error) {
      this.validationState = 'invalid';
      this.errorMessage = error.code === 'INVALID_ORIGINAL_ROM'
        ? error.message : `Error reading ROM: ${error.message}`;
      this.romFile = null;
    }
  }

  get uploadSection() {
    return this.shadowRoot?.querySelector('.upload-section');
  }
}

customElements.define('rom-uploader', RomUploader);
