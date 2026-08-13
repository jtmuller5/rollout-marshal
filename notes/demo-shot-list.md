# The demo, shot by shot

Written before the code, on purpose. Every shot below names what rung 2 has to build for
that shot to exist, so the spine gets built toward a video that already works on screen
rather than filmed around whatever happens to run in the last week.

**Hard limits from the rules page** (read 2026-08-13 at
`allthingsagentichackathon.devpost.com/rules`): four minutes, and only the first four are
evaluated. Public on YouTube or Vimeo. English. It has to show the problem, the value, the
app in action, and visual proof that the backend runs on Google Cloud — a Cloud Run
dashboard, Vertex AI logs or a `.run` URL are the examples the rules give.

## What the video is scored on

Three weighted criteria, from the same page. Each shot below carries the one it is aimed at.

| Weight | Criterion | What the judge is told to look for |
|---|---|---|
| 40% | Innovation & Operational Utility | Does it kill real friction? "High-value, autonomous execution over simple chat queries." For our category: does the agent intercept and finish a multi-step background workflow with no human in it, and is it the entrant's own friction (the BYOF mandate)? |
| 30% | Architectural Discipline & Tech Stack | Decoupling, state management, failure tolerance. "Are the tools properly isolated and scoped for security?" |
| 30% | Demo & Production Readiness | A clear four-minute explanation, **an unedited live execution**, a clean diagram, reproducible setup, and visible Google Cloud deployment. |

Two things follow from that table and they decide the whole cut.

**The centrepiece has to be one unedited take.** "The Proof of Action" is written into a
criterion worth 30%, and a cut in the middle of the halt reads as the thing being hidden.
So the middle 110 seconds are one continuous screen recording with a running clock in
shot, and every other shot is arranged around not needing to interrupt it.

**The category is Taskmaster.** The rules name three categories — Taskmaster, Collaborative
Partner, Fortified Enterprise Fleet — and the 40% criterion describes them under older
names, ours being "The Continuous Action Engine". Taskmaster asks for "a messy, multi-step
chore in your job or personal life" handled end to end, which is what a staged rollout is.
It also has its own $20,000 prize.

## The friction, in one sentence

A staged rollout is a job that runs for days and needs a judgement every few hours, so a
person ends up watching a dashboard at 2am to make a decision that is written down in
advance anyway. That sentence is the cold open and it is also the BYOF answer: it is Joe's
own release process, on Joe's own app.

## The shot list

Times are cumulative. Anything that overruns is cut from shot 6 first, then shot 3.

### 1 — Cold open: the 2am decision · 0:00–0:22 · *40%*

**On screen.** Full-frame screen recording of the Play Console rollout page for a real app.
Production-style staged rollout at 20%, and beside it the crash-free session rate. No
narrator on camera, no title card yet.

**Spoken.** "This is a release going out to real users, twenty percent at a time. Every few
hours somebody has to look at this number and decide: widen it, hold it, or halt it. The
rule is written down before the release ships. The person still has to be awake at 2am to
apply it."

**Rung 2 owes.** Nothing. This shot is a recording of a console that already exists.

### 2 — The number was written down first · 0:22–0:45 · *40% and 30%*

**On screen.** Cut to the Firestore console, `policies/{app}` open: `halt_crash_free 95.0`,
`stages [0.2, 0.5, 1.0]`, `min_hours_per_stage 6`, `session_floor 120`. The document's
"created" timestamp is visible and it is older than the rollout.

**Spoken.** "Rollout Marshal starts from a policy the human wrote before the release went
out. Ninety-five percent crash-free is the halt line. Nothing about that is the model's to
decide."

**Rung 2 owes.** The `policies` collection, written by a small CLI, with a real document
for the demo app.

### 3 — The architecture · 0:45–1:20 · *30%*

**On screen.** The README's component diagram, held still, with three highlights drawn on
in sequence: the ADK agent, the policy gate, the Play API. Then a two-second flash of the
sequence diagram.

**Spoken.** "Gemini 3.5 through Vertex AI reads the evidence and proposes one action. Every
action then goes through a policy gate — plain Python, no model — that re-derives the same
conditions from Firestore and refuses the call if they do not hold. The model never holds a
Play API credential. It runs on Cloud Run, on a Cloud Scheduler tick, with Firestore for
state and an append-only decision log."

**Rung 2 owes.** Nothing new; the diagram is committed. It has to still match the code by
the time this is filmed.

### 4 — The unedited take · 1:20–3:10 · *40% and 30%*

One recording, no cut, clock visible in a corner. Split screen: Play Console left, the
agent's streamed decision log right. Four beats inside it.

**4a · A tick that does nothing · ~25s.** Scheduler fires. The right pane shows the agent
reading the track state and the crash-free rate, then proposing WIDEN to 50%. The gate
refuses: 41 sessions is under the floor of 120. The refusal comes back as a tool result and
the agent's next line accepts it and waits.

