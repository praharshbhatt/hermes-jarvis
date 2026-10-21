#!/bin/sh
# Integration test for `hermes-jarvis adopt` without hardware: builds a tiny ESPHome "host" device (a Linux program
# with the same API and key-less encryption as the firmware), runs it, and adopts it. Needs gcc/g++ and an ESPHome
# install (the firmware venv: `uv venv .venv-fw && uv pip install esphome==2025.7.2`).
#
#   scripts/test_adopt_host.sh
set -eu
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ESPHOME="${ESPHOME:-$ROOT/.venv-fw/bin/esphome}"          # override in CI: ESPHOME=esphome HJ=hermes-jarvis PY=python
HJ="${HJ:-$ROOT/.venv/bin/hermes-jarvis}"
PY="${PY:-$ROOT/.venv/bin/python}"
W="$(mktemp -d)"
trap 'kill "$DEV" 2>/dev/null || true; rm -rf "$W" ~/.esphome/prefs/adopt-test* 2>/dev/null || true' EXIT
cd "$W"
printf 'esphome:\n  name: adopt-test\nhost:\nlogger:\napi:\n  encryption:\n' > adopt-test.yaml
"$ESPHOME" compile adopt-test.yaml >/dev/null
.esphome/build/adopt-test/.pioenvs/adopt-test/program >/dev/null 2>&1 &
DEV=$!
sleep 2
export HJ_DATA_DIR="$W/data"
"$HJ" adopt --host 127.0.0.1
test -s "$W/data/device.json"
"$PY" - <<PY
import asyncio, json
from aioesphomeapi import APIClient, RequiresEncryptionAPIError
key = json.load(open("$W/data/device.json"))["key"]
async def main():
    try:
        await APIClient("127.0.0.1", 6053, None).connect(login=True)
        raise SystemExit("plaintext still accepted")
    except RequiresEncryptionAPIError:
        pass
    c = APIClient("127.0.0.1", 6053, None, noise_psk=key)
    await c.connect(login=True)
    await c.disconnect()
asyncio.run(main())
print("adopt integration test passed")
PY
