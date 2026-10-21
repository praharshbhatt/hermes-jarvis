# Security and privacy

hermes-jarvis puts a microphone in your home in front of an agent that can act. Here is what goes where.

## What leaves your network

| Data | Goes to | When | Can you keep it local? |
|---|---|---|---|
| Your voice after the wake word | The speech-to-text provider you chose | Every request | Yes: `stt.provider: local` (faster-whisper) keeps audio on your machine |
| What you said, as text | Your brain (Hermes, Ollama, OpenAI, ...) | Every request | Yes, with a brain on your network |
| What you said, as text, plus recent conversation titles | OpenRouter (the router's decision model) | Only when the session window has passed, with the Hermes brain, and only if `OPENROUTER_API_KEY` is set | Yes: leave the key out or set `router.enabled: false` |
| Nothing | The web UI loads no external scripts, fonts or images, and its Content-Security-Policy would block them | Always |
| Replies, as speech clips | Nowhere: Piper makes them on your machine and the device downloads them over your LAN | Every reply | Always local |

**This software sends nothing before the wake word.** Wake-word detection runs on the device, and audio only starts flowing to
hermes-jarvis after it fires. What the device's own firmware does is the ESPHome firmware's business; the source is in
`firmware/`.

## What is stored

- **Recordings** of what the microphone heard are **off** by default (`privacy.save_recordings`). When on, WAV files go to
  `data/recordings` and are deleted after `privacy.recordings_keep_days`. They include false triggers.
- **Transcripts and replies** appear in the web UI's recent-turns list and in `data/turns.jsonl` (the last few hundred turns;
  older ones are trimmed away). This is on by default (`privacy.save_transcripts`). Turn it off and only timings and routing
  are kept, and log lines show `<hidden>` instead of text.
- **Conversation history** belongs to Hermes, in its own data, when you use the Hermes brain. With the `openai` brain it's in
  `data/brain-sessions.json` (the last 20 conversations).
- **Web UI sessions** live in memory only. Restarting hermes-jarvis signs everyone out.
- **Session state** is in `data/state.json`, which holds the current conversation id and when you last spoke.
  `data/settings.json` and `data/settings-history.jsonl` hold your settings and a trimmed history of changes, including the
  prompts you edited.
- **Logs** at INFO level include what was heard and said, unless `save_transcripts` is off.
- **The device key** is in `data/device.json` (mode 600). **API keys** live only in `.env`. They are never written to
  settings or deliberately logged. Error text from remote services is logged in truncated form and doesn't contain your keys.

## The device link

- After `hermes-jarvis adopt`, the connection to the device is encrypted (Noise, with a private key only you hold), and the
  device refuses everything else.
- **The adoption step itself sends the new key over your local network in plaintext, once.** Do it on a network you trust,
  not a shared or guest one. Adopting an ESPHome device in Home Assistant makes the same trade-off.
- The device downloads speech clips from the bridge over **plain HTTP** (port 8651). Clip addresses are random and expire
  after ten minutes, but anyone on your LAN who can see the traffic could fetch a clip. Keep the bridge on a trusted LAN.

## The web UI

The web UI (sign-in page, live view, settings, setup guide) is a static app served by the same process as the bridge.

**Off, and local, by default.** It starts only if `ADMIN_PASSWORD` (or `ADMIN_PASSWORD_HASH`) is set, and it listens on
127.0.0.1 unless `admin.host` says otherwise.

**Sign-in.** The login page checks the user name and password in constant time, against `ADMIN_PASSWORD` or against a PBKDF2
hash. `hermes-jarvis hash-password` makes the hash, so the password itself needn't sit in `.env`. Failed logins are slowed
down, and an address is locked out for five minutes after ten failures.

**Sessions.** A successful login creates a server-side session with a random 256-bit id, held in an `HttpOnly`,
`SameSite=Strict` cookie. Over https the cookie is also `Secure` and carries the `__Host-` prefix. The server keeps only a hash
of the id, and a new id is issued at every login. A session ends after 30 minutes without activity, after 12 hours in total
(both are settings), or on sign-out. Background polling and the live stream don't count as activity, so an abandoned tab signs
itself out. The page warns you a minute before that happens.

**Forged requests.** Every request that changes something needs the session's CSRF token in a header, and a browser `Origin`
that is this site (or one listed in `admin.allowed_origins`). The server refuses requests the browser marks as cross-site.

**Headers.** Every response carries a Content-Security-Policy. It allows scripts only from this site plus the hashes of each
page's own bootstrap scripts, with no `unsafe-inline` or `unsafe-eval` for scripts. Responses also carry
`frame-ancestors 'none'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer` and a restrictive
`Permissions-Policy`, and everything except the built, content-hashed assets gets `Cache-Control: no-store`. Request bodies
are limited to 256 KB and must be JSON objects. Settings are range-checked and length-limited.

**The live view** (`/api/events`, server-sent events) needs a session. It carries pipeline states, short text lines, tool
names and routing decisions. It never carries audio or secrets, it shows only a loudness number for the microphone, and it
hides transcript text when `privacy.save_transcripts` is off.

**It's plain HTTP unless you add TLS.** Cookies are `Secure` only when the request arrives over https. If you open the UI
beyond one machine, put it behind a TLS reverse proxy (there's a Caddy example in
[installation](installation.md#web-ui-over-https)) and set `admin.trust_proxy: true`, or reach it over a VPN such as
Tailscale. Use a long random password.

**What it can do.** It can change the prompts sent to your agent, how conversations are routed, the speech voice, and the
device's controls (including adopting a device). Treat access to it like access to the agent.

## What the agent can do

Anyone who can speak near the device can give your agent commands: a guest, a child, or a TV that happens to say the wake
word. Speech to text also mishears. So:

- Keep the agent's dangerous tools (deleting, sending, spending, controlling the house) behind confirmation inside Hermes.
  The voice prompt also tells the agent to ask before anything risky or destructive, but that is a request to a language
  model, not a guarantee.
- For a stricter setup, use a Hermes profile with limited tools for voice.
- Remember that Hermes profiles isolate memory and sessions, not what the agent can reach on its machine.
- Use the mute switch when you don't want it listening.

## Supply chain

The upstream firmware config is vendored and pinned to one commit, ESPHome is pinned, and CI builds the released firmware
from a tagged commit. Python dependencies have lower bounds, so pin them in your own install if you need reproducibility.
Voices come from the upstream Piper voice repository on first use.

## Reporting a problem

See [SECURITY.md](../SECURITY.md).
