# Setting up Hermes as the brain

hermes-jarvis talks to the OpenAI-compatible API server built into the [Hermes agent](https://hermes-agent.nousresearch.com)
(see Hermes' own [API server docs](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server)). You install
nothing into Hermes. You turn its API on, give it a key, and point hermes-jarvis at it.

## 1. Turn on the API server and choose a key

In Hermes' environment, enable the API server and set a key you choose (any long random string, for example
`openssl rand -hex 32`):

```
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0        # or 127.0.0.1 if hermes-jarvis runs on the same machine
API_SERVER_PORT=8642
API_SERVER_KEY=<your key>
```

Then put the same key in hermes-jarvis' `.env` as `HERMES_API_KEY`, and set `brain.base_url` in `config.yaml`.

> **Gotcha: which value wins.** Hermes reads `API_SERVER_KEY` from the `.env` file in its data directory *and* from the
> container or process environment, and the `.env` file wins. If you changed the key in your Docker compose file and still
> get "Invalid gateway API key", look for an older `API_SERVER_KEY` in `<hermes data>/.env`. Hermes logs a warning when both
> are set.
>
> **Gotcha: restarts are slow.** After a restart, Hermes can take several minutes to answer `/health`, and longer with many
> profiles or messaging platforms. `hermes-jarvis doctor` reports "unreachable" until it's up.

To check that it works:

```sh
curl -H "Authorization: Bearer $HERMES_API_KEY" http://<hermes>:8642/v1/models
hermes-jarvis ask "Say hello in one short sentence."
```

## 2. Profiles (optional)

Hermes profiles are separate agents, each with its own memory, sessions, skills and persona (a personal one and a work one,
say). Every profile you want to reach by voice needs its own API key, and it is addressed under `/p/<name>/`:

1. In that profile's `.env` (inside Hermes' data directory, under `profiles/<name>/`), set `API_SERVER_KEY`.
2. In hermes-jarvis' `.env`, set `HERMES_API_KEY_<NAME>` to the same value (upper-case name).
3. In the web UI, add the profile and write a one-line description of what belongs there. The router reads these
   descriptions to pick a profile for each new conversation, so be concrete ("clients, invoices, contracts, project work").

Profiles isolate Hermes' state (memory, sessions, skills). They don't sandbox what the agent can reach on the machine it
runs on.

## 3. Conversations and the router

Each spoken turn is one request to the Hermes API. hermes-jarvis sends the new message with the `X-Hermes-Session-Id` header
of the conversation it continues, and Hermes keeps the transcript. Sessions created this way show up in Hermes' session list
with the source `api_server` and a title Hermes writes itself.

- Within the **session window** (default 5 minutes) after the last voice activity, a request just continues the current
  conversation. No extra model is involved.
- After the window, the **router** asks a small, fast decision model which recent conversation the request continues (or
  whether it's new) and which profile fits. It resumes a conversation only when it's confident. Otherwise a new one starts.
  Without the router, a new conversation starts after the window, so you can ignore it entirely.

  > **The router is optional and experimental.** It uses [Jev](https://openrouter.ai/docs/guides/community/jev), a structured
  > decision model from TypeSafe, through OpenRouter's *alpha* decisions API (`POST /api/alpha/decisions`). It needs an
  > `OPENROUTER_API_KEY`, takes a few tenths of a second, costs a fraction of a cent per decision, and sends your request
  > text and recent conversation titles to OpenRouter. Because the API is in alpha, it may change. The endpoint and model are
  > settings (`router_url`, `router_model`), and any failure falls back to starting a new conversation.
- By default only conversations created through the API (`api_server`) are offered to the router. Hermes may refuse to
  continue a session owned by another surface (HTTP 409), so check with your own sessions before adding more sources in the
  web UI.

## 4. The JARVIS persona

The persona lives in Hermes, not here. Hermes reads a `SOUL.md` from its data directory (one per profile). A starting point
is in [examples/hermes/SOUL-jarvis.md](../examples/hermes/SOUL-jarvis.md): a calm, dry-witted British butler who is concise
by default. Edit it to taste.

How answers are shaped for speech is a separate matter, and it's always applied. With every turn, hermes-jarvis sends a
short voice-mode instruction (editable in the web UI). It tells the agent that the user is listening, asks it to put the
spoken answer in `<speak>` tags, and asks it to keep code, links and tables outside them. Details:
[architecture](architecture.md#the-speak-protocol).

## What shows up in Hermes

Voice conversations are ordinary Hermes sessions. Open the Hermes dashboard to read the full text of an answer, including
the code and links that weren't read aloud.

Whether you can *continue* a voice session from another Hermes surface (the desktop app, say) is up to Hermes. Its docs say
a session owned by another surface may be refused with HTTP 409, and we haven't tested it. Reading is always fine, and you
can always start a new chat that refers to the voice conversation.
