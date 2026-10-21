#!/usr/bin/env python3
"""Run one full voice turn through the real pipeline with a simulated device, no hardware needed.

  scripts/simulate_turn.py "What is two plus two?"

The request is spoken with Piper, resampled to 16 kHz and fed in as if it came from the device's microphone, so it goes
through the real end-of-speech detection, speech-to-text provider, brain, text to speech and clip queue. The "device" is a
fake that reports media-player states. Needs your keys (config.yaml / .env), and uses your brain and STT account.
"""
import asyncio
import sys

import numpy as np
from aioesphomeapi import MediaPlayerState

from hermes_jarvis import config
from hermes_jarvis.bridge import VoiceBridge
from hermes_jarvis.settings import settings
from hermes_jarvis.speaker import wav_seconds

config.load()


class FakeDevice:
    """Stands in for the aioesphomeapi client: records what the bridge sends and plays clips in (fake) real time."""

    def __init__(self, bridge):
        self.bridge, self.events, self.played = bridge, [], []

    def send_voice_assistant_event(self, ev, data):
        self.events.append(ev.name.replace("VOICE_ASSISTANT_", ""))

    def media_player_command(self, key, media_url=None, announcement=None, **_):
        clip = next(w for u, w in self.bridge.audio._clips.items() if media_url.endswith(u))[0]
        self.played.append(clip)
        dur = wav_seconds(clip, self.bridge.tts.sample_rate)
        loop = asyncio.get_running_loop()
        loop.call_later(0.05, self.bridge.speaker.on_media_state, MediaPlayerState.ANNOUNCING)
        loop.call_later(0.05 + dur / 20, self.bridge.speaker.on_media_state, MediaPlayerState.IDLE)  # 20x speed

    async def send_voice_assistant_announcement_await_response(self, url, timeout, text="", start_conversation=False):
        self.events.append(f"START_CONVERSATION={start_conversation}")
        return type("R", (), {"success": True})()


async def main(text: str) -> None:
    bridge = VoiceBridge()
    bridge.audio.add_wav = bridge.audio.add_wav  # clips are kept in memory; no HTTP server needed here
    dev = FakeDevice(bridge)
    bridge.client, bridge.media_key = dev, 1
    bridge.speaker.start()
    await bridge.speaker.prerender(settings.acks())

    pcm22 = np.frombuffer(b"".join(bridge.tts.synth_pcm(text)), dtype=np.int16).astype(np.float32)
    n = int(len(pcm22) * 16000 / bridge.tts.sample_rate)
    pcm16 = np.interp(np.linspace(0, len(pcm22) - 1, n), np.arange(len(pcm22)), pcm22).astype(np.int16).tobytes()
    pcm16 = b"\0" * 6400 + pcm16 + b"\0" * 2 * 16000 * 2  # lead-in, the request, then two seconds of quiet

    print(f"you say: {text!r}")
    await bridge.on_start("sim", 1, None, "hey jarvis")
    for i in range(0, len(pcm16), 640):
        await bridge.on_audio(pcm16[i:i + 640])
        await asyncio.sleep(0)
    await asyncio.wait_for(bridge._reply_task, timeout=300)
    await asyncio.wait_for(bridge.speaker.drain(), timeout=300)
    print("device events :", " > ".join(dev.events))
    print(f"clips played  : {len(dev.played)}")
    from hermes_jarvis import turnlog
    t = turnlog.recent(1)[0]
    print(f"route         : {t['route']['reason']} -> profile {t['profile']}, first speech {t['first_speech_s']} s, total {t['total_s']} s")
    print(f"heard         : {t['text']!r}")
    await bridge.brain.close()
    await bridge.router.close()


asyncio.run(main(" ".join(sys.argv[1:]) or "In one short sentence, what is two plus two?"))
