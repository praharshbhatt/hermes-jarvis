# Changelog

## 0.1.0

First public release.

- Voice bridge for the Home Assistant Voice PE over the ESPHome API: wake word on the device, end-of-speech detection,
  speech to text, a brain, Piper text to speech, played back sentence by sentence.
- Brains: Hermes agent (profiles, resumable sessions, tool progress) and any OpenAI-compatible endpoint.
- Speech to text: ElevenLabs, Deepgram, OpenAI-compatible, and fully local faster-whisper.
- The speak protocol: spoken text in `<speak>` tags, details stay in the chat; quick acknowledgements.
- Conversation routing: session window, then an optional Jev decision over recent conversation titles and profile descriptions.
- Long tool-using turns say a short "still working" line every `progress_every_s` (default 15 s, 0 = off).
- Stop word while speaking (also cuts off a clip already sent to the device); listening again by itself after a question.
- Firmware with key-less API encryption, Wi-Fi provisioning after flashing, and the stop-word changes; web flasher.
- `hermes-jarvis` command: `run`, `doctor`, `discover`, `adopt`, `device`, `voices`, `init`, `say`, `ask`.
- Web UI (Next.js, served by the service): sign-in with server-side sessions, a live core that animates from the pipeline, a
  guided setup (brain, speech to text, voice preview on the device, device adoption, wake word, live test), settings,
  profiles, device controls, router test, recent turns and settings history. Strict CSP, CSRF protection, lockout.
