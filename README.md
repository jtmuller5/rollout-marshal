# Rollout Marshal

An agent that owns a mobile app release from the moment it goes out to the moment it is
either at 100% or halted.

A staged rollout is a decision nobody wants to make at 2am. The build is at 20% on Play,
the crash-free rate just moved, and somebody has to widen, hold, or halt. Rollout Marshal
polls the Play Developer API and Sentry release health, judges what it reads against a halt
number that was written down *before* the release went out, and then acts on the store
account: widen the stage, halt the rollout, or ship a Dart-only hotfix through Shorebird.
It emails the human afterwards, not before.

It ends in a store write, not a recommendation. Halting a rollout is irreversible
in the sense that matters, because the users who already updated have the build, and it is
the action a person is otherwise paid to sit and wait to take.

> Built by an autonomous agent working for Joe Muller. The code, the diagrams and this
> README were written by that agent; the accounts, the apps and the money are Joe's.

The hackathon write-up, which is the same text as the Devpost submission, is in
[`SUBMISSION.md`](SUBMISSION.md). The hosted page is at
http://joemuller.com/rollout-marshal/.

---

## Status

The spine runs. One command takes a policy, a staged release and a crash spike through
two ticks, and the second one halts the rollout, writes the audit trail and sends the
email:

```bash
git clone https://github.com/jtmuller5/rollout-marshal.git
cd rollout-marshal
uv venv && uv pip install -r requirements-dev.txt   # requirements.txt alone runs the demo
bash demo/run_demo.sh
```

Those four commands were run against a fresh clone on 2026-08-13, on Python 3.13 and an
empty environment: the install takes a few seconds, the demo prints the halt and exits 0,
and the tests pass in about six seconds. `pip install -r requirements-dev.txt` in a
`python -m venv` works the same way if you would rather not install `uv`.

That runs on a clean checkout with no credentials at all, because every outside edge has
a fixture behind the same interface as the real thing. Five environment variables swap
them one at a time:

| Variable | Default | The real thing |
|---|---|---|
| `MARSHAL_BRAIN` | `scripted` | `adk`, Gemini 3.5 through ADK |
| `MARSHAL_PLAY` | `fixture` | `live`, Play Developer API writes |
| `MARSHAL_CRASH_FEED` | `fixture` | `sentry`, live release health |
| `MARSHAL_STORE` | `file` | `firestore` |
| `MARSHAL_SCRIBE` | `template` | `gemma`, `gemma-4-31b-it` writes the email |

What has been exercised, and what has not, as of 2026-08-14:

- **The agent, on the real model.** `MARSHAL_BRAIN=adk` runs the whole tick on Gemini 3.5
  Flash. On the first tick it proposed WIDEN, the gate refused it on the session floor,
  and it accepted the refusal and held; on the second it proposed HALT and the halt was
  written. Both reasonings are in the decision log.
- **The Play client, writing to a real store account.** On 2026-08-13 one tick with
  `MARSHAL_PLAY=live`, `MARSHAL_STORE=firestore` and `MARSHAL_BRAIN=adk` halted a real
  rollout: Gemini proposed HALT, the gate confirmed the breach, and the executor committed
  edit `06187374055212919847` against `com.mullr.abis_recipes` on the `alpha` closed
  testing track, which went from `inProgress` at 20% to `halted` at 20%. The write took 3
  seconds of the 58-second tick; the rest is model latency. The decision document in
  Firestore carries that edit id. The call sequence is written up in
  `notes/play-write-path.md`.
- **Two more Google models, both on the same key.** `MARSHAL_SCRIBE=gemma` has
  `gemma-4-31b-it` write the opening paragraph of the email; it took 47.1s and 49.4s on
  the free tier, which is why the timeout is 90 seconds and why a refusal falls back to a
  template that says so in the mail. `gemini-2.5-flash-preview-tts` spoke all twelve
  narration cues at 24kHz, and every one was transcribed back and checked against the
  script. That model allows three requests a minute, so `demo/narrate.py` paces itself.
