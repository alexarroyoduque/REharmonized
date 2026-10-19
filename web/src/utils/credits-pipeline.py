import base64
import io
import json
import struct
import sys
import tempfile
import wave
from array import array
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "/tmp")

from wav_to_harmony_pause_fix import main as inject_main
import add_credits_screen as credits

job = json.loads(credits_job_json)
assets = job["assets"]
audio_base = inject_main.__globals__["base"]
original_read_wav = audio_base.read_wav_mono_float


def read_wav_compact(path):
    samples = array("d")
    with wave.open(str(path), "rb") as source, tempfile.TemporaryDirectory() as directory:
        chunk_path = Path(directory) / "chunk.wav"
        while True:
            frames = source.readframes(16384)
            if not frames:
                break
            with wave.open(str(chunk_path), "wb") as chunk:
                chunk.setnchannels(source.getnchannels())
                chunk.setsampwidth(source.getsampwidth())
                chunk.setframerate(source.getframerate())
                chunk.writeframes(frames)
            mono, rate = original_read_wav(chunk_path)
            samples.extend(mono)
        return samples, source.getframerate()


def precompiled_stub(bitmap_addr, original_target, tmpdir):
    stub = bytearray(base64.b64decode(assets["stub"]))
    struct.pack_into("<I", stub, assets["bitmapOffset"], bitmap_addr)
    struct.pack_into("<I", stub, assets["entryOffset"], original_target)
    return bytes(stub)


def precompiled_image():
    return credits.Image.open(io.BytesIO(base64.b64decode(assets["image"]))).convert("RGB")


sys.argv = ["wav_to_harmony_pause_fix.py", job["romPath"], job["configPath"], job["injectedPath"]]
with patch.object(audio_base, "read_wav_mono_float", read_wav_compact):
    inject_main()

sys.argv = ["add_credits_screen.py", job["injectedPath"], job["outputPath"]]
with patch.object(credits, "assemble_stub", precompiled_stub), patch.object(credits.shutil, "which", return_value="precompiled"):
    credits.main(render_fn=precompiled_image)