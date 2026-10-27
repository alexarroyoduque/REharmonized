import base64
import io
import json
import struct
import sys
import tempfile
from pathlib import Path

scripts = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(scripts))
from modules import credits


def main():
    script = Path(credits.__file__).resolve()
    version = credits.VERSION
    credits.VERSION = f"{credits.VERSION}-custom"

    bitmap_addr = 0x08123400
    entry_addr = 0x08000200
    with tempfile.TemporaryDirectory() as directory:
        stub = credits.assemble_stub(bitmap_addr, entry_addr, Path(directory))
        offsets = []
        for address in (bitmap_addr, entry_addr):
            literal = struct.pack("<I", address)
            if stub.count(literal) != 1:
                raise RuntimeError("Credits stub no longer has unique address literals")
            offsets.append(stub.index(literal))

        for bitmap_test, entry_test in ((0x08812340, 0x08001234), (0x09F05678, 0x08005678)):
            relocated = bytearray(stub)
            struct.pack_into("<I", relocated, offsets[0], bitmap_test)
            struct.pack_into("<I", relocated, offsets[1], entry_test)
            expected = credits.assemble_stub(bitmap_test, entry_test, Path(directory))
            if relocated != expected:
                raise RuntimeError("Relocated credits stub differs from native assembler output")

    image = io.BytesIO()
    credits.render_credits_image().save(image, format="PNG")
    print(json.dumps({
        "version": version,
        "source": script.read_text(),
        "image": base64.b64encode(image.getvalue()).decode("ascii"),
        "stub": base64.b64encode(stub).decode("ascii"),
        "bitmapOffset": offsets[0],
        "entryOffset": offsets[1],
    }))


if __name__ == "__main__":
    main()