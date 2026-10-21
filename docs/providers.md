# Brains, speech to text, and voices

## Brains

Set the brain with `brain.type` in `config.yaml`.

| Type | Use it for | Notes |
|---|---|---|
| `hermes` | The [Hermes agent](https://hermes-agent.nousresearch.com) | Profiles, resumable sessions with titles, tool-progress events. The recommended setup. See [Hermes setup](hermes-setup.md) |
| `openai` | OpenAI, Ollama, LM Studio, vLLM, OpenRouter, anything with `/v1/chat/completions` and streaming | hermes-jarvis keeps the conversation history (saved in `data/`). No profiles and no router. The persona comes from `persona` / `brain.system_prompt` |

An Ollama example:

```yaml
brain:
  type: openai
  base_url: http://localhost:11434/v1
  model: llama3.1
  api_key_env: ""          # Ollama needs no key
```

A small local model answers fast but can't use tools. If you want a JARVIS that does things (calendar, notes, the web, your
own tools), put an agent such as Hermes behind it. The voice layer is the same either way.

## Speech to text

Set the provider with `stt.provider`. Whichever you pick, the request goes out when you finish speaking (this machine detects
the end of speech), so latency is the provider's turnaround time.

| Provider | Where audio goes | Typical speed | Needs |
|---|---|---|---|
| `elevenlabs` (Scribe v2) | ElevenLabs | 0.4 to 0.7 s, best on short phrases | `ELEVENLABS_API_KEY` |
| `deepgram` (Nova-3) | Deepgram | 0.2 to 0.6 s | `DEEPGRAM_API_KEY` |
| `openai` | OpenAI, or your own server with `/audio/transcriptions` | not measured | `OPENAI_API_KEY` (not for self-hosted) |
| `local` (faster-whisper) | Nowhere. Fully local | depends on your CPU and model | `pip install 'hermes-jarvis[local-stt]'` |

The speeds come from about twenty real spoken requests on one setup, so yours will differ. To compare providers on your own
voice and network, set `stt.compare_with` to a second provider. Both run on every request, the main one's text is used, and
both timings and transcripts are logged.

`local` downloads the Whisper model on first use. `small.en` is a good start on a modern CPU, and `base.en` suits a small
board.

## Speech (text to speech)

[Piper](https://github.com/OHF-Voice/piper1-gpl) runs on the CPU, faster than real time. The default voice is
`en_GB-alan-medium`, downloaded on first start. More in [voices](voices.md).

Speech speed, noise and the quick acknowledgements are settings in the web UI.
