#!/usr/bin/env bash
# Force-install ami in Chrome and Firefox for every profile on this machine.
#
#   sudo scripts/install-policies.sh               install / update
#   sudo scripts/install-policies.sh --keep-incognito   don't disable Chrome incognito
#   sudo scripts/install-policies.sh --uninstall   remove ami's policies (ami will notice)
#
# Chrome reads /etc/opt/chrome/policies/managed/*.json; snap Firefox reads /etc/firefox/policies/policies.json.
# Both apply to all profiles, including ones created later. The local daemon token is
# passed through policy, so no profile needs manual setup.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }
: "${SUDO_USER:?Run with sudo from your normal account.}"
home="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
data="$home/.local/share/ami/ext"
url="http://127.0.0.1:47821"
chrome_file=/etc/opt/chrome/policies/managed/ami.json
firefox_file=/etc/firefox/policies/policies.json
ff_id="ami-companion@ami.local"

mode=install
keep_incognito=0
for arg in "$@"; do
  case "$arg" in
    --uninstall) mode=uninstall ;;
    --keep-incognito) keep_incognito=1 ;;
    *) echo "unknown option $arg" >&2; exit 1 ;;
  esac
done

if [ "$mode" = uninstall ]; then
  rm -f "$chrome_file" && echo "removed $chrome_file"
  if [ -f "$firefox_file" ]; then
    python3 - "$firefox_file" "$ff_id" <<'PY'
import json, sys
path, ext = sys.argv[1], sys.argv[2]
d = json.load(open(path))
p = d.get("policies", {})
p.get("ExtensionSettings", {}).pop(ext, None)
p.get("3rdparty", {}).get("Extensions", {}).pop(ext, None)
json.dump(d, open(path, "w"), indent=2)
print("removed ami from", path)
PY
  fi
  exit 0
fi

token="$(cat "$home/.config/ami/token")"
chrome_id="$(cat "$data/chrome-id" 2>/dev/null || true)"

# ---- Chrome ----
if [ -n "$chrome_id" ]; then
  mkdir -p "$(dirname "$chrome_file")"
  python3 - "$chrome_file" "$chrome_id" "$url" "$token" "$keep_incognito" <<'PY'
import json, os, sys
path, ext, url, token, keep_incognito = sys.argv[1:6]
policy = {
    "ExtensionSettings": {ext: {"installation_mode": "force_installed",
                                "update_url": f"{url}/ext/updates.xml",
                                "toolbar_pin": "force_pinned"}},
    "3rdparty": {"extensions": {ext: {"daemonUrl": url, "token": token}}},
    "BrowserGuestModeEnabled": False,   # guest windows can't run extensions
}
if keep_incognito != "1":
    policy["IncognitoModeAvailability"] = 1  # force-installed extensions can't be turned on in incognito
with open(path, "w") as f:
    json.dump(policy, f, indent=2)
os.chmod(path, 0o644)
print("wrote", path)
PY
else
  echo "Chrome: skipped (run scripts/build-extension.sh first)"
fi

# ---- Firefox ----
if [ -f "$data/ami.xpi" ]; then
  mkdir -p "$(dirname "$firefox_file")"
  python3 - "$firefox_file" "$ff_id" "$url" "$token" <<'PY'
import json, os, sys
path, ext, url, token = sys.argv[1:5]
d = json.load(open(path)) if os.path.exists(path) else {}
p = d.setdefault("policies", {})
p.setdefault("ExtensionSettings", {})[ext] = {"installation_mode": "force_installed",
                                             "install_url": f"{url}/ext/ami.xpi",
                                             "private_browsing": True}
p.setdefault("3rdparty", {}).setdefault("Extensions", {})[ext] = {"daemonUrl": url, "token": token}
with open(path, "w") as f:
    json.dump(d, f, indent=2)
os.chmod(path, 0o644)
print("wrote", path)
PY
else
  echo "Firefox: skipped (no signed ami.xpi yet; see scripts/build-extension.sh)"
fi

echo "Done. Restart Chrome/Firefox; check chrome://policy and about:policies."
