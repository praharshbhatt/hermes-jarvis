"""Command line: run, doctor, discover, adopt, device, voices, init, say, ask."""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import secrets
import signal
import sys
from pathlib import Path

from . import __version__, config
from .errors import UserError

PRESETS = {"hermes": Path(__file__).parent / "config.example.yaml",
           "local": Path(__file__).parent / "presets" / "local.yaml"}


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    for noisy in ("aiohttp.access", "zeroconf", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def cmd_run(args) -> int:
    _setup_logging(args.verbose)
    from .bridge import VoiceBridge

    async def go() -> None:
        bridge = VoiceBridge()
        task = asyncio.create_task(bridge.run())
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):  # docker stop sends SIGTERM
            try:
                loop.add_signal_handler(sig, task.cancel)
            except NotImplementedError:  # Windows
                pass
        try:
            await task
        except asyncio.CancelledError:
            logging.getLogger("hermes_jarvis").info("shutting down")
        finally:
            await bridge.close()

    asyncio.run(go())
    return 0


def cmd_healthcheck(_args) -> int:
    """Exit 0 if the running bridge answers on its speech port. Used by the container health check."""
    import urllib.request
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{int(config.cfg.audio.port)}/healthz", timeout=4)  # noqa: S310
    except Exception as e:
        print(f"unhealthy: {e}")
        return 1
    return 0


def cmd_doctor(_args) -> int:
    logging.basicConfig(level=logging.ERROR)
    from .doctor import run
    return asyncio.run(run())


def cmd_discover(_args) -> int:
    from .discovery import discover
    devices = asyncio.run(discover(timeout=5.0))
    if not devices:
        print("No ESPHome devices found. Is the device powered on and on the same network?")
        return 1
    for d in devices:
        state = "adopted (has a key)" if d.adopted else ("ready to adopt" if d.adoptable else "no encryption")
        print(f"{d.name:34} {d.host:15} esphome {d.version:8} {state}{'  <- voice device' if d.likely_voice else ''}")
    return 0


def cmd_adopt(args) -> int:
    from .adopt import AdoptError, adopt
    from .discovery import discover

    async def go() -> int:
        host = args.host
        name = ""
        if not host:
            voice = [d for d in await discover(timeout=5.0) if d.likely_voice]
            if not voice:
                print("No voice device found. Pass --host <ip> if you know its address.")
                return 1
            if len(voice) > 1:
                print("Several voice devices found; pick one with --host:")
                for d in voice:
                    print(f"  {d.name}  {d.host}")
                return 1
            host, name = voice[0].host, voice[0].name
            print(f"Found {name} at {host}")
        try:
            out = await adopt(host, name, int(config.cfg.device.port))
        except AdoptError as e:
            print(f"Could not adopt: {e}")
            return 1
        print(f"{out['note'].capitalize()}: {out['name']} at {host}. The key is saved in {config.cfg.data_path('device.json')}.")
        print("Next: `hermes-jarvis doctor`, then `hermes-jarvis run`.")
        return 0

    return asyncio.run(go())


def cmd_voices(args) -> int:
    from .tts import voices
    if args.action == "list":
        for name, (_, desc) in voices.CATALOG.items():
            mark = "installed" if voices.installed(name) else "         "
            print(f"{mark}  {name:38} {desc}")
        print("\nAny Piper voice works: set tts.voice to the path of its .onnx file. "
              "Check each voice's license in its model card.")
        return 0
    if not args.name:
        print("usage: hermes-jarvis voices download <name>")
        return 2
    print(f"Downloaded to {voices.ensure(args.name)}")
    return 0


def cmd_init(args) -> int:
    d = Path(args.dir).resolve()
    d.mkdir(parents=True, exist_ok=True)
    cfg_file, env_file = d / "config.yaml", d / ".env"
    if cfg_file.exists() or env_file.exists():
        print(f"{cfg_file} or {env_file} already exists; not overwriting.")
        return 1
    cfg_file.write_text(PRESETS[args.preset].read_text())
    pw = secrets.token_urlsafe(14)
    keys = ("" if args.preset == "local" else
            "HERMES_API_KEY=\nELEVENLABS_API_KEY=\nDEEPGRAM_API_KEY=\nOPENAI_API_KEY=\nOPENROUTER_API_KEY=\n")
    env_file.write_text("# Secrets for hermes-jarvis. Never commit this file.\n" f"ADMIN_PASSWORD={pw}\n" + keys)
    os.chmod(env_file, 0o600)
    print(f"Wrote {cfg_file} and {env_file} (preset: {args.preset}).")
    print(f"Admin UI login: user 'admin', password {pw}  (also in .env)")
    if args.preset == "local":
        print("Next: make sure Ollama is running, then `hermes-jarvis adopt` and `hermes-jarvis doctor`.")
    else:
        print("Next: put your keys in .env and set brain.base_url in config.yaml, then `hermes-jarvis doctor`.")
    return 0


def cmd_ask(args) -> int:
    """Run the brain only and print what would be spoken. No microphone, no speaker, no device."""
    from .brains import make_brain
    from .speak import SpeakParser

    async def go() -> int:
        brain = make_brain()
        parser = SpeakParser()
        text = " ".join(args.text)
        try:
            async for ev in brain.turn(text):
                if ev["type"] == "text":
                    for s in parser.feed(ev["delta"]):
                        print(f"[speak] {s}", flush=True)
                elif ev["type"] == "tool" and ev.get("status") == "running":
                    print(f"[tool]  {ev.get('tool')}: {str(ev.get('label', ''))[:70]}", flush=True)
                elif ev["type"] == "error":
                    print(f"[error] {ev}")
                    return 1
            for s in parser.finish():
                print(f"[speak] {s}")
        finally:
            await brain.close()
        return 0

    return asyncio.run(go())


