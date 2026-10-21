import asyncio

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

from hermes_jarvis import config
from hermes_jarvis.stt import STT, make_provider
from hermes_jarvis.stt.base import pcm_to_wav
from hermes_jarvis.tts import voices


def test_voice_paths_and_catalog(tmp_path):
    assert voices.model_path("en_GB-alan-medium") == config.cfg.data_path("voices", "en_GB-alan-medium.onnx")
    assert voices.model_path("~/x/my.onnx").name == "my.onnx"
    assert not voices.installed("en_GB-alan-medium")
    assert all(rel.startswith("en/") and rel.endswith(name) for name, (rel, _) in voices.CATALOG.items())
    with pytest.raises(FileNotFoundError, match="unknown voice"):
        voices.ensure("not-a-voice")
    with pytest.raises(FileNotFoundError):
        voices.ensure(str(tmp_path / "missing.onnx"))


def test_an_installed_voice_is_not_downloaded_again(monkeypatch):
    p = voices.model_path("en_GB-alan-medium")
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x")
    (p.parent / "en_GB-alan-medium.onnx.json").write_text("{}")
    monkeypatch.setattr(voices, "_fetch", lambda *a: pytest.fail("should not download"))
    assert voices.ensure("en_GB-alan-medium") == p


def test_stt_provider_factory_and_key_checks(monkeypatch):
    with pytest.raises(ValueError, match="unknown stt provider"):
        make_provider("nope")
    el = make_provider("elevenlabs")
    assert el.check()[0] is False and "ELEVENLABS_API_KEY" in el.check()[1]
    monkeypatch.setenv("ELEVENLABS_API_KEY", "k")
    assert el.check()[0] is True
    config.use({"stt": {"provider": "deepgram", "compare_with": "elevenlabs"}})
    assert [p.name for p in STT().providers()] == ["deepgram", "elevenlabs"]


def test_openai_compatible_stt_against_a_fake_server():
    seen = {}

    async def transcriptions(request):
        form = await request.post()
        seen["model"], seen["lang"], seen["auth"] = form["model"], form["language"], request.headers.get("Authorization")
        seen["bytes"] = len(form["file"].file.read())
        return web.json_response({"text": " hello there "})

    async def go():
        app = web.Application()
        app.router.add_post("/v1/audio/transcriptions", transcriptions)
        async with TestServer(app) as srv:
            config.use({"stt": {"provider": "openai", "openai_base_url": str(srv.make_url("/v1"))}})
            return await make_provider("openai").transcribe_pcm(b"\0\0" * 1600)

    assert asyncio.run(go()) == "hello there"
    assert seen["model"] == "gpt-4o-mini-transcribe" and seen["lang"] == "en" and seen["bytes"] > 3200


def test_wav_wrapper_has_a_header():
    wav = pcm_to_wav(b"\0\0" * 100)
    assert wav[:4] == b"RIFF" and len(wav) == 44 + 200
