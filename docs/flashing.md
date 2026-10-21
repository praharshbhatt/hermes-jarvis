# Flashing the device

hermes-jarvis uses its own firmware for the Home Assistant Voice Preview Edition. It is the stock firmware plus a few
changes (listed below), so the device keeps working as a voice satellite. It just talks to hermes-jarvis instead of Home
Assistant.

## What the firmware changes

- **No secrets in the image.** The device is built with API encryption but without a key. Until a client gives it one, it
  accepts a plaintext connection on your local network. Once `hermes-jarvis adopt` has set a key, the device accepts only
  that key, and only a factory reset or a full erase removes it. Home Assistant adopts ESPHome devices the same way.
- **Wi-Fi after flashing.** You enter your Wi-Fi name and password in the browser right after flashing (Improv over USB), or
  from a phone over Bluetooth (Improv, authorized with the center button).
- **The stop word works while the device is talking**, and the device reports it so hermes-jarvis can drop the rest of the
  reply.
- Everything else is upstream's: the wake words ("Hey Jarvis", "Okay Nabu", "Hey Mycroft"), echo cancellation, the LED ring,
  the mute switch and the volume dial.

The firmware config is `firmware/hermes-jarvis.yaml`. It layers those changes on a pinned copy of upstream's config in
`firmware/upstream/` (the same ESPHome version, 2025.7.2).

## Flash from the browser

1. Use Chrome or Edge on a desktop computer. Other browsers can't talk to USB devices.
2. Open the flasher page of this project (GitHub Pages: `https://praharshbhatt.github.io/hermes-jarvis/`).
3. Plug the device into the computer's USB port with a data cable. A charge-only cable won't work.
4. Click **Install**, choose the device's serial port, and confirm. Tick "Erase device" only if you want to wipe it, which you
   need to do if something else already adopted it.
5. When prompted, enter your Wi-Fi name and password. The device reboots and joins your network.
6. On the machine that runs hermes-jarvis, run `hermes-jarvis adopt`.

If the device was set up with Home Assistant, remove it there first, or disable the ESPHome integration entry for it.
Otherwise Home Assistant keeps reconnecting, and a device only talks to one voice client at a time.

## Build it yourself

You need Python 3.11 or newer **with `venv` and `pip` included** (on Debian and Ubuntu, `apt install python3-venv`; with `uv`,
use a managed Python), and about 4 GB of disk for the toolchain.

```sh
python3 -m venv .venv-fw && . .venv-fw/bin/activate
pip install "esphome==2025.7.2"
cd firmware
esphome compile hermes-jarvis.yaml
esphome run hermes-jarvis.yaml --device /dev/ttyACM0     # flash over USB
```

The first build downloads the toolchain and takes several minutes. ESPHome is pinned to 2025.7.2 because the vendored Voice
PE configuration was written for that version. Newer versions need the configuration updated first.

**Baking in Wi-Fi.** If you'd rather not use the browser step, add a local file next to `hermes-jarvis.yaml`, for example
`firmware/local.yaml`:

```yaml
packages:
  hermes-jarvis: !include hermes-jarvis.yaml
wifi:
  ssid: "My network"
  password: "secret"
```

Build that file instead, and don't commit it.

**Different wake words.** Add models in your local file. They are added to the stock ones:

```yaml
micro_wake_word:
  models:
    - model: https://example.com/my_wake_word.json
      id: my_wake_word
```

To drop stock models, edit your own copy of `firmware/upstream/home-assistant-voice.yaml`. More in [wake words](wake-words.md).

## Updating

You can update over Wi-Fi from a build with `esphome upload hermes-jarvis.yaml --device <ip>`, or flash again from the
browser. Settings stored on the device (Wi-Fi, the key) normally survive a re-flash without erasing. If the device stops
connecting afterwards, flash with "Erase device" and adopt it again. New releases are announced in the
[changelog](../CHANGELOG.md).

## Going back to the stock firmware

Use the official installer at <https://esphome.github.io/home-assistant-voice-pe/> and tick "Erase device". Then set the
device up with Home Assistant as usual.

## Troubleshooting

| Symptom | Fix |
|---|---|
| No serial port shows up | Use a data cable. On Linux, add yourself to the `dialout` group and log in again. Flashing normally needs no button presses; if the device isn't recognized, see the Home Assistant Voice PE documentation for its download mode |
| Flashing fails halfway | Retry with "Erase device" ticked, and a different USB port |
| Wi-Fi prompt never appears | Reload the page and click Install again, or provision over Bluetooth from a phone (Improv) |
| `hermes-jarvis adopt` finds nothing | The device must be on the same network and subnet, and mDNS must work. Pass `--host <ip>` |
| `adopt` says the device already has a key | Another install or Home Assistant adopted it. Flash again with "Erase device", or set `ESPHOME_API_KEY` |
| After re-flashing, `doctor` says the key does not match | Run `hermes-jarvis adopt` again; the erase removed the old key |
