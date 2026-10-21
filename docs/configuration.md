# Configuration

Settings live in three places, ordered from "set once" to "change while it runs":

| Where | What | How to change |
|---|---|---|
| `.env` | Secrets: API keys, the admin password | Edit the file, restart |
| `config.yaml` | Startup configuration: device, ports, which brain, which speech-to-text, which voice | Edit the file, restart |
| Web UI (`data/settings.json`) | Tunables: speech speed, thresholds, prompts, profiles, acknowledgements | Change in the browser, applies at once |

`hermes-jarvis init` writes a commented `config.yaml` and a `.env` for you. You can also set any `config.yaml` key from the
environment as `HJ_<SECTION>_<KEY>`, for example `HJ_ADMIN_HOST=0.0.0.0` or `HJ_BRAIN_BASE_URL=http://hermes:8642`. The
environment wins over the file. Secrets are never read from `config.yaml`.

## config.yaml

| Key | Default | Meaning |
|---|---|---|
| `data_dir` | `./data` | Settings, session state, downloaded voices, the device key. Relative to the config file |
| `persona` | `jarvis` | `jarvis` or `neutral`: the wording of the quick acknowledgements and, for the `openai` brain, the persona text |
| `user.name` | empty | Your name (only used in the persona text of the `openai` brain) |
| `user.address_as` | `sir` | How short lines address you: `sir`, `ma'am`, `boss`, or empty for none |
| `device.host` | empty | Device address. Empty: use the one saved by `adopt`, or find it by mDNS |
| `device.port` | `6053` | ESPHome API port |
| `device.wake_word` | `hey_jarvis` | The wake word to switch on when the device has none active (a freshly flashed device has none, and Home Assistant is no longer there to pick one). Others: `okay_nabu`, `hey_mycroft`. Empty: leave the device as it is |
| `audio.public_host` | empty | Address the device uses to download speech clips from this machine. Empty: detected |
| `audio.port` | `8651` | Port serving speech clips (the device must be able to reach it) |
| `brain.type` | `hermes` | `hermes` or `openai` ([providers](providers.md)) |
| `brain.base_url` | `http://localhost:8642` | Where the brain is. For `openai`, for example `http://localhost:11434/v1` |
| `brain.model` | `hermes-agent` | Model name sent to the endpoint |
| `brain.api_key_env` | `HERMES_API_KEY` | Name of the environment variable holding the key. Empty for no key |
| `brain.history_messages` | `24` | `openai` only: how many past messages are resent each turn |
| `brain.system_prompt` | empty | `openai` only: persona text. Empty uses the persona preset |
| `stt.provider` | `elevenlabs` | `elevenlabs`, `deepgram`, `openai` or `local` |
| `stt.compare_with` | empty | A second provider, run in parallel and only logged, for comparing accuracy and speed |
| `stt.language` | `en` | Language code |
| `stt.local_model` | `small.en` | faster-whisper model for `local` |
| `stt.openai_model` / `stt.openai_base_url` | `gpt-4o-mini-transcribe` / OpenAI | Model and endpoint for `openai`; point the URL at your own Whisper server if you have one |
| `tts.voice` | `en_GB-alan-medium` | A name from `hermes-jarvis voices list`, or the path to a Piper `.onnx` file |
| `router.enabled` | `true` | Match requests to earlier conversations and profiles (Hermes brain plus `OPENROUTER_API_KEY`) |
| `admin.host` / `admin.port` / `admin.user` | `127.0.0.1` / `8650` / `admin` | The web UI. It is off unless `ADMIN_PASSWORD` (or `ADMIN_PASSWORD_HASH`) is set |
| `admin.session_idle_minutes` / `admin.session_max_hours` | `30` / `12` | When a sign-in ends: after this long idle, or in total |
| `admin.trust_proxy` | `false` | Behind your own TLS reverse proxy: trust `X-Forwarded-Proto` so cookies are `Secure` |
| `admin.allowed_origins` | `[]` | Extra browser origins allowed to make changes (for example `http://localhost:3000` for UI development) |
| `privacy.save_recordings` | `false` | Keep what the microphone heard as WAV files in `data/recordings` |
| `privacy.recordings_keep_days` | `7` | Delete recordings older than this |
| `privacy.save_transcripts` | `true` | Keep recent transcripts for the web UI. When off, only timings and routing are kept |

