<div align="center">

<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/hero.svg" alt="hermes-jarvis: your AI agent, by voice" width="100%">

<br>

[![CI](https://github.com/praharshbhatt/hermes-jarvis/actions/workflows/ci.yml/badge.svg)](https://github.com/praharshbhatt/hermes-jarvis/actions/workflows/ci.yml)
[![License: GPL-3.0](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776ab.svg)](pyproject.toml)
[![Home Assistant Voice PE](https://img.shields.io/badge/hardware-Voice%20PE-18bcf2.svg)](docs/hardware.md)

**[Quick start](#quick-start)** · **[How it works](#how-it-works)** · **[Docs](#documentation)** · **[FAQ](#faq)** · **[Troubleshooting](docs/troubleshooting.md)**

<br>

[![Watch the demo on YouTube](https://img.youtube.com/vi/h1A4fgpf1qg/maxresdefault.jpg)](https://youtu.be/h1A4fgpf1qg)

**[▶ Watch the 6-minute demo](https://youtu.be/h1A4fgpf1qg)**: guided setup, live voice turns with tools, follow-up questions and the stop word.

</div>

---

**hermes-jarvis turns a [Home Assistant Voice Preview Edition](https://www.home-assistant.io/voice-pe/) into a speech-first
assistant for your own AI agent.** Say "Hey Jarvis", ask for something, and the agent that already knows your notes, calendar
and tools answers out loud, in a calm British voice, while it is still working on the rest. It is built for the
[Hermes agent](https://hermes-agent.nousresearch.com) (an open-source, self-hosted AI agent that uses tools and keeps memory)
and works with any OpenAI-compatible model, including a fully local one.

It runs on your own machine or NAS. Home Assistant is not involved.

> Not affiliated with Marvel, Disney, Nous Research, Nabu Casa or Home Assistant. "JARVIS" is a fictional character's name;
> this project ships no actor's voice and no studio assets ([voices](docs/voices.md)).

## What it is like to use

<div align="center">
<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/turn-timeline.svg" alt="Timeline of one spoken turn: you speak, a quick acknowledgement plays, then the agent's answer is spoken sentence by sentence" width="100%">
</div>

An example exchange (timings are typical, not guaranteed):

```text
you      "Hey Jarvis, what's the status of the Acme invoice?"
         (the ring lights up while you speak and thinks while it works)
 2.5 s   JARVIS  "One moment, sir."
 3.4 s   JARVIS  "Checking the finance folder."            <- the agent's own line, before its tool call
 9.8 s   JARVIS  "The October invoice was sent on the ninth and is still unpaid. It is due on the twenty-third."
 ...     JARVIS  "Shall I draft a reminder to them?"        <- ends in a question: the device listens, no wake word
you      "Yes, please."
         (and "stop" cuts it off at any point)
```

Agents think before they answer, call tools, and read your files. That is why they are useful, and it is why a normal voice
assistant feels broken when you put one behind it: you ask, and then there is a minute of silence. hermes-jarvis is the layer
that makes an agent comfortable to talk to.

## Features

- **Answers start while the agent is still working.** The reply is spoken sentence by sentence as it is written. If the agent
  is slow to begin, a short acknowledgement ("One moment, sir.") plays first, and the agent announces what it is doing before
  each tool call ("Checking your calendar").
- **It talks like a person, not a terminal.** The agent is told you are listening, so it speaks in short sentences and never
  reads out code, links or tables. Those stay in the chat, complete, for when you are back at your desk.
- **You can interrupt.** Say "stop" while it talks and it goes quiet at once, even when a long job is still running in the
  background.
- **It listens when it needs an answer.** If the agent asks you a question, the device starts listening again by itself. No
  second "Hey Jarvis".
- **It knows which conversation you are in.** Follow-ups continue the same chat. After a pause, a small fast model matches your
  request to the right earlier conversation and the right agent profile (personal, work, ...).
- **Yours, end to end.** Self-hosted. Choose the brain, the speech-to-text service (or run Whisper locally), and the voice.
  This software sends nothing before the wake word, and the [privacy page](docs/security-privacy.md) lists exactly what goes where.
- **No Home Assistant required, no secrets in the firmware.** A one-click web flasher, then `hermes-jarvis adopt` gives your
  device its own encryption key.
- **A tuning UI and a doctor.** An admin page for prompts, speed, thresholds and the device's own controls; `hermes-jarvis
  doctor` checks the whole setup and says what to fix.

## Quick start

**You need:** a [Voice PE](https://www.home-assistant.io/voice-pe/) (sold by Home Assistant), a machine that stays on (a Raspberry
Pi 4, a NAS or a mini PC is plenty, no GPU) with Python 3.11+ or Docker, and a brain: your Hermes agent, or Ollama or OpenAI to
try it. Speech to text needs an ElevenLabs, Deepgram or OpenAI key, **or nothing at all** with the local preset below.

**1. Flash the device**: open the [web flasher](docs/flashing.md) in Chrome or Edge, plug the device in, click Install, enter
your Wi-Fi. A few minutes, no tools.

**2. Install and configure**

```sh
pip install hermes-jarvis          # or: pip install . from a clone, or the Docker image
mkdir jarvis && cd jarvis
hermes-jarvis init                 # writes config.yaml and .env
```

Put your keys in `.env` (for Hermes, its `API_SERVER_KEY` goes in as `HERMES_API_KEY`), and point `config.yaml` at your brain
and speech-to-text provider. **No accounts at all?** `hermes-jarvis init --preset local` sets up Ollama and local Whisper instead.

**3. Adopt, check, run**

```sh
hermes-jarvis adopt                # gives the device its private encryption key
hermes-jarvis doctor               # every line should say ok
hermes-jarvis run
```

Say **"Hey Jarvis"**. The [quick start guide](docs/quickstart.md) walks through each step, and Docker users go to
[installation](docs/installation.md#docker).

## Works with

| | Options | |
|---|---|---|
| **Brain** | **[Hermes agent](docs/hermes-setup.md)**: profiles, resumable conversations, tool progress | tested end to end |
| | **Any OpenAI-compatible API**: Ollama, OpenAI, LM Studio, vLLM, OpenRouter | tested with fakes |
| **Speech to text** | ElevenLabs Scribe, Deepgram Nova | tested end to end |
| | OpenAI or a self-hosted Whisper server | tested with fakes |
| | Local `faster-whisper`: audio never leaves your machine | not yet tested on a device |
| **Voice** | [Piper](https://github.com/OHF-Voice/piper1-gpl), CPU only, faster than real time. Default `en_GB-alan-medium`; any Piper voice works | tested end to end |
| **Device** | Home Assistant Voice Preview Edition | tested end to end |
| | Other ESPHome voice satellites | [untested](docs/hardware.md) |

*Tested end to end* = run through a real device and real services. *Tested with fakes* = covered by automated tests only.

## How it works

<div align="center">
<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/architecture.svg" alt="Architecture: the voice device talks to hermes-jarvis, which talks to the brain and the speech-to-text service" width="100%">
</div>

The device keeps the wake word and the audio hardware. hermes-jarvis takes the place Home Assistant normally has: it connects to
the device over the ESPHome API, detects when you stop speaking, turns your voice into text, asks the brain, and plays the
reply back through the device's speaker, a sentence at a time. Because replies are played as announcements rather than as one
pipeline response, the device stays free for the wake word and the stop word while a long job runs.
The full story is in [architecture](docs/architecture.md).

## Web UI

A sign-in page, a live core that reacts to the voice pipeline, a guided setup, and every setting. Changes apply at once and
are logged.

<div align="center">
<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/ui-core.png" alt="Web UI: the live core, feed and readouts" width="100%">
<br>
<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/ui-login.png" alt="Web UI: sign-in" width="49%">
<img src="https://raw.githubusercontent.com/praharshbhatt/hermes-jarvis/main/docs/images/ui-setup.png" alt="Web UI: the guided setup, adopting the device" width="49%">
</div>

Set `ADMIN_PASSWORD` to turn it on; it listens on localhost unless you say otherwise. Sessions are server-side, forms are
CSRF-protected and the page ships a strict Content-Security-Policy ([security](docs/security-privacy.md#the-web-ui)). To try
it without any hardware, run `scripts/admin_demo.py`.

## Commands

| | |
|---|---|
| `hermes-jarvis init [--preset local]` | Write a starter `config.yaml` and `.env` |
| `hermes-jarvis run` | Start the voice bridge |
| `hermes-jarvis doctor` | Check the setup and say what to fix |
| `hermes-jarvis discover` · `adopt` | Find devices on the network; give a freshly flashed one its private key |
| `hermes-jarvis device list` / `set` / `logs` | Read and change the device's controls (wake word sensitivity, mute, ...), read its log |
| `hermes-jarvis say "..."` / `ask "..."` | Test the speaker and the brain on their own |
| `hermes-jarvis voices list` / `download` | Speech voices |

## FAQ

<details>
<summary><b>Do I need Home Assistant?</b></summary>

No. The Voice PE is an ESPHome device; hermes-jarvis talks to it directly. (A device serves one voice client at a time, so it
cannot be used by Home Assistant and hermes-jarvis together.)
</details>

<details>
<summary><b>Isn't this what Home Assistant's own voice assistant does?</b></summary>

Partly. If you mostly want to switch lights and ask short questions, Home Assistant's voice pipeline is the right tool and the
better integrated one. hermes-jarvis is for when the thing you talk to is an *agent*: something that takes time, uses tools,
remembers earlier conversations, and may need to ask you a question back.
</details>

<details>
<summary><b>Can it run fully offline?</b></summary>

Yes: Ollama (or another local model) as the brain, local Whisper for speech to text, and Piper for speech. See
`hermes-jarvis init --preset local`. The wake word already runs on the device.
</details>

<details>
<summary><b>What does it cost?</b></summary>

The software is free. You pay for what you choose to use: the Voice PE, and any cloud speech-to-text or model account. A
fully local setup costs nothing beyond hardware.
</details>

<details>
<summary><b>Which brain should I use?</b></summary>

One that can follow the short voice instruction it is sent every turn (put the spoken answer in `<speak>` tags, keep code
and links outside). Capable models do this reliably. For something that can *do* things, put an agent such as Hermes behind it.
</details>

<details>
<summary><b>The wake word fires on my TV, or misses me.</b></summary>

Start with the device's "Wake word sensitivity" (`hermes-jarvis device set "Wake word sensitivity" "Slightly sensitive"`),
then see [wake words](docs/wake-words.md).
</details>

<details>
<summary><b>Other languages?</b></summary>

Speech to text, the voice and the brain each decide. Piper has voices in many languages and the speech-to-text providers
support many more. The stock wake words are English.
</details>

<details>
<summary><b>What does it send to the cloud?</b></summary>

Only what you configure: your voice goes to your speech-to-text provider (unless you use local Whisper), and the text goes to
your brain. This software sends nothing before the wake word, which the device detects locally. Details: [security and privacy](docs/security-privacy.md).
</details>

## Status and limits

hermes-jarvis is young (0.1). It grew out of a setup the author uses every day (one Voice PE, Hermes, ElevenLabs); this release
is that code, generalized and tidied for others, with the firmware rebuilt as a one-click flash. The pieces marked "tested on
hardware" above have run on a real device; the rest is covered by automated tests. Things to know before you start:

- **Home Assistant features are not included**: no Voice PE timers, no house control (your agent can have its own tools for
  those).
- **Wake words are on-device models** and can false-trigger on TV or music. There are knobs and a path to training your own;
  see [wake words](docs/wake-words.md).
- **Hardware other than the Voice PE is untested**, and so are the less common providers in the table above. Reports are
  welcome.
- **The web UI is plain HTTP.** Keep it on a trusted network or behind TLS.

## Documentation

| | |
|---|---|
| [Quick start](docs/quickstart.md) | From a boxed device to your first spoken answer |
| [Installation](docs/installation.md) | pip, Docker, a NAS, running as a service |
| [Flashing the device](docs/flashing.md) | Web flasher, building from source, updating, going back to stock |
| [Configuration](docs/configuration.md) | Every setting, and what the web UI controls |
| [Hermes setup](docs/hermes-setup.md) | API key, profiles, the JARVIS persona, conversations |
| [Brains, speech to text, voices](docs/providers.md) · [Voices](docs/voices.md) | Choosing and configuring each piece |
| [Architecture](docs/architecture.md) · [Design notes](docs/design-notes.md) | How it works and why it is built this way |
| [Wake words](docs/wake-words.md) | The stock models, tuning, training your own |
| [Troubleshooting](docs/troubleshooting.md) | Common problems and their fixes |
| [Security and privacy](docs/security-privacy.md) | What leaves your network, and how the web UI is protected |
| [Hardware](docs/hardware.md) | Supported devices and what the bridge needs from them |

## Contributing

Bug reports, hardware reports and pull requests are welcome; start with [CONTRIBUTING.md](CONTRIBUTING.md). When something
breaks, run `hermes-jarvis doctor` and include its output in the issue. Please report security problems privately
([SECURITY.md](SECURITY.md)).

## Acknowledgements

Built on the shoulders of [ESPHome](https://esphome.io) and the
[Home Assistant Voice Preview Edition](https://github.com/esphome/home-assistant-voice-pe) firmware,
[Piper](https://github.com/OHF-Voice/piper1-gpl) for speech, [microWakeWord](https://github.com/kahrendt/microWakeWord) for the
on-device wake word, [Silero VAD](https://github.com/snakers4/silero-vad) for end-of-speech detection, and the
[Hermes agent](https://hermes-agent.nousresearch.com). Third-party licenses are in [NOTICE](NOTICE).

## License

GPL-3.0-or-later, see [LICENSE](LICENSE). The Piper engine this project uses is GPL-3.0, and the combined work follows it.
