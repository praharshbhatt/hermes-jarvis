"""Pull spoken sentences out of Hermes's streamed text.

Hermes wraps spoken text in <speak>...</speak>; everything else is chat-only detail. The parser works on
streamed deltas and yields complete sentences as soon as they are known, so TTS can start early.
"""
import re

from . import prompts

OPEN, CLOSE = "<speak>", "</speak>"
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")
_MIN_CHARS = 24  # merge very short sentences so the clips are not choppy

_URL = re.compile(r"https?://\S+")
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_MD_MARKS = re.compile(r"[*_`#>]+")
_EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF]")
_CODE_FENCE = re.compile(r"```.*?```", re.S)


def clean(text: str) -> str:
    """Make a piece of text safe to read aloud."""
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub("a link", text)
    text = _EMOJI.sub("", text)
    text = _MD_MARKS.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _tail_prefix_len(buf: str, tag: str) -> int:
    """Length of a trailing piece of buf that could be the start of tag (so we hold it back)."""
    for n in range(min(len(tag) - 1, len(buf)), 0, -1):
        if buf.endswith(tag[:n]):
            return n
    return 0


class SpeakParser:
    def __init__(self) -> None:
        self._buf = ""
        self._pending = ""   # speech text not yet emitted as a full sentence
        self._inside = False
        self.saw_tag = False
        self.outside = ""    # text outside <speak>, kept for the fallback

    def _emit_sentences(self, final: bool) -> list[str]:
        out: list[str] = []
        parts = _SENT_SPLIT.split(self._pending)
        keep = "" if final else parts.pop()  # last part may be unfinished
        acc = ""
        for p in parts:
            acc = f"{acc} {p}".strip()
            if len(acc) >= _MIN_CHARS or final:
                out.append(acc)
                acc = ""
        # keep the unfinished tail as-is: its trailing space matters when the next delta starts a word
        self._pending = (f"{acc} {keep}" if acc else keep).lstrip() if not final else ""
        if final and acc:
            out.append(acc)
        return [s for s in (clean(x) for x in out) if s]

    def feed(self, delta: str) -> list[str]:
        self._buf += delta
        out: list[str] = []
        while True:
            if not self._inside:
                i = self._buf.find(OPEN)
                if i >= 0:
                    self.outside += self._buf[:i]
                    self._buf = self._buf[i + len(OPEN):]
                    self._inside, self.saw_tag = True, True
                    continue
                hold = _tail_prefix_len(self._buf, OPEN)
                self.outside += self._buf[: len(self._buf) - hold]
                self._buf = self._buf[len(self._buf) - hold:]
                return out
            i = self._buf.find(CLOSE)
            if i >= 0:
                self._pending += self._buf[:i]
                self._buf = self._buf[i + len(CLOSE):]
                self._inside = False
                out += self._emit_sentences(final=True)
                continue
            hold = _tail_prefix_len(self._buf, CLOSE)
            self._pending += self._buf[: len(self._buf) - hold]
            self._buf = self._buf[len(self._buf) - hold:]
            out += self._emit_sentences(final=False)
            return out

    def finish(self) -> list[str]:
        """End of stream. Flush an unclosed <speak>, or build a fallback if Hermes never used the tags."""
        if self._inside:
            self._pending += self._buf
            self._buf, self._inside = "", False
            return self._emit_sentences(final=True)
        if self.saw_tag:
            return []
        return fallback(self.outside + self._buf)


def fallback(text: str) -> list[str]:
    """Hermes ignored the format: speak the first couple of sentences and point to the chat."""
    had_code = "```" in text
    text = _CODE_FENCE.sub(" ", text)
    text = "\n".join(ln for ln in text.splitlines() if not ln.lstrip().startswith(("|", "- ", "* ", "#")))
    text = clean(text)
    if not text:
        return [prompts.FALLBACK_TAIL] if had_code else []
    sents = _SENT_SPLIT.split(text)
    spoken = " ".join(sents[:2])
    if len(spoken) > 300:
        spoken = spoken[:300].rsplit(" ", 1)[0]
    if len(sents) > 2 or had_code or len(text) > len(spoken):
        return [spoken, prompts.FALLBACK_TAIL]
    return [spoken]