## .env

| Variable | Used for |
|---|---|
| `ADMIN_PASSWORD` | Web UI login (user from `admin.user`). Without it (or a hash) the web UI is off |
| `ADMIN_PASSWORD_HASH` | A PBKDF2 hash from `hermes-jarvis hash-password`, used instead of the plain password |
| `HERMES_API_KEY` | The brain's key (name set by `brain.api_key_env`) |
| `HERMES_API_KEY_<PROFILE>` | One per extra Hermes profile, for example `HERMES_API_KEY_WORK` |
| `ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY`, `OPENAI_API_KEY` | Speech to text, whichever you chose |
| `OPENROUTER_API_KEY` | The router's decision model (optional) |
| `ESPHOME_API_KEY` | The device's encryption key, if you did not use `adopt` |

## Web UI settings

Sign in to the web UI (default <http://127.0.0.1:8650>). The first sign-in starts the setup guide, and you can run it again
from **Setup**. The **Settings** page has the sections below. Everything there applies at once, and every change is logged in
History. Numeric settings are range-checked, so a speech speed of 0, for example, is refused.

- **Session routing** (Hermes brain): the window in which a conversation just continues (default 5 minutes), how many recent
  conversations the router considers, which conversation sources may be resumed, the router model and its thresholds, and
  the two prompts it is given. The router uses TypeSafe's Jev decision model through OpenRouter's experimental decisions API
  (`router_url`, `router_model` in `data/settings.json`). It is optional; see
  [Hermes setup](hermes-setup.md#3-conversations-and-the-router).
- **Profiles** (Hermes brain): names, descriptions (what the router reads to choose), enabled, and the default.
- **Listening**: how much quiet ends your sentence, and how long the device waits for your first word.
- **Follow-up questions**: whether the device listens again by itself after a question, the recency window, and closing
  phrases like "anything else" that don't need an answer.
- **Voice**: speech speed and noise settings, when to say a quick acknowledgement, what the acknowledgements say, how to
  address you, and the voice-mode prompt sent to the brain on every turn.
- **Router test**: type a sentence and see which profile and conversation it would be routed to. Nothing is spoken and
  nothing is sent to the brain.
- **Device**: the device's own controls (wake word sensitivity, mute, wake sound).
- **Core** (the home page): the live view, readouts, and recent turns with their timings.

## Command line

| Command | |
|---|---|
| `hermes-jarvis init [DIR] [--preset hermes\|local]` | Write a starter `config.yaml` and `.env`. `local` is Ollama plus local Whisper, no accounts |
| `hermes-jarvis run [-v]` | Start the bridge (`-v` for debug logging). Stops cleanly on Ctrl-C or SIGTERM |
| `hermes-jarvis doctor` | Check the setup and say what to fix |
| `hermes-jarvis discover` | List ESPHome devices on the network |
| `hermes-jarvis adopt [--host IP]` | Give a freshly flashed device its private encryption key |
| `hermes-jarvis device list` | The device's controls and their current values |
| `hermes-jarvis device set NAME VALUE` / `device press NAME` | Change a control (wake word sensitivity, mute, wake sound) or press a button |
| `hermes-jarvis device logs [SECONDS]` | Stream the device's log (default 30 seconds) |
| `hermes-jarvis voices list` / `voices download NAME` | Speech voices |
| `hermes-jarvis say "text"` | Speak a line on the device (tests text to speech and the speaker) |
| `hermes-jarvis ask "text"` | Send text to the brain and print what would be spoken (no device needed) |
| `hermes-jarvis hash-password` | Make an `ADMIN_PASSWORD_HASH` value (asks for the password twice) |
| `hermes-jarvis healthcheck` | Exit 0 if a running bridge is healthy (used by the container health check) |

Two global options go before the command: `-c PATH` for a config file other than `./config.yaml`, and `--debug` to show full
tracebacks instead of a one-line error. `HERMES_JARVIS_CONFIG=/path/to/config.yaml` does the same as `-c` (the Docker image
sets it). A config file you name explicitly must exist. A missing default `./config.yaml` just means defaults.

Mistyped settings are reported, not ignored: an unknown key in `config.yaml` is an error, and an unknown `HJ_*` environment
variable produces a warning.
