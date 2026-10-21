# Design notes

These are the measurements and the reasoning behind the main decisions, roughly in order of how much they shaped the
project. The numbers come from one test setup: a Voice PE, the agent on a separate machine, and a desktop-class CPU for
speech. Treat them as orders of magnitude, not benchmarks.

## The problem: agents are slow to start

A plain voice pipeline waits for the full answer. An agent that reads notes and calls tools can take anywhere from ten
seconds to several minutes. In our tests the Hermes API took 1.3 to 4.8 s to produce a first token for a simple question, and
14 s for one that read a file. So the design goal became twofold: never leave the user in silence, and never read aloud what
should only be read.

Here is where the time goes in a turn:

| Stage | Time |
|---|---|
| End of speech detected after you stop | 0.8 s (a setting) |
| Speech to text (cloud) | 0.2 to 0.7 s |
| Routing, when the session window has passed | 0.23 to 0.29 s, with the session list filtered on the server |
| First token from the agent | 1.3 to 4.8 s |
| Text to speech for one sentence (Piper, CPU) | about 0.1 s; real-time factor 0.04 to 0.08 (desktop-class CPU; measure yours with `hermes-jarvis say`) |
| Gap between consecutive clips on the device | 0.12 to 0.17 s |

## Decisions and the reasons behind them

**Replies are announcements, and the pipeline run ends early.** Home Assistant's pipeline plays one response and holds the
device until it finishes. If we end the run at the first speech and queue clips as announcements instead, the wake word and
the stop word keep working, speech can arrive minutes later, and the device can ask a question and listen. See
[architecture](architecture.md#why-replies-are-announcements-not-a-pipeline-response).

**`<speak>` tags instead of a second model that rewrites the answer.** An extra model pass adds latency and cost to every
turn. One instruction to the agent plus a parser costs nothing. Our first version of the instruction was too weak: the model
sometimes put a one-line intro in the tags and the real answer outside, which sounded like silence. Saying that the spoken
part must contain the answer itself fixed it. If it ever comes back, the fallback is to speak a trimmed version of the reply
and say the details are in the chat.

**Acknowledgements are canned, not generated.** A model-written acknowledgement needs a model call before the first word.
Pre-rendered lines ("One moment, sir.") play instantly and cost nothing. The agent's own spoken line before a tool call is
better ("Checking your calendar"), and it arrives when the agent is actually about to do something.

**Routing is a time rule first and a model second.** Within a few minutes the same conversation continues with no model
call. Only after that does a small decision model pick among conversation *titles* (not contents), so the common case adds
nothing and the rare case adds a quarter of a second. It resumes a conversation only above a confidence threshold, and when
unsure it starts a new one. A wrong "new" is cheap, since you can continue it later. A wrong match pollutes the wrong
context.

**Ask the server to filter.** Listing sessions unfiltered took 1 to 5 s, and scheduled jobs dominated the list, pushing real
conversations out of the newest 100. Filtering by source on the server brought the same lookup down to 0.02 s.

**Stop means "be quiet", not "cancel".** Cancelling a half-finished agent job by accident is worse than letting it finish. So
stop clears the queue, and a generation counter drops the rest of the reply that is still streaming in. The job and its full
answer stay in the chat.

**The stop-word model is enabled while the device speaks.** The stock firmware turns it on from pipeline events only. With
announcements those events never happen, so the model never ran. The firmware now enables it for as long as anything is
announcing, and keeps it on for 2 s across the gaps between clips.

## Things that cost us time

- Home Assistant has to disconnect from the device. If it stays connected, it answers the wake word and the bridge never
  hears anything.
- ESPHome honors voice-assistant commands only from the connection that subscribed to the voice stream. If a second tool
  sends the same command, it is silently ignored and times out.
- Opening the device's serial port resets it, and the API connection then needs the 5 s keepalive to notice and resubscribe.
- The firmware's wake word sensitivity select overrides the per-model cutoff for the stock models, so editing a cutoff in a
  manifest changes nothing for them.
- A wake-word model that scored 1.0 on the target phrase also scored 1.0 on "Hey Travis" and on TV speech. Training on
  synthetic samples alone makes near-misses fire. Real recordings and hard negatives are what help.
- Hermes reads its API key from a `.env` file that overrides the environment, and it takes minutes to restart.
- Piper voices differ in natural pace by tens of percent. Measure a voice's words per minute (trimmed speech time) instead of
  guessing, then set `length_scale` to match.
