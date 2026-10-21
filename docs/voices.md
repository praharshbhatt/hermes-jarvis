# Voices

## The default

`en_GB-alan-medium` is a British English male Piper voice. hermes-jarvis downloads it from the
[rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices) repository the first time you run it, and nothing is
bundled with this project. Each voice has its own license. Before you use one beyond personal use, read the `MODEL_CARD` file
next to it in that repository.

```sh
hermes-jarvis voices list                      # the built-in shortlist
hermes-jarvis voices download en_US-ryan-medium
hermes-jarvis say "Good evening. All systems are running normally."
```

Set `tts.voice` in `config.yaml` to a name from the list, or to the path of **any Piper `.onnx` voice** (its `.onnx.json` must
sit next to it). The Piper catalog covers many languages. Pick one that matches `stt.language` and your agent's language.

## Speed and tone

In the web UI, under Voice, `length scale` sets the pace (bigger is slower, and 1.0 is the voice's natural pace). Two noise
settings change how lively the voice sounds. Changes apply immediately and re-render the quick acknowledgements.

## Bringing your own voice

You can train or fine-tune a Piper voice and point `tts.voice` at it. Only train on a voice you have the right to use: your
own, or a speaker who has agreed in writing.

**Don't clone a real person's voice, such as an actor's, to distribute it or to publish a model of it.** This project
includes no such voice and won't accept one. Using one privately is your own call, with legal and ethical questions this
project can't answer for you.

## Why "JARVIS" sounds the way it does here

The persona (calm, British, understated) is text. It comes from the acknowledgement wording in `persona: jarvis` and, in
Hermes, from a `SOUL.md` ([example](../examples/hermes/SOUL-jarvis.md)). The voice is whichever Piper voice you choose.
