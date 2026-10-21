# Wake words

The wake word runs **on the device**, using [microWakeWord](https://github.com/kahrendt/microWakeWord) models, which are small
neural networks that run on the ESP32-S3. The firmware ships three stock models and a "stop" model:

| Model | Phrase |
|---|---|
| `hey_jarvis` | "Hey Jarvis" |
| `okay_nabu` | "Okay Nabu" |
| `hey_mycroft` | "Hey Mycroft" |
| `stop` | "Stop" (only active while the device is speaking) |

The device listens only for the wake words you've enabled on it. Models and their detection thresholds are part of the
firmware. To add your own, see [flashing](flashing.md#build-it-yourself).

## False triggers and missed wake words

Small on-device models trade accuracy for size. A loud TV, music, or speech that sounds like the phrase ("Hey Travis", "Hey
service") can trigger them. Here is what you can do, cheapest first:

1. **Change the device's "Wake word sensitivity".** The firmware exposes a select with three levels (slightly, moderately,
   very sensitive) that sets the detection threshold per model. *Slightly* is the strictest. Use `hermes-jarvis device list`
   and `hermes-jarvis device set "Wake word sensitivity" "Slightly sensitive"`, or the Device card in the web UI.
2. **Move the device away from speakers**, and keep its echo cancellation working. The device removes its *own* playback from
   the microphone signal, not other sources.
3. **Mute it** (the hardware switch) when you don't want it listening.
4. **Train a model on your own voice and room.** See below.

hermes-jarvis records nothing by default. With `privacy.save_recordings: true`, it keeps what the microphone heard after each
wake word (including false triggers) as WAV files in `data/recordings`. That is useful as training and test data. Delete the
files when you're done; see [security and privacy](security-privacy.md).

## Training your own

microWakeWord has a [training notebook](https://github.com/kahrendt/microWakeWord). It generates synthetic speech for the
phrase, mixes in background noise and speech, trains a model, and exports a `.tflite` plus a `.json` manifest. Here's what we
learned:

- Synthetic samples alone give a model that fires on near-misses ("Hey Travis"). Add real recordings from your own device,
  and add **hard negatives**: other speech, TV audio, and similar-sounding phrases.
- Check a model offline against real recordings before flashing, for example with the `pymicro-wakeword` package. It gives
  you a per-clip score, so you can see how close real speech gets to the threshold.
- Set `probability_cutoff` and `sliding_window_size` in the manifest, and remember that the firmware's sensitivity select
  overrides the cutoff for the stock models.
