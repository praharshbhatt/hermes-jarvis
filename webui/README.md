# hermes-jarvis web UI

The control panel for hermes-jarvis: sign-in, a live core that animates from the voice pipeline, the guided setup, and settings.
Next.js (App Router, React, TypeScript), exported to static files. The Python service serves them, so nothing here runs at
runtime.

```sh
npm ci
npm run dev          # http://localhost:3000, proxies /api to http://127.0.0.1:8680 (HJ_API to change)
npm run lint && npm run typecheck && npm test
npm run build        # static site in out/
../scripts/build_ui.sh    # build and copy into ../src/hermes_jarvis/static/app (commit the result)
```

Start the service side with `python ../scripts/admin_demo.py --dev` (fake data, fake device, scripted live events).

## Layout

| | |
|---|---|
| `src/app/login` | sign-in page |
| `src/app/(app)` | the signed-in pages (`/`, `/setup`, `/settings`) sharing one layout, so the live stream persists |
| `src/components/Reactor.tsx` | the animated core (canvas); `drawFrame` is pure and tested |
| `src/components/setup/` | the guided setup steps |
| `src/lib/api.ts` | fetch wrapper: same-origin cookies, CSRF token, expired-session handling |
| `src/lib/events.tsx` | the live event stream (SSE) and its reducer |
| `src/lib/session.tsx` | session, idle countdown, auth gate |

## Rules

- **No external assets** (fonts, scripts, images, CDNs): the service sends a strict Content-Security-Policy.
- **No secrets in the browser.** The session is an `HttpOnly` cookie; the CSRF token is the only credential-like value JS holds.
- Respect `prefers-reduced-motion`, keep keyboard focus visible, keep contrast readable, and make it work down to phone width.
