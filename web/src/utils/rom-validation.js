export const ORIGINAL_ROM_MESSAGE = 'Select a compatible 8 MiB Harmony of Dissonance ROM: USA or Europe, or the supported Advance Collection USA ROM (02_Byakuya_US.patch_210520m.bin). Compatible visual patches are allowed if they preserve the required format and audio-engine signature. Do not select a ROM with REharmonized already applied. Your file has not been changed.';

const COLLECTION_ENGINE_START = 0x0bb655;
const COLLECTION_ENGINE_END = 0x0bd739;
const COLLECTION_ENGINE_SHA256 = '8b65a0b54dc6912460f9bbead4180be0f0079949a0b2366da26fd289dd35b68f';

async function hasAdvanceCollectionEngine(file) {
  if (!globalThis.crypto?.subtle) {
    throw new Error('Secure SHA-256 verification is unavailable in this environment.');
  }
  const engineBytes = await file
    .slice(COLLECTION_ENGINE_START, COLLECTION_ENGINE_END)
    .arrayBuffer();
  const digest = new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256', engineBytes));
  const hash = [...digest].map((byte) => byte.toString(16).padStart(2, '0')).join('');
  return hash === COLLECTION_ENGINE_SHA256;
}

function invalidRom(message = ORIGINAL_ROM_MESSAGE) {
  const error = new Error(message);
  error.code = 'INVALID_ORIGINAL_ROM';
  return error;
}

export async function validateOriginalRom(file) {
  if (file.size !== 8 * 1024 * 1024) throw invalidRom();

  const code = new TextDecoder().decode(await file.slice(0xAC, 0xB0).arrayBuffer());
  if (code === 'ACHE' && await hasAdvanceCollectionEngine(file)) {
    return { gameCode: code, advanceCollection: true };
  }

  if (!['ACHE', 'ACHP'].includes(code)) {
    throw invalidRom('This is not a supported Harmony of Dissonance ROM. Select a compatible USA (ACHE) or Europe (ACHP) version without REharmonized already applied.');
  }

  const signatures = [
    [0xBC458, [0x28, 0x68, 0x00, 0xF0, 0x43, 0xFB]],
    [0xBBF2C, [0xA1, 0x7C, 0x14, 0x20, 0x22, 0x56, 0x80, 0x23]],
  ];
  for (const [offset, expected] of signatures) {
    const bytes = new Uint8Array(await file.slice(offset, offset + expected.length).arrayBuffer());
    if (!expected.every((value, index) => bytes[index] === value)) throw invalidRom();
  }
  return { gameCode: code, advanceCollection: false };
}