*Spoken:* "First tick. The agent wants to widen, and the gate says no — forty-one sessions
is not enough evidence to widen on, whatever the percentage says. The refusal goes back to
the agent as a tool result, and this is the part most agents skip: it has to respond to
being told no."

**4b · The spike · ~10s.** The crash feed is switched to the fixture carrying the real
incident: 76.9% crash-free over 412 sessions. This is stated out loud as an injection.

*Spoken:* "Now I inject a crash spike into the telemetry feed. These are real numbers from
a real release in this portfolio that ran at 76.9 percent against a 95 percent line."

**4c · The halt · ~45s.** Next tick, same pane. The agent states the declared number, states
the measured number, proposes HALT. The gate re-reads the policy, confirms the breach on
its own, and calls `edits.insert → tracks.patch status=halted → edits.commit`. The raw API
response is on screen. Then the Play Console tab on the left is refreshed **in the same
take** and reads halted.

*Spoken:* "Declared 95. Measured 76.9 over 412 sessions. It proposes a halt, the gate
confirms the breach independently, and it writes to the Play Developer API. That is a real
store account, and this is the console refreshing."

This beat was rehearsed live on 2026-08-13, so the take has a clock: the whole tick took
**58 seconds** and the Play write **3 seconds** of it, the rest being two Gemini calls. Plan
4c at about a minute of real time, not 45 seconds, and do not cut the wait — the pause is
the model thinking, and it is the part that proves nothing is scripted. Setting it up costs
one command before the take (`MARSHAL_PLAY=live python demo/live_alpha.py set inProgress
0.2`), because Play will not let a release be taken off a track.

**4d · The audit trail and the email · ~20s.** Scroll the new `decisions/{ts}` document:
inputs, proposal, gate verdict, action taken, the API response, the model's reasoning. Then
the email landing in an inbox, timestamped after the halt.

*Spoken:* "Every input it used, what it proposed, what the gate allowed, and what the store
said back. The human gets the email after the fact, not before. That is the whole point:
nobody was watching."

**Rung 2 owes** — this is the spine, and it is the only shot that cannot be faked:

- The Cloud Run `/tick` endpoint, the ADK agent, and the streamed log the right pane reads.
- The gate, including the session-floor refusal path, since 4a depends on a refusal.
- Real `tracks.patch` writes against a real Play track. **Task #1032 proves this, and until
  it passes, the demo above is a story.** In particular it has to establish that a testing
  track supports `userFraction` and a halt the same way production does.
- A crash-feed interface with two implementations, live and fixture, swappable at 4b.
- The email.

### 5 — Proof it runs on Google Cloud · 3:10–3:35 · *30%*

**On screen.** Four quick pans, no narration over the first two: the Cloud Run service page
showing the revision and its `.run` URL; the request log with the tick that just ran, the
timestamp matching shot 4; the Vertex AI call in the logs; the Cloud Scheduler job with its
last-run status.

**Spoken.** "This is not running on my laptop. Cloud Run, scaled to zero between ticks;
Vertex AI; Cloud Scheduler; Firestore; the Play key in Secret Manager, never in the image."

**Rung 2 owes.** A real deploy. The timestamps have to line up with shot 4, so this is
filmed straight after the take, not another day.

### 6 — The hotfix, then out · 3:35–3:55 · *40%*

**On screen.** The agent filing the hotfix and shipping a Dart-only Shorebird patch, sped up
with a visible speed indicator. Then the disclosure card.

**Spoken.** "Halting is only half the job, so it files the fix and ships it as a
Dart-only patch — no store review, minutes to reach devices. Rollout Marshal was built by an
autonomous agent working for Joe Muller. The accounts, the apps and the release it halted
are his."

**Cut this shot first if the video is long.** The patch path is marked "not built yet" in
the README and it is the least defensible thing to promise on camera.

## What is real and what is a fixture

The write-up says this too, in the same words. A seam is allowed; hiding it is not.

| Real | Fixture |
|---|---|
| The Play Developer API calls, against a real account and a real track | The crash spike in shot 4b, injected deliberately and said out loud |
| The agent, the gate, the Gemini calls, the Firestore writes | |
| The Cloud Run deploy and every console shot in 5 | |
| The 76.9% figure, which is a measurement from a real halted release | |

## Rules this cut is built on

- **The halt path is the demo because it needs no clock.** Widening requires six hours at
  the stage, and six hours cannot be filmed. Halting is valid at any moment. The demo is
  the branch that fits inside four minutes without a cheat.
- **The refusal is the differentiator, so it comes before the halt.** An agent that shows
  what it may not do is memorable, and almost nobody demos it. Putting 4a first also means
  the halt in 4c reads as a judgement rather than the only thing the thing can do.
- **Nothing gets narrated over the API response or the console refresh.** Those two seconds
  are the evidence, and a voice over them sounds like cover.
- **Record a rough cut at rung 2**, against whatever exists then. The first take is always
  worse than expected and the second one needs a day that will not be there in the last week.
