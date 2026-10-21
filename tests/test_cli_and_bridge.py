"""Command line behaviour (friendly errors, presets) and the bridge's guards. No device needed."""
import asyncio
import stat

import pytest

from hermes_jarvis import cli, config


def test_a_missing_config_file_gives_a_message_not_a_traceback(capsys, tmp_path):
    assert cli.main(["-c", str(tmp_path / "nope.yaml"), "doctor"]) == 1
    err = capsys.readouterr().err
    assert err.startswith("error: config file not found") and "Traceback" not in err


def test_a_typo_in_the_config_is_explained(capsys, tmp_path):
    f = tmp_path / "config.yaml"
    f.write_text("stt:\n  provder: local\n")
    assert cli.main(["-c", str(f), "doctor"]) == 1
    assert "unknown config key" in capsys.readouterr().err


def test_init_writes_private_files_and_a_preset(capsys, tmp_path):
    assert cli.main(["init", str(tmp_path / "a")]) == 0
    env = (tmp_path / "a" / ".env")
    assert stat.S_IMODE(env.stat().st_mode) == 0o600 and "ADMIN_PASSWORD=" in env.read_text()
    assert "type: hermes" in (tmp_path / "a" / "config.yaml").read_text()
    assert cli.main(["init", str(tmp_path / "b"), "--preset", "local"]) == 0
    c = config.load(tmp_path / "b" / "config.yaml")      # the preset is valid config
    assert (c.brain.type, c.stt.provider, c.router.enabled) == ("openai", "local", False)
    assert "ELEVENLABS" not in (tmp_path / "b" / ".env").read_text()   # the local preset needs no cloud keys
    assert cli.main(["init", str(tmp_path / "a")]) == 1                # never overwrites
    capsys.readouterr()


def test_healthcheck_reflects_the_speech_port():
    from aiohttp import web

    from hermes_jarvis.audio_server import AudioServer

    async def go():
        srv = AudioServer(port=0)  # 0 is "unset" in AudioServer; use a real free port instead
        srv.port = 18899
        await srv.start()
        config.use({"audio": {"port": 18899}})
        up = await asyncio.get_running_loop().run_in_executor(None, cli.cmd_healthcheck, None)
        await srv.stop()
        down = await asyncio.get_running_loop().run_in_executor(None, cli.cmd_healthcheck, None)
        return up, down, web

    up, down, _ = asyncio.run(go())
    assert (up, down) == (0, 1)


def test_the_audio_server_serves_expires_and_caps_clips():
    from aiohttp.test_utils import TestClient, TestServer

    from hermes_jarvis.audio_server import MAX_CLIPS, AudioServer

    async def go():
        srv = AudioServer(port=1)
        url = srv.add_wav(b"RIFFdata")
        from aiohttp import web
        app = web.Application()
        app.add_routes([web.get("/audio/{cid}", srv._get), web.get("/healthz", srv._health)])
        async with TestClient(TestServer(app)) as c:
            ok = await c.get("/audio/" + url.rsplit("/", 1)[1])
            missing = await c.get("/audio/nope.wav")
            health = await c.get("/healthz")
            return ok.status, await ok.read(), ok.content_type, missing.status, health.status, srv

    status, body, ctype, missing, health, srv = asyncio.run(go())
    assert (status, body, ctype, missing, health) == (200, b"RIFFdata", "audio/wav", 404, 200)
    for _ in range(MAX_CLIPS + 50):
        srv.add_wav(b"x")
    assert len(srv._clips) <= MAX_CLIPS


def test_a_disconnect_mid_turn_does_not_crash_the_pipeline(monkeypatch):
    from hermes_jarvis import bridge as bridge_mod

    class Bare(bridge_mod.VoiceBridge):
        def __init__(self):  # skip the heavy parts: only the send guard is under test
            self.client = None

    b = Bare()
    b._send(bridge_mod.Ev.VOICE_ASSISTANT_RUN_END, {})  # must be a no-op, not an AttributeError
    sent = []
    b.client = type("C", (), {"send_voice_assistant_event": lambda self, ev, d: sent.append(ev)})()
    b._send(bridge_mod.Ev.VOICE_ASSISTANT_RUN_END, {})
    assert len(sent) == 1


@pytest.mark.parametrize("argv", [["voices", "download", "not-a-voice"]])
def test_other_user_errors_are_friendly(argv, capsys):
    assert cli.main(argv) == 1
    assert capsys.readouterr().err.startswith("error:")


def test_a_fresh_device_gets_a_wake_word_switched_on():
    import asyncio
    from types import SimpleNamespace as NS

    from hermes_jarvis import config
    from hermes_jarvis.bridge import VoiceBridge

    class Client:
        def __init__(self, active):
            self.active, self.set_to = active, None

        async def get_voice_assistant_configuration(self, timeout):
            return NS(active_wake_words=self.active, max_active_wake_words=1,
                      available_wake_words=[NS(id="okay_nabu"), NS(id="hey_jarvis")])

        async def set_voice_assistant_configuration(self, ids):
            self.set_to = ids

    async def go(active, want="hey_jarvis"):
        config.cfg.device.wake_word = want
        c = Client(active)
        await VoiceBridge._ensure_wake_word(None, c)
        return c.set_to

    assert asyncio.run(go([])) == ["hey_jarvis"]
    assert asyncio.run(go(["okay_nabu"])) is None      # one is already active: leave it alone
    assert asyncio.run(go([], "nope")) is None          # not on this device
    assert asyncio.run(go([], "")) is None               # disabled
    config.cfg.device.wake_word = "hey_jarvis"
