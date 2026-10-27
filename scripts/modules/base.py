"""Compatibility exports for legacy scripts and tempo consumers."""
from __future__ import annotations

from .rom import *
from .audio import *
from .normalization import *
from .tempo import *
from .songs import DEFAULT_BASE_NOTE, DEFAULT_VOLUME
from .songs import build_legacy_song_blob as build_song_blob
from .config import parse_legacy_config as parse_config