- **Firestore, for real.** `MARSHAL_STORE=firestore` runs the whole of shot 4 against a
  live database on project `gen-lang-client-0325469250`: policy, rollout, the halt, and
  the append-only decision log read back. It is on the free tier and cannot bill. The one
  composite index it needs is in `firestore.indexes.json`.
- **The container, for real.** `docker build` produces a 251 MB image; running it serves
  `/healthz` and `/decisions/{app}` off that Firestore database.
- **Not yet: the Cloud Run deploy and Cloud Scheduler.** Both APIs refuse to enable on a
  project with no billing account, and the loop's spend cap is $0.00, so this waits on
  Joe. `notes/deploy.md` has the measurement and the exact commands.
- **The project page, generated from the log.**
  `python -m rollout_marshal.cli publish --app bakedown` reads the policy, the rollout and
  every decision out of whatever store the environment points at, and writes
  `docs/index.html`. Published against Firestore, the page leads with the live halt and
  the Play edit id that halt committed; published after `demo/run_demo.sh`, the same page
  says fixture in the same words. It refuses to build when the log is empty, so it cannot
  keep claiming a halt that has stopped happening. GitHub Pages serves `docs/`.
- **The take, recorded rather than described.** `bash demo/record_take.sh` films shot 4 (the
  refused widen, the injected spike, the halt, the audit trail) to an mp4, with no
  camera and no desktop: a browser on a virtual X display, `ffmpeg` reading that display,
  and the real service driving the page. Run live on 2026-08-13 it produced a 78-second
  continuous capture in which Gemini's own reasoning, the gate's verdict and Play edit
  `10688190058094298396` are all legible, and the track pill flips to `halted` on an
  independent read of the API three seconds after the write. The clock in the corner is
  the browser's and never stops, which is how someone who was not there can check that
  nothing was cut. Fixtures are the default, so the same command rehearses it with no
  credential. A take that stops on a beat that did not happen puts the release back to
  `halted` itself and says so on camera, which was proved against the real API on
  2026-08-13: resume as edit `04142531536641645176`, the driver's own undo as edit
  `05826247871260134620` eighteen seconds later, and a second call wrote nothing.
- **The narration, spoken and measured.** `python demo/narrate.py` reads the shooting
  script in `notes/demo-script.md`, speaks its twelve cues with Gemini 2.5 Flash TTS, and lays
  them on the video's own clock: a 3:55 audio bed, subtitles that match it, and one wav
  per line so any of them can be replaced by a human read without re-timing the rest.
  Measured on 2026-08-13, that is 453 spoken words across nine beats inside 3:55, and the
  tool exits non-zero when a beat has more words than its heading allows. It did that
  twice, and the script was shortened instead of the pauses. The script is now the timing
  sheet as well as the prose, so `tests/test_narration.py` holds its headings to tiling
  shot 4's window exactly. Every cue was transcribed back with Whisper and checked against
  the script it came from, because a wav of the right length is not a wav that says the
  words. Neither speech engine is a dependency of this repo; `--dry-run` budgets the cut
  with the standard library alone.
- **The cut, assembled from the same clock.** `python demo/assemble.py` reads the shooting
  script's windows, the ones the narration is already laid on, and fills each with the
  picture named in `demo/cut.json`, so the voice and the picture cannot drift apart. A shot
  nobody has filmed yet becomes a placeholder card saying who owes it, which keeps the cut
  full length and makes swapping the real shot in a one-line change. It refuses two things
  on purpose: a clip shorter than its window, and any attempt to pad a clip marked
  `unedited`. Freezing a frame to cover a gap in shot 4 would make the video lie about
  being an unedited live execution, so the fix for a short take is to record it again.
- **Not yet: shots 1 and 5, and the finished cut.** Those two are pans of the Play Console
  and the Google Cloud console on a logged-in browser, so they are the human's. Everything
  around them is in the can.
- **Not yet: the Shorebird patch.** It stays marked as not built in the diagram below.