def cmd_device(args) -> int:
    from . import devicectl

    async def go() -> int:
        async with devicectl.connected() as c:
            if args.action == "logs":
                await devicectl.stream_logs(c, float(args.name or 30))
                return 0
            ents, states = await devicectl.snapshot(c)
            if args.action == "list":
                for it in devicectl.describe(ents, states):
                    extra = f"  options: {', '.join(it['options'])}" if "options" in it else ""
                    print(f"{it['kind']:7} {it['name']:30} {str(it['state']):22}{extra}")
                return 0
            if not args.name:
                print(f"usage: hermes-jarvis device {args.action} NAME" + (" VALUE" if args.action == "set" else ""))
                return 2
            try:
                print(devicectl.apply(c, ents, args.name, args.value))
            except ValueError as e:
                print(e)
                return 1
            await asyncio.sleep(0.5)
            return 0

    try:
        return asyncio.run(go())
    except RuntimeError as e:
        print(e)
        return 1


def cmd_hash_password(_args) -> int:
    """Make a PBKDF2 hash for ADMIN_PASSWORD_HASH, so the password itself never has to sit in .env."""
    import getpass

    from .auth import hash_password
    pw = getpass.getpass("Admin password: ")
    if len(pw) < 8:
        print("error: use at least 8 characters", file=sys.stderr)
        return 1
    if getpass.getpass("Repeat it: ") != pw:
        print("error: the two entries differ", file=sys.stderr)
        return 1
    print("Put this line in .env (and remove ADMIN_PASSWORD):\n")
    print(f"ADMIN_PASSWORD_HASH={hash_password(pw)}")
    return 0


def cmd_say(args) -> int:
    """Speak a line on the device: tests text to speech and the way back to the speaker."""
    from aioesphomeapi import APIClient, MediaPlayerInfo

    from . import discovery
    from .audio_server import AudioServer
    from .tts import PiperTTS

    async def go() -> int:
        host, _ = await discovery.resolve_host()
        if not host:
            print("No device found.")
            return 1
        tts = PiperTTS()
        srv = AudioServer(port=int(config.cfg.audio.port) + 1)  # next to a running bridge
        await srv.start()
        c = APIClient(host, int(config.cfg.device.port), None, noise_psk=config.device_key())
        await c.connect(login=True)
        ents, _ = await c.list_entities_services()
        mp = next(e for e in ents if isinstance(e, MediaPlayerInfo))
        wav = tts.synth_wav(" ".join(args.text))
        c.media_player_command(mp.key, media_url=srv.add_wav(wav), announcement=True)
        await asyncio.sleep(max(3.0, (len(wav) - 44) / (tts.sample_rate * 2) + 2.0))
        await c.disconnect()
        await srv.stop()
        return 0

    return asyncio.run(go())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="hermes-jarvis", description=__doc__)
    p.add_argument("--version", action="version", version=f"hermes-jarvis {__version__}")
    p.add_argument("-c", "--config", help="path to config.yaml (default: ./config.yaml or $HERMES_JARVIS_CONFIG)")
    p.add_argument("--debug", action="store_true", help="show full tracebacks for errors")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="start the voice bridge")
    r.add_argument("-v", "--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("doctor", help="check the setup").set_defaults(fn=cmd_doctor)
    sub.add_parser("discover", help="list ESPHome devices on the network").set_defaults(fn=cmd_discover)
    a = sub.add_parser("adopt", help="give a freshly flashed device its private encryption key")
    a.add_argument("--host", help="device IP address (default: find it automatically)")
    a.set_defaults(fn=cmd_adopt)
    v = sub.add_parser("voices", help="list or download speech voices")
    v.add_argument("action", choices=["list", "download"])
    v.add_argument("name", nargs="?")
    v.set_defaults(fn=cmd_voices)
    i = sub.add_parser("init", help="write a starter config.yaml and .env")
    i.add_argument("dir", nargs="?", default=".")
    i.add_argument("--preset", choices=sorted(PRESETS), default="hermes",
                   help="hermes: the Hermes agent and a cloud speech-to-text service. local: Ollama and local Whisper, no account")
    i.set_defaults(fn=cmd_init)
    sub.add_parser("hash-password", help="make an ADMIN_PASSWORD_HASH value for .env").set_defaults(fn=cmd_hash_password)
    sub.add_parser("healthcheck", help="exit 0 if the running bridge is healthy (for containers)").set_defaults(fn=cmd_healthcheck)
    d = sub.add_parser("device", help="read or change the device's controls (wake word sensitivity, mute, ...), or read its log")
    d.add_argument("action", choices=["list", "set", "press", "logs"])
    d.add_argument("name", nargs="?", help="control name, for set and press")
    d.add_argument("value", nargs="?", help="value for set; seconds for logs (default 30)")
    d.set_defaults(fn=cmd_device)
    s = sub.add_parser("say", help="speak a line on the device")
    s.add_argument("text", nargs="+")
    s.set_defaults(fn=cmd_say)
    q = sub.add_parser("ask", help="send text to the brain and print what would be spoken")
    q.add_argument("text", nargs="+")
    q.set_defaults(fn=cmd_ask)

    args = p.parse_args(argv)
    try:
        if args.command != "init":
            config.load(args.config)
        return int(args.fn(args))
    except UserError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except OSError as e:
        if args.debug:
            raise
        hint = " (is hermes-jarvis already running?)" if getattr(e, "errno", None) == 98 else ""
        print(f"error: {e}{hint}", file=sys.stderr)
        return 1
    except Exception as e:
        if args.debug:
            raise
        print(f"error: {type(e).__name__}: {e}\n(run again with --debug for the full traceback)", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
