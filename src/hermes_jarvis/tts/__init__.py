"""Text to speech. Piper is the only engine for now; the app only needs `synth_wav(text)` and `sample_rate`."""
from .piper import PiperTTS

__all__ = ["PiperTTS"]
