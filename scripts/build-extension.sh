#!/usr/bin/env bash
# Package the extension for policy installs and publish it where the daemon serves /ext/*.
#   Chrome:  signed CRX (local key -> stable extension ID) + updates.xml
#   Firefox: signed XPI via AMO "unlisted" signing, if AMO_JWT_ISSUER / AMO_JWT_SECRET are in .env
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cfg="${AMI_CONFIG_DIR:-$HOME/.config/ami}"
out="${AMI_DATA_DIR:-$HOME/.local/share/ami}/ext"
dist="$root/extension/dist"
url="http://127.0.0.1:47821"
mkdir -p "$cfg" "$out"

"$root/scripts/sync-ui.sh"
version="0.1.$(git -C "$root" rev-list --count HEAD)"

# Fresh copy of the extension without tests or old builds, version stamped.
stage="$(mktemp -d)"
mkdir -p "$stage/ami"
(cd "$root/extension" && tar --exclude=./test --exclude=./dist -cf - .) | (cd "$stage/ami" && tar -xf -)
python3 - "$stage/ami/manifest.json" "$version" <<'PY'
import json, sys
p, v = sys.argv[1], sys.argv[2]
m = json.load(open(p))
m["version"] = v
json.dump(m, open(p, "w"), indent=2)
PY

# Chrome: the key fixes the extension ID across builds. Keep it out of git.
key="$cfg/extension-key.pem"
if [ ! -f "$key" ]; then
  (umask 077 && openssl genrsa 2048 2>/dev/null | openssl pkcs8 -topk8 -nocrypt -out "$key")
  echo "created signing key $key"
fi
profile="$(mktemp -d)"
google-chrome --headless=new --user-data-dir="$profile" --no-message-box \
  --pack-extension="$stage/ami" --pack-extension-key="$key" >/dev/null 2>&1 || true
[ -f "$stage/ami.crx" ] || { echo "CRX packing failed" >&2; exit 1; }
cp "$stage/ami.crx" "$out/ami.crx"
id="$(openssl pkey -in "$key" -pubout -outform DER 2>/dev/null | sha256sum | head -c32 | tr '0-9a-f' 'a-p')"
echo "$id" > "$out/chrome-id"
cat > "$out/updates.xml" <<XML
<?xml version='1.0' encoding='UTF-8'?>
<gupdate xmlns='http://www.google.com/update2/response' protocol='2.0'>
  <app appid='$id'>
    <updatecheck codebase='$url/ext/ami.crx' version='$version' />
  </app>
</gupdate>
XML
echo "$version" > "$out/version"
echo "Chrome:  ami $version, extension id $id"

# Firefox: needs Mozilla signing. Credentials are read from .env without executing it.
envfile="$root/.env"
amo_key="$(grep -E '^AMO_JWT_ISSUER=' "$envfile" 2>/dev/null | cut -d= -f2- || true)"
amo_secret="$(grep -E '^AMO_JWT_SECRET=' "$envfile" 2>/dev/null | cut -d= -f2- || true)"
if [ -n "$amo_key" ] && [ -n "$amo_secret" ]; then
  WEB_EXT_API_KEY="$amo_key" WEB_EXT_API_SECRET="$amo_secret" \
    npx -y web-ext@10.7.0 sign --source-dir "$stage/ami" --artifacts-dir "$stage/xpi" --channel unlisted
  xpi="$(ls -t "$stage"/xpi/*.xpi | head -1)"
  cp "$xpi" "$out/ami.xpi"
  echo "Firefox: signed $(basename "$xpi")"
else
  echo "Firefox: skipped (add AMO_JWT_ISSUER and AMO_JWT_SECRET to .env to sign)"
fi
echo "Published to $out (served at $url/ext/)"
