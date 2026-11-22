#!/usr/bin/env bash
# Fetch Basilisk (MIT) at the commit archetypal's UMI support is pinned to (research R15).
# The checkout goes to tools/basilisk-check/.basilisk/, which basilisk-check.csproj compiles.
set -euo pipefail

BASILISK_URL="https://github.com/MITSustainableDesignLab/basilisk"
BASILISK_COMMIT="5cce24e8"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
dest="${here}/.basilisk"

if [ ! -d "${dest}/.git" ]; then
    git clone --quiet --no-checkout "${BASILISK_URL}" "${dest}"
fi
if ! git -C "${dest}" cat-file -e "${BASILISK_COMMIT}^{commit}" 2>/dev/null; then
    git -C "${dest}" fetch --quiet origin
fi
git -C "${dest}" -c advice.detachedHead=false checkout --quiet --force "${BASILISK_COMMIT}"
echo "basilisk at $(git -C "${dest}" rev-parse --short=8 HEAD) in ${dest}"
