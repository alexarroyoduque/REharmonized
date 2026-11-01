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
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
ROM_ORIGINAL_USA="rom-harmony-usa.gba"
ROM_ORIGINAL_ADVANCE_COLLECTION="02_Byakuya_US.patch_210520m.bin"
VERSION="$(tr -d '[:space:]' < "$SCRIPT_DIR/../VERSION")"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "Error: Invalid version in $SCRIPT_DIR/../VERSION: $VERSION" >&2
    exit 1
fi
ROM_REHARMONIZED_USA="rom-harmony-usa-$VERSION"
ROM_REHARMONIZED_ADVANCE_COLLECTION="02_Byakuya_US.patch_210520m-$VERSION"

# RESULTS
PATCH_USA="REharmonized.bps"
PATCH_ADVANCE_COLLECTION="REharmonized-AdvanceCollection.bps"

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
rm -f "$PATCH_USA" "$PATCH_ADVANCE_COLLECTION"

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

if node ./RomPatcher.js/index.js create --format bps "$ROM_ORIGINAL_ADVANCE_COLLECTION" "$ROM_REHARMONIZED_ADVANCE_COLLECTION".bin; then
    echo "OK: REharmonized Advance Collection patch generated"
    mv "$ROM_REHARMONIZED_ADVANCE_COLLECTION".bps "$PATCH_ADVANCE_COLLECTION"
    echo "$PATCH_ADVANCE_COLLECTION"
    echo ""
else
    echo "Error: REharmonized Advance Collection" >&2
    exit 1
fi

echo "Move patches to parent directory"
mv -f "$PATCH_ADVANCE_COLLECTION" "$PATCH_USA" "../"

echo "Process completed."
echo ""