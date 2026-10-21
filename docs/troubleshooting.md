# Troubleshooting

**Start with `hermes-jarvis doctor`.** It checks the config, the keys, the brain, speech to text, the voice, the device
connection, and the address the device downloads speech from, then says what to fix. Add `-v` to `hermes-jarvis run` for
debug logs.

## The device never reacts to the wake word

- **Home Assistant is still connected to it.** A device serves only one voice client. Remove it from Home Assistant, or
  disable the ESPHome integration entry for it. This is the most common cause.
- The bridge isn't running, or `doctor` shows the device connection failing. Check that `hermes-jarvis run` is up.
- The wake word isn't firing, meaning the ring doesn't light when you say it. See [wake words](wake-words.md).
- The mute switch is on (red dots on the ring).
- The ring twinkles red. The device isn't connected to hermes-jarvis: the bridge isn't running, the key is wrong, or another
  client has the device.
- After a device reboot the bridge reconnects within a few seconds. If it doesn't, restart the bridge.

## "Connection requires encryption" / "the encryption key does not match"

Either the device has a key we don't have, or we have one it doesn't. Run `hermes-jarvis adopt`. If Home Assistant or another
install adopted the device, either set `ESPHOME_API_KEY` to that key or flash the device again with "Erase device".

## It hears me but never answers, or answers with silence

- `doctor` and the log show which stage failed. Look for `heard=` (speech to text worked) and `first speech` (the brain
  answered). If nothing follows `heard=`, the brain is unreachable or its key is wrong.
- **Hermes: "Invalid gateway API key".** The `.env` file in Hermes' data directory wins over the container's environment. See
  [Hermes setup](hermes-setup.md#1-turn-on-the-api-server-and-choose-a-key).
- **Hermes is slow to answer after a restart.** It can take minutes to come back. Try `hermes-jarvis ask "hello"`.
- The model ignores the speak format, and the reply is a trimmed fallback ("the full details are in your chat"). Use a more
  capable model, or edit the voice-mode prompt in the web UI.

## It answers, but I hear nothing

- The device can't download the speech clips. `doctor` prints the address it uses (`http://<ip>:8651`), so open it from
  another machine on the network. Then fix `audio.public_host`, a firewall, or Docker networking
  ([installation](installation.md#without-host-networking)).
- `hermes-jarvis say "test"` plays a line without the brain. If that's silent too, the problem is the audio path, not the
  brain.
- Check the volume with the device's dial.

## It cuts itself off, or two voices overlap

Two things are talking to the same device: another hermes-jarvis, a script, or Home Assistant. Only one should.

## Saying "stop" does nothing

- The firmware lacks the stop word event (an older or stock firmware), and `doctor` warns "stop word support". Flash the
  hermes-jarvis firmware.
- The device has to hear the stop word over its own speech. Lower the volume a little, or say it closer and clearer. The
  device removes its own playback from the microphone signal, but a loud reply leaves less room.

## The wake word fires on the TV, or misses me

See [wake words](wake-words.md).

## It does not start listening after a question

- Only a reply that *ends* with a question mark triggers it, and only within the follow-up window after your request.
  Closing questions like "anything else?" are skipped on purpose. You can change all of this in the web UI under Follow-up
  questions.
- "Stop" cancels the follow-up on purpose.
- Try the web UI's "Test: make the device listen now" button.

## It will not start

`hermes-jarvis run` prints one line starting with `error:` for problems you can fix yourself. Add `--debug` before the command
for the full traceback.

- **"cannot listen on port 8651"** or **"cannot start the web UI"**: something else has the port, usually another
  hermes-jarvis that is still running. Stop it, or change `audio.port` / `admin.port`.
- **"could not load the speech voice"**: the first-run voice download failed (no network, or a typo in `tts.voice`). Run
  `hermes-jarvis voices download en_GB-alan-medium`, or point `tts.voice` at a `.onnx` file.
- **"unknown config key"**: `config.yaml` has a typo, and the message names the key. A misspelled `HJ_*` environment variable
  shows up as a warning at startup.
- **"config file not found"**: the path you gave with `-c` or `HERMES_JARVIS_CONFIG` doesn't exist.

## The web UI says "too many failed logins"

Ten wrong passwords from one address lock that address out for five minutes (a browser asking for the password doesn't
count). Wait, or restart hermes-jarvis.

## Docker

- No device found: the default compose file uses host networking, which mDNS needs. Without it, set `HJ_DEVICE_HOST` and
  `HJ_AUDIO_PUBLIC_HOST`. Docker Desktop on macOS and Windows has no host networking.
- `hermes-jarvis say` can't work from inside a container without host networking. It serves its clip on the port after
  `audio.port`, and that port isn't published. Use `ask` to test the brain, or run `say` on the host.
- Web UI not reachable: with host networking it's on the host's port 8650 and bound to `127.0.0.1` by default. See
  [security and privacy](security-privacy.md#the-web-ui).

## Opening the device's serial port resets it

If you open the device's serial port while hermes-jarvis is running, the device reboots and the bridge has to reconnect. Read
the device's log through the API instead with `hermes-jarvis device logs 30` (30 seconds of it), or use the bridge's own log.

## Still stuck

Open an issue with the output of `hermes-jarvis doctor` and the relevant part of `hermes-jarvis run -v`. Remove API keys and
anything private first.