Read `notes/experiments.md` for what has been tried and `notes/demo-shot-list.md` for
what the video needs.

### The tests

```bash
.venv/bin/python -m pytest tests -q      # 106 tests, about six seconds, from the repo root
```

`pytest` is in `requirements-dev.txt` rather than `requirements.txt`, so a runtime install
carries no test dependency into the Cloud Run image.

They cover the gate rule by rule and one whole tick with every collaborator faked. They
also cover the parts the camera sees: the four operator commands that set the release up,
the HTTP surface the demo is filmed through, `/stream` included, and `demo/run_demo.sh`
itself, run end to end on a free port and read shot by shot.

Nine of them are about the published page. Change a reading in the store and the page has
to change with it; empty the log and there must be no page at all; and a fixture Play
client must never be reported as a real edit. One of them parses the node labels out of
the README's mermaid blocks and looks for each of them in the SVG beside it, so a diagram
that renders but says the wrong thing fails here.

Two of them are about the recording, not the code. The shooting script speaks the
halt number and the session counts out loud, so `tests/test_demo_path.py` reads those
numbers out of the fixtures and the `policy set` flags, and requires
`notes/demo-script.md` to still say them. Edit a fixture without them and every test
stays green; the take is wasted at the cut instead.

No test can reach a real account. `tests/conftest.py` clears every variable that selects
a live edge, the SMTP settings among them, and points the rest inside a temporary
directory.

---

## Architecture

The diagram draws what has run, not what is planned. The three groups say where a box is:
inside the container, on Google Cloud, or designed and not yet deployed. Every dashed box
is in that last group. The project has no billing account, so Cloud Run, Cloud Scheduler
and Secret Manager refuse to enable on it (the Status list above, and `notes/deploy.md`).
Today the container is started by hand and the tick is an HTTP POST.

```mermaid
flowchart TB
  subgraph SVC["marshal — one container, run by hand today"]
    direction LR
    ADK["ADK agent — Rollout Marshal<br/>Gemini 3.5 Flash"]
    GATE["Policy gate<br/>deterministic Python"]
    TOOLS["ADK FunctionTools<br/>play_state · crash_free · policy<br/>widen · halt · patch · notify"]
    SCRIBE["Scribe — gemma-4-31b-it<br/>no tools, no credential<br/>runs after the write"]
    ADK -->|"proposes one action"| GATE
    GATE -.->|"refused + reason"| ADK
    GATE -->|"allowed"| TOOLS
    TOOLS -->|"tool results"| ADK
  end

  subgraph GCP["Google Cloud — called by every tick that has run"]
    direction LR
    GEM["Gemini API<br/>gemini-3.5-flash · gemma-4-31b-it"]
    FS[("Firestore<br/>policies · rollouts · decisions")]
  end

  subgraph TODO["Designed, not deployed — the project has no billing account"]
    direction LR
    SCH["Cloud Scheduler<br/>every 10 min · one job per app"]
    CRUN["Cloud Run<br/>would host this container"]
    SM["Secret Manager<br/>today the keys are environment variables"]
  end

  TICK["POST /tick<br/>by hand, or demo/run_demo.sh"]
  PLAY["Play Developer API v3<br/>edits.tracks get · patch · commit"]
  SENTRY["Sentry release health<br/>crash-free rate + sessions"]
  SB["Shorebird · not built<br/>Dart-only patch"]
  MAIL["Email to the human<br/>opening paragraph by Gemma"]

  TICK -->|"the heartbeat today"| ADK
  SCH -.->|"the heartbeat once deployed"| ADK
  ADK <--> GEM
  TOOLS <--> FS
  TOOLS <-->|"read state · write userFraction"| PLAY
  TOOLS --> SENTRY
  TOOLS -.->|"hotfix"| SB
  TOOLS -->|"after the fact"| SCRIBE
  SCRIBE --> MAIL
  SCRIBE <--> GEM

  classDef ext fill:#ffffff,stroke:#777;
  classDef todo fill:#ffffff,stroke:#777,stroke-dasharray:4 3;
  class PLAY,SENTRY,MAIL,TICK ext;
  class SB,SCH,CRUN,SM todo;
```

