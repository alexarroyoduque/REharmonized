"""Read the repository's canonical application/ROM release version."""
from __future__ import annotations

import re
from pathlib import Path


def _read_version() -> str:
    for parent in Path(__file__).resolve().parents:
        version_file = parent / "VERSION"
        if version_file.is_file():
            version = version_file.read_text(encoding="ascii").strip()
            if re.fullmatch(r"\d+\.\d+\.\d+", version):
                return version
            raise RuntimeError(f"Invalid semantic version in {version_file}: {version!r}")
    raise FileNotFoundError("Could not find repository VERSION file")


VERSION = _read_version()