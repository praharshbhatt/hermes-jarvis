"""End-of-speech detection on the 16 kHz 16-bit mono stream from the device (Silero VAD)."""
from pysilero_vad import SileroVoiceActivityDetector

CHUNK_BYTES = SileroVoiceActivityDetector.chunk_bytes()  # 512 samples = 32 ms
CHUNK_SECONDS = 0.032


class Endpointer:
    """Feed raw PCM; get 'speech_start' and 'speech_end' events.

    speech_end fires after `silence_s` of quiet once speech has started. `no_speech_s` bounds the wait
    for the first word and `max_s` bounds the whole utterance. The silence and no-speech values come from the
    admin settings and are applied at each reset.
    """

    def __init__(self, threshold: float = 0.5, silence_s: float = 0.8, no_speech_s: float = 6.0, max_s: float = 60.0):
        self.vad = SileroVoiceActivityDetector()
        self.threshold = threshold
        self.max_chunks = int(max_s / CHUNK_SECONDS)
        self.silence_chunks = int(silence_s / CHUNK_SECONDS)
        self.no_speech_chunks = int(no_speech_s / CHUNK_SECONDS)
        self.reset()

    def reset(self, silence_s: float | None = None, no_speech_s: float | None = None) -> None:
        if silence_s is not None:
            self.silence_chunks = int(silence_s / CHUNK_SECONDS)
        if no_speech_s is not None:
            self.no_speech_chunks = int(no_speech_s / CHUNK_SECONDS)
        self.vad.reset()
        self._buf = b""
        self.started = False
        self.finished = False
        self._quiet = 0
        self._n = 0

    def feed(self, pcm: bytes) -> list[str]:
        events: list[str] = []
        self._buf += pcm
        while len(self._buf) >= CHUNK_BYTES and not self.finished:
            chunk, self._buf = self._buf[:CHUNK_BYTES], self._buf[CHUNK_BYTES:]
            self._n += 1
            speech = self.vad(chunk) >= self.threshold
            if speech:
                self._quiet = 0
                if not self.started:
                    self.started = True
                    events.append("speech_start")
            elif self.started:
                self._quiet += 1
                if self._quiet >= self.silence_chunks:
                    self.finished = True
                    events.append("speech_end")
            elif self._n >= self.no_speech_chunks:
                self.finished = True
                events.append("no_speech")
            if not self.finished and self._n >= self.max_chunks:
                self.finished = True
                events.append("speech_end")
        return events
