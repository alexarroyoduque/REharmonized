#!/usr/bin/env python3

import argparse
from pathlib import Path


DEFAULT_SIZE_MB = 30


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Expand a GBA ROM by appending zero-filled space without "
            "modifying any existing ROM data."
        )
    )

    parser.add_argument(
        "input",
        type=Path,
        help="Input .gba ROM",
    )

    parser.add_argument(
        "output",
        type=Path,
        help="Expanded output .gba ROM",
    )

    parser.add_argument(
        "--size-mb",
        type=int,
        default=DEFAULT_SIZE_MB,
        help=f"Target ROM size in MiB (default: {DEFAULT_SIZE_MB})",
    )

    args = parser.parse_args()

    # Check input ROM.
    if not args.input.is_file():
        raise SystemExit(f"ROM not found: {args.input}")

    data = args.input.read_bytes()

    # MiB = 1024 * 1024 bytes.
    target_size = args.size_mb * 1024 * 1024

    if target_size <= 0:
        raise SystemExit("Target size must be greater than 0 MiB.")

    if len(data) > target_size:
        raise SystemExit(
            f"ROM is already larger than requested target size.\n"
            f"Current: {len(data):,} bytes\n"
            f"Target:  {target_size:,} bytes"
        )

    padding_size = target_size - len(data)

    # Write original ROM exactly as-is, followed by zero padding.
    with args.output.open("wb") as f:
        f.write(data)

        # Avoid unnecessarily creating a huge temporary bytes object.
        chunk = b"\x00" * (1024 * 1024)

        remaining = padding_size

        while remaining > 0:
            amount = min(remaining, len(chunk))
            f.write(chunk[:amount])
            remaining -= amount

    final_size = args.output.stat().st_size

    print()
    print("GBA ROM Expander")
    print("=" * 60)
    print(f"Input:         {args.input}")
    print(f"Output:        {args.output}")
    print()
    print(f"Original size: {len(data):,} bytes")
    print(f"Target size:   {target_size:,} bytes")
    print(f"Added space:   {padding_size:,} bytes")
    print(f"Final size:    {final_size:,} bytes")
    print()

    if final_size != target_size:
        raise SystemExit(
            f"ERROR: resulting ROM has unexpected size "
            f"({final_size:,} instead of {target_size:,})"
        )

    print("OK")
    print("Existing ROM data was not modified.")
    print("New space was filled with 0x00.")


if __name__ == "__main__":
    main()