### What runs where

| Component | Where it runs | Deployed? | What it is responsible for |
|---|---|---|---|
| `marshal` service | One container, started by hand | Runs, off Cloud Run | Holds the agent, the tools and the gate. Stateless: every fact it uses comes from Firestore or an upstream API on the tick it runs. |
| ADK agent | Inside the service | Runs | Reads the evidence, states the halt number, states the measured rate, and proposes exactly one action per tick with the reasoning attached. |
| Policy gate | Inside the service, plain Python | Runs | Re-checks the preconditions itself before any irreversible call. The model never reaches the Play API directly. |
| Gemini 3.5 Flash | Google Cloud, Gemini API | Called by every tick | The judgement. It reads the numbers and proposes the action. |
| Gemma 4 31B | Google Cloud, Gemini API | Called after an action | Writes the opening paragraph of the email. It has no tools and no credential, and it runs after the store write, so nothing it says can change what was done. |
| Firestore | Google Cloud | Live, free tier | The pre-declared policy per app, the current rollout state, and an append-only decision log that is also the audit trail. |
| The tick | `curl`, or `demo/run_demo.sh` | Runs | The heartbeat, by hand for now. One POST per app per tick. |
| Cloud Run | Google Cloud | **Not deployed** | Would host the same container, scaled to zero. Blocked on billing, not on code. |
| Cloud Scheduler | Google Cloud | **Not deployed** | Would replace the hand-typed tick. One job per watched app, so a wedged app cannot stall the others. |
| Secret Manager | Google Cloud | **Not deployed** | Would hold the Play service-account key and the Sentry token. They are environment variables today. |
| Cloud Build → Artifact Registry | Google Cloud | **Not deployed** | Would build and store the image. It is the deploy path rather than the run path, so it is not in the diagram. |

### Why the gate exists

The agent is genuinely deciding. It reads the numbers and picks the action. But a language
model that has talked itself into widening a bad release is a language model that ships a
bad release to four times as many people. So every write goes through code that re-derives
the same conditions from the same Firestore documents, and refuses the call if they do not
hold. When the gate refuses, the refusal and its reason go back to the agent as a tool
result, which is usually what makes it halt instead.

The gate enforces four things, none of them negotiable by prompt:

- **The halt number was written down first.** No policy document in Firestore, no rollout.
- **Widening needs both conditions**, never either: at least six hours at the current stage,
  and a crash-free session rate no worse than the pre-release baseline.
- **A session floor.** At 20% of a small app a fresh release may have a handful of sessions,
  and "100% crash-free over 9 sessions" says nothing. Below the floor the answer is "wait",
  not "widen". The floor gates widening only. A breach halts at any volume, because halting
  is cheap and nobody new is affected by an unnecessary one.
- **One concurrent rollout per app.** A second release cannot start while the first is
  still climbing.

## The decision, one tick at a time

```mermaid
sequenceDiagram
  autonumber
  participant S as The tick — POST /tick
  participant A as ADK agent (Gemini)
  participant G as Policy gate
  participant P as Play Developer API
  participant Y as Sentry
  participant F as Firestore

  S->>A: POST /tick {app}
  A->>F: read policies/{app} — halt number, stage ladder
  A->>P: edits.insert → tracks.get → edits.delete
  P-->>A: track=production status=inProgress userFraction=0.2
  A->>Y: sessions?field=crash_free_rate(session)&groupBy=release
  Y-->>A: 76.9% crash-free over 412 sessions
  A->>A: measured 76.9% is below the declared 95.0%
  A->>G: propose HALT, with both numbers
  G->>F: re-read policy, confirm the breach independently
  G->>P: edits.insert → tracks.patch status=halted → edits.commit
  P-->>G: halted
  G->>F: append decisions/{ts} — inputs, decision, API response
  G-->>A: halted at 20%
  A->>A: file the hotfix, then notify
```

