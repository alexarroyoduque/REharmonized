export const ORIGINAL_ROM_MESSAGE = 'Select a compatible Harmony of Dissonance ROM (USA or Europe, exactly 8 MiB) without REharmonized already applied. Compatible visual patches are allowed if they preserve the ROM size and audio engine. A ROM already patched with REharmonized cannot be processed again. Your file has not been changed.';

function invalidRom(message = ORIGINAL_ROM_MESSAGE) {
  const error = new Error(message);
  error.code = 'INVALID_ORIGINAL_ROM';
  return error;
}

export async function validateOriginalRom(file) {
  if (file.size !== 8 * 1024 * 1024) throw invalidRom();

  const code = new TextDecoder().decode(await file.slice(0xAC, 0xB0).arrayBuffer());
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
  return code;
}