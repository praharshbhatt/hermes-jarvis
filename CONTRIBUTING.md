# Contributing

Thanks for helping. Issues, hardware reports, docs fixes and pull requests are all welcome.

## Set up

```sh
git clone https://github.com/praharshbhatt/hermes-jarvis && cd hermes-jarvis
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest -q            # no device, no network, no API keys needed
ruff check src tests scripts
```

`uv.lock` pins one known-good set of dependencies for development (`uv sync`); the published package declares only lower bounds.

The tests use fakes (a fake brain, speaker, device controls, and HTTP servers on localhost) so they run anywhere. Please
add one for what you change.

`scripts/test_adopt_host.sh` exercises `hermes-jarvis adopt` end to end against a small ESPHome "host" device built on your
machine (needs gcc and the firmware venv from `firmware/`); run it when you touch `adopt.py` or the firmware's API
settings.

## Code map

```
src/hermes_jarvis/
  bridge.py       the ESPHome adapter and the turn pipeline
  conversation.py one spoken turn: route, ask the brain, speak, decide whether to listen again
  router.py       which conversation and profile (Jev via OpenRouter, optional)
  speak.py        <speak> parser   speaker.py  clip queue on the device   audio_server.py  clip HTTP server
  brains/         hermes.py, openai_compat.py   (interface in base.py)
  stt/            elevenlabs, deepgram, openai_stt, local   (interface in base.py)
  tts/            piper.py, voices.py
  settings.py     runtime settings (web UI)   config.py  startup config
  admin.py        the HTTP API and the static files of the web UI   auth.py  sign-in, sessions, CSRF   events.py  live event stream
  static/app/     the built web UI (committed, so `pip install .` needs no Node)
  discovery.py, adopt.py, devicectl.py, doctor.py, cli.py
webui/            the web UI source (Next.js, TypeScript): see webui/README.md
firmware/         ESPHome overlay, vendored upstream config, web flasher
```

`scripts/make_hero.py` regenerates the animated banner (`docs/images/hero.svg`); `scripts/admin_demo.py` runs the real web UI
and API with made-up data and a fake device, for screenshots and UI work.

## Working on the web UI

The UI is a static Next.js export that the Python service serves, so nothing in `webui/` runs at runtime. You need Node 20.9
or newer only to change it.

```sh
python scripts/admin_demo.py --dev       # the API with fake data and scripted live events
cd webui && npm ci && npm run dev        # http://localhost:3000, proxies /api to the demo
npm run lint && npm run typecheck && npm test
```

Before you open a pull request, run `scripts/build_ui.sh` and **commit the result in `src/hermes_jarvis/static/app/`**. CI warns
when the committed export is out of date, and the release build regenerates it for the published wheel. Rules for the UI:

- **No external assets** (fonts, scripts, images, CDNs): the service sends a strict Content-Security-Policy.
- **No secrets in the browser.** The session is an `HttpOnly` cookie; the CSRF token is the only credential-like value JavaScript holds.
- Respect `prefers-reduced-motion`, keep keyboard focus visible and contrast readable, and make it work down to phone width.
- Screenshots in the docs must come from `scripts/admin_demo.py`, never from a real setup.

## Adding a brain, speech-to-text provider or voice engine

- **Brain**: implement `brains/base.py`'s `Brain`: an async generator `turn()` that yields `session`, `text`, optional `tool`,
  `error`, and `done` events, plus `check()` for `doctor`. Register it in `brains/__init__.py` and document it in
  [providers](docs/providers.md).
- **Speech to text**: a class with `name`, `check()`, and `async transcribe_pcm(pcm)` taking 16 kHz 16-bit mono PCM;
  register it in `stt/__init__.py`.
- Keep secrets in environment variables read with `config.secret()`, never in `config.yaml` or settings.

## Rules for pull requests

- **No secrets, no personal data** in code, tests, docs, logs or screenshots.
- **No voice models, voice samples or recordings of real people.** Voices are downloaded from their upstream sources.
- Keep the defaults generic: nothing in a default may refer to one person, company or setup.
- Say what you tested, on which hardware. If you could not test on a device, say so.
- Firmware changes: say whether you flashed them. The upstream config in `firmware/upstream/` is vendored and pinned; change
  behaviour in `firmware/hermes-jarvis.yaml`, and if you must update the vendored copy, update the pinned commit in
  its header and in `NOTICE`.

## Releases

Tag `vX.Y.Z`. CI builds the firmware, publishes the web flasher to GitHub Pages, attaches the images to the release, pushes
the container image, and builds the wheel with a freshly built web UI. Update `CHANGELOG.md` and the version in `pyproject.toml` and `src/hermes_jarvis/__init__.py` first.
