from pathlib import Path

from PIL import Image


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "desktop/runtime/icon.icns"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(root / "favicon.ico") as source:
        image = source.convert("RGBA").resize((1024, 1024), Image.Resampling.NEAREST)
        image.save(destination, format="ICNS")


if __name__ == "__main__":
    main()