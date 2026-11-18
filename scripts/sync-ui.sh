#!/usr/bin/env bash
# Copy the design system from ui/ (the source of truth) into the extension.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$root/extension/ui"
cp "$root/ui/tokens.css" "$root/ui/overlay.css" "$root/extension/ui/"
echo "synced ui/*.css -> extension/ui/"
