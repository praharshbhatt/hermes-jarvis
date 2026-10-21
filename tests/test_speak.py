"""The <speak> parser: pulls spoken sentences out of streamed model text."""
from hermes_jarvis.speak import SpeakParser, clean


def run(deltas):
    p, out = SpeakParser(), []
    for d in deltas:
        out += p.feed(d)
    out += p.finish()
    return out


def test_tags_split_at_every_position_parse_the_same():
    text = ("<speak>Found it. The first heading is **2025 Achievements**, and I changed nothing."
            "</speak>\n\nPath: /x/y.md\n- Line 1")
    want = run([text])
    assert want == ["Found it.", "The first heading is 2025 Achievements, and I changed nothing."]
    for i in range(1, len(text)):
        assert run([text[:i], text[i:]]) == want, i


def test_preamble_tool_pause_and_final_answer():
    out = run(["<speak>Running that", " command now.</speak>", "\n\n<speak>The output was hello,",
               " exit code zero.</speak>\n\nThe command printed: hello"])
    assert out == ["Running that command now.", "The output was hello, exit code zero."]


def test_unclosed_tag_is_flushed_at_the_end():
    assert run(["<speak>Half a thought and no close"]) == ["Half a thought and no close"]


def test_sentences_are_emitted_while_still_inside_the_tag():
    p = SpeakParser()
    got = p.feed("<speak>First sentence is here. Second one is also here. Third is part")
    assert got == ["First sentence is here. Second one is also here."]  # short ones are merged
    assert p.feed("ial.</speak>") == ["Third is partial."]


def test_fallback_when_the_model_ignores_the_format():
    fb = run(["Here is the script:\n```python\nprint(1)\n```\nIt prints one. Then it exits. Third sentence here."])
    assert fb[-1] == "The full details are in your chat."
    assert "print(1)" not in " ".join(fb)
    assert run(["Sure, done."]) == ["Sure, done."]


def test_clean_makes_text_safe_to_read_aloud():
    assert clean("See [the docs](https://a.b/c) at https://x.y now \U0001F642") == "See the docs at a link now"
    assert clean("**bold** and `code`") == "bold and code"
