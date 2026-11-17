#!/usr/bin/env bash
set -euo pipefail

revision="${PARTYDECK_REVISION:-main}"
[[ $revision =~ ^[A-Za-z0-9._/-]+$ ]] || { echo "Révision Git invalide." >&2; exit 2; }
staging=$(mktemp -d /tmp/partydeck-install.XXXXXX)
trap 'rm -rf -- "$staging"' EXIT
curl --fail --silent --show-error --location --retry 2 --connect-timeout 15 \
    --proto '=https' \
    "https://api.github.com/repos/Thomson67/partydeck-batocera/tarball/$revision" \
    --output "$staging/source.tar.gz"
mkdir "$staging/source"
tar -xzf "$staging/source.tar.gz" --strip-components=1 -C "$staging/source"
bash "$staging/source/scripts/install-partydeck-test.sh" installer
