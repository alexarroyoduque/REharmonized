import { LitElement, html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import SONGS from '../../songs.json';
import './song-item.js';

class SongList extends LitElement {
  static properties = {
    songs: { type: Array },
    romFile: { type: Object },
    bulkMode: { type: String },
  };

  static styles = css`
    :host {
      display: block;
    }

    .songs-container {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 1rem;
      animation: slideUp 0.3s ease;
    }

    @media (max-width: 760px) {
      .songs-container {
        grid-template-columns: minmax(0, 1fr);
      }
    }

    .songs-header {
      background-color: var(--bg-secondary);
      border-left: 4px solid var(--accent);
      padding: 1rem;
      margin-bottom: 1rem;
      border-radius: 4px;
    }

    .songs-header h3 {
      color: var(--accent);
      margin: 0;
      font-size: 1.1rem;
    }

    .songs-header p {
      color: var(--text-secondary);
      margin: 0.5rem 0 0 0;
      font-size: 0.9rem;
    }

    .bulk-options {
      display: flex;
      flex-wrap: wrap;
      gap: 1.25rem;
      margin-top: 1rem;
    }

    .bulk-option {
      display: flex;
      align-items: center;
      gap: 0.65rem;
      color: var(--text-primary);
      cursor: pointer;
    }

    .bulk-option input {
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
      cursor: pointer;
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
    this.songs = SONGS;
    this.romFile = null;
    this.bulkMode = '';
  }

  render() {
    return html`
      <div class="songs-header">
        <h3>♫ Customize Harmony of Dissonance Soundtrack</h3>
        <p>⚠ Remember that the maximum size for a GBA ROM is 32MB</p>
        <div class="bulk-options" role="radiogroup" aria-label="Apply mode to all tracks">
          <label class="bulk-option">
            <input
              type="radio"
              name="bulk-mode"
              value="none"
              .checked=${this.bulkMode === 'none'}
              @change=${this._handleBulkModeChange}
            />
            <span>Set all to "No modification"</span>
          </label>
          <label class="bulk-option">
            <input
              type="radio"
              name="bulk-mode"
              value="reharmonized"
              .checked=${this.bulkMode === 'reharmonized'}
              @change=${this._handleBulkModeChange}
            />
            <span>Set all to "REharmonized preset"</span>
          </label>
        </div>
      </div>

      <div class="songs-container">
        ${repeat(
          this.songs,
          (song) => song.id,
          (song) => html`<song-item
            .song=${song}
            .romFile=${this.romFile}
            @mode-changed=${this._handleSongModeChanged}
          ></song-item>`
        )}
      </div>
    `;
  }

  _handleBulkModeChange(event) {
    this.bulkMode = event.target.value;
    this.shadowRoot.querySelectorAll('song-item').forEach((item) => {
      item.mode = this.bulkMode === 'reharmonized' && item.song.preset === true
        ? 'reharmonized'
        : 'none';
      item.showCustomFields = false;
    });
  }

  _handleSongModeChanged() {
    this.bulkMode = '';
  }

  /**
   * Collect all song selections (mode, wav files, tempos, volumes)
   * Called by app.js when applying REharmonized
   */
  getSelections() {
    const items = this.shadowRoot.querySelectorAll('song-item');
    const selections = [];

    items.forEach((item) => {
      selections.push({
        song_id: item.song.id,
        mode: item.mode,
        wav_file: item.customWav,
        tempo: item.customTempo,
        volume: item.customVolume,
      });
    });

    return selections;
  }
}

customElements.define('song-list', SongList);
