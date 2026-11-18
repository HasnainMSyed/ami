#!/usr/bin/env bash
# Install ami as a systemd *user* service (no sudo): starts at login, restarts on failure.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
unit_dir="$HOME/.config/systemd/user"
mkdir -p "$unit_dir"
cp "$root/systemd/ami.service" "$unit_dir/ami.service"
systemctl --user daemon-reload
systemctl --user enable --now ami.service
sleep 2
systemctl --user --no-pager --lines=5 status ami.service || true
echo
echo "Logs: journalctl --user -u ami -f"