The failure path is the interesting one, so it is the path drawn. The happy path, widening
0.2 to 0.5, is the same shape with a different gate outcome.

Those numbers are not invented for the diagram. A real app in this portfolio shipped a
release that ran at 76.9% crash-free against a 95% line and was halted by hand within
hours. That is the judgement being automated, and the ground truth the demo runs against.

## Data model

```
policies/{app}          declared before a release, immutable for its duration
  halt_crash_free       95.0
  stages                [0.2, 0.5, 1.0]
  min_hours_per_stage   6
  session_floor         120
  baseline_crash_free   99.4

rollouts/{app}          current state, one document, overwritten each tick
  version_code, track, status, user_fraction, stage_entered_at, policy_ref

decisions/{ts}          append-only; the audit trail and the demo's right-hand pane
  inputs {crash_free, sessions, hours_at_stage, halt_criterion}
  proposal, gate_verdict, action_taken, api_response, model_reasoning
  attempts[]            every proposal this tick, in order, with the gate's answer
```

`attempts` is there because a refused proposal is the part worth keeping. A tick that
wanted to widen, was refused on the session floor and then held is a different event
from a tick that simply held, and only the first one tells you the policy did work.

`decisions/` is append-only on purpose. It is what makes "the agent acted while nobody was
watching" reviewable after the fact, and it is what the demo video reads from.

## Required technologies

The contest requires all three. Each one is load-bearing here, not added to qualify.

| Requirement | How it is met | Why it is not decoration |
|---|---|---|
| Gemini 3.5 or newer | Gemini 3.5 Flash through the Gemini API | It reads the evidence and picks the action. Remove it and there is a cron job with an if-statement. |
| A Google agent framework | ADK | Tools, the tool-result loop, and the gate's refusal coming back as a tool result the agent has to respond to. |
| A Google Cloud infrastructure service | Firestore, live and holding every decision the agent has made. Cloud Run, Cloud Scheduler and Secret Manager are designed and blocked on billing. | The policy, the rollout state and the audit trail outlive any one tick, and a rollout takes days. There is nowhere for that state to live inside the process. |

Everything above sits inside free tiers: Firestore on Spark, the Gemini API on a project
with billing switched off, and, once it can be enabled, Cloud Run scaled to zero and
Cloud Scheduler's first three jobs.

## Repository layout

```
rollout_marshal/
  server.py       the Cloud Run service: POST /tick/{app}, GET /stream, /decisions, /healthz
  tick.py         one tick, start to finish, and the collaborators it holds
  agent.py        the ADK agent on Gemini 3.5, and a scripted control that uses no model
  tools.py        the four functions the model can call, bound to one tick
  gate.py         the policy gate. Pure Python, no I/O, no prompt input
  executor.py     the only module that performs a store write
  play.py         Play Developer API v3, and a fixture with the same behaviour
  crash.py        Sentry release health, and a fixture that can be swapped mid-run
  store.py        Firestore, and a JSON-file store with the same three collections
  notify.py       the email, sent after the action
  models.py       the values that move through a tick
  cli.py          declare a policy, seed a track, inject a reading, run a tick, publish
  publish.py      the hosted page, generated from the decision log
demo/
  run_demo.sh     shot 4, end to end, on one command
  render_diagrams.py  the two mermaid blocks above, rendered to docs/assets/*.svg
  fixtures/       quiet · spike · healthy — the three readings the demo uses
docs/             the GitHub Pages site: index.html and the diagrams it inlines
tests/            the gate's rules one by one, a whole tick, the CLI, the HTTP
                  surface, and demo/run_demo.sh run end to end
Dockerfile        the Cloud Run image
requirements.txt      what the service needs to run
requirements-dev.txt  the same, plus pytest, for the suite above
notes/            the shot list, the measured Play write path, the experiment log
```

The package is `rollout_marshal` instead of `marshal` because `marshal` is a Python
built-in module and shadows any package of that name.

## Licence

MIT, in `LICENSE`. Copyright Joe Muller.
