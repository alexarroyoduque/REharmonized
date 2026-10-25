from pathlib import Path

from PIL import Image


def main():
    root = Path(__file__).resolve().parents[1]
    destination = root / "desktop/runtime/icon.icns"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(root / "favicon.ico") as source:
        image = source.convert("RGBA").resize((1024, 1024), Image.Resampling.NEAREST)
        image.save(destination, format="ICNS")
        windows_image = image.resize((256, 256), Image.Resampling.NEAREST)
        windows_image.save(destination.with_suffix(".ico"), format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (256, 256)])
        windows_image.save(destination.with_suffix(".png"), format="PNG")


if __name__ == "__main__":
    main()