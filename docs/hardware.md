# Hardware

## Tested: Home Assistant Voice Preview Edition

The [Voice PE](https://www.home-assistant.io/voice-pe/) has an ESP32-S3, dual microphones with an XMOS audio front end for
echo cancellation, a speaker, a 12-LED ring, a mute switch and a volume dial. The firmware in `firmware/` is built for it,
and hermes-jarvis is developed against it.

## What the bridge needs from a device

hermes-jarvis works with any **ESPHome** device that offers all of these:

- the `voice_assistant` component with audio over the API (not only a separate UDP stream)
- a `media_player` that can play an announcement from an HTTP URL (WAV)
- the usual voice-assistant events, so the LED ring or status light can follow along

For the best experience it should also have:

- on-device wake word (`micro_wake_word`) with a "stop" model, and the "Stop word" event from `firmware/hermes-jarvis.yaml`.
  Without the event, saying stop still silences the speaker, but the bridge keeps its queued sentences.
- support for the "announce, then start a conversation" command, which follow-up questions use

`hermes-jarvis doctor` checks each of these against the connected device and tells you which ones are missing.

Other ESPHome voice satellites, such as builds based on the ESP32-S3-BOX-3 or the M5Stack Atom Echo, should connect but are
**untested**. Reports and patches for other hardware are welcome.

## Not supported

- **Timers and Home Assistant device control.** Voice PE timers are driven by Home Assistant's intents. Without it, "set a
  timer" is just a request to your agent, which can use its own tools for reminders.
- **Using the device with Home Assistant and hermes-jarvis at the same time.** A device serves one voice client.

## The computer that runs hermes-jarvis

Any always-on machine on the same network will do, CPU only. Piper runs faster than real time on a single core of a modern
CPU, and that's fast enough on a Raspberry Pi 4-class board and a typical NAS. Local speech to text (faster-whisper) needs
more. `small.en` is comfortable on a recent desktop-class CPU. On small boards, use `base.en` or `tiny.en`, or a cloud
provider.
