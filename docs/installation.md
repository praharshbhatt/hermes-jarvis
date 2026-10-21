# Installation

hermes-jarvis is a small Python service. It runs all the time, on a machine that can reach both the voice device and your
brain. A Raspberry Pi 4 or better, a NAS, a mini PC or a home server is plenty: Piper runs faster than real time on one CPU
thread, and nothing needs a GPU.

## pip

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install hermes-jarvis            # fully local speech to text: pip install 'hermes-jarvis[local-stt]'
hermes-jarvis init                   # or: hermes-jarvis init --preset local   (Ollama + local Whisper, no accounts)
```

Run it with `hermes-jarvis run` from the folder that holds `config.yaml` and `.env`, or pass `-c /path/to/config.yaml`.

### As a service (systemd)

```ini
# /etc/systemd/system/hermes-jarvis.service
[Unit]
Description=hermes-jarvis voice bridge
After=network-online.target
Wants=network-online.target

[Service]
User=jarvis
WorkingDirectory=/opt/hermes-jarvis
ExecStart=/opt/hermes-jarvis/.venv/bin/hermes-jarvis run
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Run `sudo systemctl enable --now hermes-jarvis`, then `journalctl -u hermes-jarvis -f` to follow the log.

## Docker

The image is CPU only and holds no secrets and no voices. Everything lives in the `/data` volume.

```sh
mkdir -p data && sudo chown 1000 data      # the container runs as user 1000
docker compose run --rm hermes-jarvis hermes-jarvis init /data   # writes data/config.yaml and data/.env: edit both
docker compose run --rm hermes-jarvis hermes-jarvis adopt        # once, after flashing the device
docker compose up -d
```

`./data` holds your `config.yaml`, your `.env` with the keys, the device key and the downloaded voices. Back it up.

The included `docker-compose.yml` uses **host networking**: the container finds the device by mDNS, and the device downloads
speech clips straight from the host. It's the simplest setup and works on Linux. Docker Desktop on macOS and Windows doesn't
support host networking, so use the next section there.

To build the image instead of pulling it, uncomment `build:` in the compose file. `--build-arg EXTRAS=local-stt` adds fully
local speech to text.

### Without host networking

Publish the ports and give the bridge the addresses explicitly, because mDNS doesn't cross a bridge network:

```yaml
services:
  hermes-jarvis:
    image: ghcr.io/praharshbhatt/hermes-jarvis:latest
    ports: ["8651:8651"]                 # speech clips (the device downloads them from here)
    environment:
      HJ_DEVICE_HOST: 192.168.1.50       # the voice device
      HJ_AUDIO_PUBLIC_HOST: 192.168.1.10 # the Docker host, as the device sees it
    volumes: ["./data:/data"]
```

In this mode `hermes-jarvis adopt` can't find the device by mDNS, so pass `--host <device ip>`.

## On a NAS

Any NAS that runs Docker works with the compose file above. Put `./data` on a persistent volume, because the first-time
voice and Whisper-model downloads land there too. A NAS CPU is usually fast enough for Piper. To check how it sounds and how
quick it is, run `hermes-jarvis voices download en_GB-alan-medium` and then `hermes-jarvis say "test"`.

## Web UI over https

The web UI is plain HTTP and listens on localhost by default. To use it from other computers, put it behind a reverse proxy
that terminates TLS, and tell hermes-jarvis to trust the proxy so session cookies are marked `Secure`:

```yaml
# config.yaml
admin:
  host: 127.0.0.1        # the proxy runs on the same machine; keep the UI itself off the network
  trust_proxy: true
```

A Caddy example (Caddy gets and renews the certificate for you, and the live view needs no special buffering settings):

```
jarvis.example.com {
    reverse_proxy 127.0.0.1:8650
}
```

nginx needs `proxy_buffering off;` for the live view (`/api/events`), plus the usual `X-Forwarded-Proto` header. A VPN such as
Tailscale works too: reach `http://<machine>:8650` over the VPN and keep `admin.host` on the VPN address only.

Use a long random password, or a hash from `hermes-jarvis hash-password`. See [security](security-privacy.md#the-web-ui).

## Updating

With pip, run `pip install -U hermes-jarvis`. With Docker, run `docker compose pull && docker compose up -d`. Your settings
and the device key live in the data directory and survive updates. For new firmware, see [flashing](flashing.md#updating).
