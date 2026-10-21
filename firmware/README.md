# Firmware

ESPHome firmware for the Home Assistant Voice Preview Edition.

| File | |
|---|---|
| `hermes-jarvis.yaml` | The firmware: upstream's config plus key-less API encryption, Wi-Fi provisioning, and the stop-word changes |
| `upstream/` | Upstream's Voice PE configuration, vendored and pinned to one commit (see its README) |
| `flash/index.html` | Template of the web flasher page; `scripts/make_flash_site.py` turns a build into the site |

**To just flash the device**, use the web flasher: [docs/flashing.md](../docs/flashing.md). To build, change or extend the
firmware, read on.

## Build

Needs Python 3.11+ with `venv` and `pip`, and about 4 GB for the toolchain. ESPHome is pinned to 2025.7.2, the version
the vendored configuration targets.

```sh
python3 -m venv ../.venv-fw && . ../.venv-fw/bin/activate
pip install "esphome==2025.7.2"
esphome config hermes-jarvis.yaml        # validate, a few seconds
esphome compile hermes-jarvis.yaml       # first build takes about five minutes
esphome run hermes-jarvis.yaml --device /dev/ttyACM0
```

The images are in `.esphome/build/hermes-jarvis/.pioenvs/hermes-jarvis/`: `firmware.factory.bin` (what the web flasher
writes, at offset 0) and `firmware.ota.bin` (for over-the-air updates).

## What `hermes-jarvis.yaml` changes

1. `api: encryption:` with no key. Until a client sets one the device accepts a plaintext connection; afterwards it only
   accepts that key. `hermes-jarvis adopt` sets it. No secrets are baked into the image.
2. Wi-Fi provisioning copied from upstream's factory image: Improv over USB (browser) and over Bluetooth (phone, centre button).
3. A **"Stop word" event** that fires when the stop model hears "stop", so the bridge can drop queued speech.
4. The stop model is enabled while anything is announcing (the stock firmware enables it from voice-pipeline events, which
   hermes-jarvis does not use), stays on across the gaps between clips, and goes off 2 s after the last clip.

## Local changes: Wi-Fi, wake words

Create a file next to `hermes-jarvis.yaml` (it is gitignored if you name it `local.yaml`) that includes it and adds to it:

```yaml
packages:
  hermes-jarvis: !include hermes-jarvis.yaml

wifi:
  ssid: "My network"
  password: "secret"

micro_wake_word:
  models:
    - model: https://example.com/my_wake_word.json
      id: my_wake_word
```

and build that file instead. Lists are appended to the stock ones; to remove stock wake words, edit your own copy of
`upstream/home-assistant-voice.yaml`.

## Web flasher

`scripts/make_flash_site.py --version X --factory <firmware.factory.bin> --out site/` writes the page, the
[ESP Web Tools](https://esphome.github.io/esp-web-tools/) manifest and the image. CI does this on every tagged release and
publishes it to GitHub Pages (flashing from the browser needs https).

## Updating the vendored upstream config

1. Pick the new upstream commit and the ESPHome version it targets.
2. Copy `home-assistant-voice.yaml` from that commit over `upstream/home-assistant-voice.yaml`.
3. Re-pin the two moving references: the `external_components` `ref:` and the sound-file URLs (`raw/dev/` -> `raw/<commit>/`),
   and set `refresh: never`. Update the header comment and `NOTICE`.
4. Bump the ESPHome version here, in `.github/workflows/`, and in the docs. Run `esphome config`, compile, and test on a device.

## Testing the adoption flow without hardware

`../scripts/test_adopt_host.sh` builds a small ESPHome "host" device (a Linux program with the same API and key-less
encryption) and runs `hermes-jarvis adopt` against it.
