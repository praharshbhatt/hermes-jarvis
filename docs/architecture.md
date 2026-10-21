# Architecture

## The pieces

```
Voice PE (ESP32-S3)                              hermes-jarvis
  wake word on the device ──ESPHome API──▶   adapter (bridge.py)     the role Home Assistant normally plays
  microphone, echo cancel     16 kHz PCM        │
  speaker, LEDs        ◀── clip URLs ──         ├─ vad.py            end of speech (Silero VAD)
                                                ├─ stt/              speech to text
                                                ├─ router.py         which conversation and profile?
                                                ├─ brains/           Hermes or any OpenAI-compatible API
                                                ├─ speak.py          pull <speak> sentences out of the stream
                                                ├─ tts/              Piper text to speech
                                                ├─ speaker.py        queue of clips played on the device
                                                └─ admin.py          settings, router tester, recent turns
```

The Voice PE is an ESPHome device, so it runs an API *server*, and Home Assistant would normally connect to it as a client.
hermes-jarvis takes over that client role. It subscribes to the device's voice stream, receives microphone audio after the
wake word, and sends events back so the LED ring follows along. Replies play through the device's media player: the device
downloads small WAV clips from a tiny HTTP server inside hermes-jarvis.

## One spoken turn

1. **Wake word.** The device detects it and starts streaming 16 kHz audio to the bridge.
2. **End of speech.** The bridge (Silero VAD) waits for about 0.8 s of quiet after you stop.
3. **Speech to text** with the provider you chose.
4. **Routing.** Within the session window, the current conversation just continues. After it, the router matches your
   request to a recent conversation and a profile ([Hermes setup](hermes-setup.md#3-conversations-and-the-router)).
5. **The brain** is called and streams its answer. If it hasn't said anything after `ack_after_s` (default 2.5 s), a
   pre-rendered acknowledgement plays ("One moment, sir."). If a tool-heavy turn then stays silent for `progress_every_s`
   (default 15 s), a short "still working" line plays.
6. **Sentence by sentence.** As soon as the brain finishes a spoken sentence, Piper turns it into a clip (about 0.1 s) and
   queues it on the device. The queue sends the next clip when the media player reports idle.
7. **Follow-up.** If the last sentence is a question and your request was recent, the device starts listening again by
   itself once the reply has played.

The pipeline run closes as soon as the first speech starts, so the device is free for the wake word while a long job is
still running.

## The speak protocol

Most of an agent's reply isn't meant to be heard: code, links, tables, file paths. So on every turn the voice layer sends
the agent a short instruction. Put what should be *spoken* inside `<speak>...</speak>` and write it for the ear: short
sentences, numbers and dates the way you'd say them, nothing that needs to be seen. Put everything else after it as normal
text. The bridge parses the tags as the text streams in. Whatever sits outside them is never read aloud, but it stays in the
agent's conversation, so the full answer is waiting when you sit down at your desk.

The agent is also told to give one short `<speak>` line before it calls a tool ("Checking your calendar"). That is the best
kind of acknowledgement, because it says what is actually happening. If the agent ignores the format entirely, a fallback
reads the first two sentences with code and tables removed, then says "the full details are in your chat".

The instruction says outright that the spoken part must contain the answer itself. Without that, models sometimes put a
one-line intro in the tags and the real answer outside, which sounds like silence.

## Why replies are announcements, not a pipeline response

Home Assistant's own voice pipeline ends with a single text-to-speech URL played as the response, and the run only ends
when it finishes. That works for a one-second answer and fails for an agent: it ties the device up for the whole job and
can't say anything later. hermes-jarvis ends the run when the first speech starts and plays everything as announcements
through the media player. That also makes three things possible:

- **Interrupting.** The stop word and the wake word work during playback and during long jobs.
- **Speaking without being asked.** The same path can deliver a result that finishes minutes later.
- **Asking you a question and listening.** The firmware has an "announce, then start a conversation" command for this.

## Stop

The stock firmware enables its stop-word model only from voice-pipeline events, and those don't happen here. So the
hermes-jarvis firmware turns the model on whenever an announcement is playing and keeps it on across the gaps between clips.
When it fires, the firmware stops the playing clip and raises a "Stop word" event. The bridge then clears its queue and bumps
a generation counter, which drops the rest of that reply, still arriving from the brain. "Stop" means "be quiet": the
agent's job keeps running and its full answer stays in the chat.

## The live view

The pipeline publishes what it is doing to a small in-process event bus: `wake`, `listening`, `speech`, `thinking`,
`speaking`, `stopped`, `followup`, spoken lines, tool progress, routing decisions, and a microphone loudness number. The web
UI subscribes through a session-protected server-sent-events stream and animates its core from it. The stream never carries
audio, and transcript text is replaced by an empty string when `privacy.save_transcripts` is off.

## Constraints

- A device serves one voice client. ESPHome sends voice-assistant messages to the connection that subscribed to the voice
  stream, and accepts voice commands only from it, so Home Assistant and hermes-jarvis can't both serve the same device.
- Everything runs over your local network, using HTTP and the ESPHome API. The device must reach the bridge's port (8651 by
  default), and the bridge must reach the device's port 6053.
- The brain decides what counts as "spoken". Quality depends on the model following the voice instruction, and capable
  models do that reliably.

## Extending it

Brains, speech-to-text providers and voices are small interfaces: see `brains/base.py`, `stt/base.py` and `tts/piper.py`. A
new brain yields events (`session`, `text`, `tool`, `error`, `done`). A new speech-to-text provider turns 16 kHz 16-bit PCM
into text. See [CONTRIBUTING](../CONTRIBUTING.md).
