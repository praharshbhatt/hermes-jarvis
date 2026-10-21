# Quick start

This takes you from a boxed Voice PE to your first spoken answer in about 20 minutes.

## What you need

- A **[Home Assistant Voice Preview Edition](https://www.home-assistant.io/voice-pe/)**. Other ESPHome voice devices may
  work: see [hardware](hardware.md).
- A computer or NAS that stays on and shares a network with the device. It can run Linux, macOS or Windows with **Python 3.11
  or newer**, or anything that runs Docker. You don't need a GPU.
- A **brain**: the [Hermes agent](https://hermes-agent.nousresearch.com) (an open-source, self-hosted agent runtime with
  tools, memory and an OpenAI-compatible API), or, for a first try, any OpenAI-compatible endpoint such as
  [Ollama](https://ollama.com).
- **Speech to text**: an account with ElevenLabs, Deepgram or OpenAI, *or* the fully local option, which needs no account
  ([providers](providers.md)).

If you'd rather not open any cloud account, use the **local preset** below: Ollama and local Whisper.

## 1. Flash the device

Open the [web flasher](flashing.md) in Chrome or Edge, plug the device into your computer with USB, click the button, pick
the serial port, and enter your Wi-Fi name and password when asked. This replaces the stock firmware, and you can go back
([flashing](flashing.md#going-back-to-the-stock-firmware)).

If you set the device up with Home Assistant before, remove it there first, or HA will keep trying to take it back.

## 2. Install

```sh
pip install hermes-jarvis          # or, from a clone of this repository: pip install .
```

Or use Docker: [installation](installation.md). Fully local speech to text needs `pip install 'hermes-jarvis[local-stt]'`.

## 3. Configure

```sh
mkdir jarvis && cd jarvis
hermes-jarvis init                    # Hermes (or any API) plus a cloud speech-to-text service
# or, with no accounts at all (Ollama + local Whisper):
hermes-jarvis init --preset local
```

This writes `config.yaml` and `.env`. Open both:

- **`.env`** holds your keys. For Hermes, put the key you set as `API_SERVER_KEY` in Hermes into `.env` **as
  `HERMES_API_KEY`**, and add your speech-to-text key (`ELEVENLABS_API_KEY`, `DEEPGRAM_API_KEY` or `OPENAI_API_KEY`).
  `init` has already generated an admin password. Details: [Hermes setup](hermes-setup.md).
- **`config.yaml`** needs `brain.base_url` (plus `brain.type: openai` and `brain.model` if you aren't using Hermes) and
  `stt.provider`. Every setting is explained in [configuration](configuration.md).

Download the default voice now (about 60 MB), so the first start isn't silent while it downloads:

```sh
hermes-jarvis voices download en_GB-alan-medium
```

## 4. Adopt the device

```sh
hermes-jarvis adopt
```

A freshly flashed device has no encryption key. `adopt` finds it on the network, gives it a random private key, checks that
the key works, and saves it in `data/device.json`. Home Assistant does the same thing when it adds an ESPHome device, and it
happens once. If `adopt` can't find the device, pass its address: `hermes-jarvis adopt --host 192.168.1.50`.

## 5. Check and run

```sh
hermes-jarvis doctor
hermes-jarvis run
```

`doctor` prints one line per check:

```
    ok  Hermes gateway reachable: http://hermes.local:8642/health -> HTTP 200
  warn  router: OPENROUTER_API_KEY not set: conversations are not matched across sessions (optional)
  FAIL  speech to text (elevenlabs): missing: set ELEVENLABS_API_KEY
```

`ok` is good. `warn` is optional or informational (the router, a voice that will download on first start). `FAIL` needs
fixing before things will work, and the line tells you what to do.

Say **"Hey Jarvis"**, wait for the ring to light up, and ask something. The first answer can be slow while the brain warms up.

## 6. Sign in to the web UI

Open <http://127.0.0.1:8650> and sign in as `admin` with the password from `.env`. The first time, a **setup guide** walks you
through checking your brain and speech to text, choosing a voice (it plays on the device so you can hear it), finding and
adopting the device, tuning the wake word, and running a live test where you say "Hey Jarvis" and watch the core react. Each
step runs a real check and explains in plain words how to fix a failure. You can skip steps, and run the guide again from
**Setup**.

The web UI only listens on the machine it runs on. To reach it from another computer, read
[security](security-privacy.md#the-web-ui) first. Put it behind TLS or a VPN rather than just changing `admin.host`.

## If something does not work

Run `hermes-jarvis doctor` and read [troubleshooting](troubleshooting.md). The usual causes are that Home Assistant is still
connected to the device, that the device can't reach the machine running hermes-jarvis on port 8651, or that a key is missing
or misnamed.
