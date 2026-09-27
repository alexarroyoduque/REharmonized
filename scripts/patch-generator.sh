#!/bin/bash

# ============================================================
# This script generates REharmonized patches for the specified ROMs
# Inside the folder containing this script
# git clone https://github.com/marcrobledo/RomPatcher.js.git
# cd RomPatcher.js
# npm install
# chmod +x patch-generator.sh
# Run: ./patch-generator.sh
# ============================================================

# SOURCES
ROM_ORIGINAL_USA="rom-harmony-usa.gba"
ROM_ORIGINAL_EUROPE="rom-harmony-europe.gba"
VERSION="1.3.1"
ROM_REHARMONIZED_USA="rom-harmony-usa-reharmonized-$VERSION"
ROM_REHARMONIZED_EUROPE="rom-harmony-europe-reharmonized-$VERSION"

# RESULTS
PATCH_USA="REharmonized-usa.bps"
PATCH_EUROPE="REharmonized-europe.bps"

# ============================================================
# WAIT-FILE FUNCTION
# ============================================================
wait_file() {
    local file_path="$1"
    for i in {1..100}; do
        if [ -f "$file_path" ]; then
            local file_size
            file_size=$(stat -f%z "$file_path" 2>/dev/null || echo 0)
            if [ "$file_size" -gt 0 ]; then
                return 0
            fi
        fi
        sleep 0.1
    done
    echo "Error: Archivo no generado -> $file_path" >&2
    return 1
}

# ============================================================
# PREVIOUS CLEANUP
# ============================================================
rm -f "$PATCH_USA" "$PATCH_EUROPE"

echo ""
echo "========================================"
echo "GENERATING REharmonized patches"
echo "========================================"
echo ""

if node ./RomPatcher.js/index.js create --format bps "$ROM_ORIGINAL_USA" "$ROM_REHARMONIZED_USA".gba; then
    echo "OK: REharmonized USA patch generated"
    mv "$ROM_REHARMONIZED_USA".bps "$PATCH_USA"
    echo "$PATCH_USA"
    echo ""
else
    echo "Error: REharmonized USA" >&2
    exit 1
fi

if node ./RomPatcher.js/index.js create --format bps "$ROM_ORIGINAL_EUROPE" "$ROM_REHARMONIZED_EUROPE".gba; then
    echo "OK: REharmonized Europe patch generated"
    mv "$ROM_REHARMONIZED_EUROPE".bps "$PATCH_EUROPE"
    echo "$PATCH_EUROPE"
    echo ""
else
    echo "Error: REharmonized Europe" >&2
    exit 1
fi

echo "Move patches to parent directory"
mv -f "$PATCH_EUROPE" "$PATCH_USA" "../"

echo "Process completed."
echo ""