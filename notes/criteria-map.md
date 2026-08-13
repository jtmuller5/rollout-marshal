# What each judging criterion asks, and what answers it

The organisers' words are quoted from `https://allthingsagentichackathon.devpost.com/rules`,
sections 6 and 8, read 2026-08-13. Everything under "answer" names the file, the shot or
the measurement that backs it, so a claim here can be checked rather than believed.

Read this before writing a submission field, cutting a shot, or arguing that a piece of
work is worth doing. Work that no row below points at is work for a different project.

## Stage One is pass/fail, and it comes before any score

> "The first stage will determine via pass/fail whether the Submission meets a baseline
> level of viability, in that the Submission includes all Submission requirements,
> reasonably addresses a Challenge, and reasonably applies the requirements."

A missing part costs more than a weak one. Nine things are required.

| Required | What satisfies it | State |
|---|---|---|
| A category selected | Taskmaster. `SUBMISSION.md` names it in the first line and gives the reason. | done |
| "URL to the hosted Project (if available)… A hosted project is highly encouraged." | `http://joemuller.com/rollout-marshal/`, generated from the decision log by `rollout_marshal/publish.py`. | done |
| "A text description… features and functionality, technologies used, information about any other data sources used, and your findings and learnings" | `SUBMISSION.md`. All five headings are present, "Data sources" and "What we learned" included. | done |
| "URL to your private or public code repository" | `github.com/jtmuller5/rollout-marshal`, public, MIT. | done |
| "Spin-up Instructions: a step-by-step guide in your `README.md`" | The Status block. Proved from an unauthenticated clone: `uv venv`, `uv pip install -r requirements-dev.txt`, tests, `bash demo/run_demo.sh`. | done |
| "An Architecture Diagram with a clear visual representation of your system" | Two mermaid diagrams in `README.md`, rendered to SVG by `demo/render_diagrams.py` and inlined on the hosted page. | done |
| A demo video, "not be longer than 4 minutes", public on YouTube or Vimeo, English | `demo/assemble.py` builds it to the windows in `notes/demo-script.md`. Two shots are still slates. | **open — #1060** |
| The video "must demonstrate the backend is running on Google Cloud" | Shot 5. See the gap below; the Firestore console is the fallback that does not need a deploy. | **open — #1060, #1035** |
| The three mandatory technologies | Gemini 3.5 Flash through the Gemini API; ADK 2.6.3 `LlmAgent`; Firestore (nam5, free tier). All three have run. | done |

Two rules bind after submission as well. The project must stay "free of charge and without
any restriction" for testing until judging ends **2026-10-01**, so the repo stays public and
the page stays up. And "Projects must be newly created during the Submission Period" — any
code later lifted out of `~/projects/fun-money` must be disclosed by name in `SUBMISSION.md`
in the cycle that copies it.

## Stage Two — the three weighted criteria

Scored 1 to 5 each and averaged by weight.

### Innovation & Operational Utility — 40%

> "Does the system eliminate real-world friction? Is the 'Twist' present? We are looking for
> high-value, autonomous execution over simple chat queries."
> For The Continuous Action Engine: "Does the agent successfully intercept and complete a
> multi-step background workflow without human intervention? Did the team successfully
> utilize the 'Bring Your Own Friction' (BYOF) mandate to solve a unique, personal problem?"

| The question | The answer | Where the judge sees it |
|---|---|---|
| Real friction? | A staged rollout runs for days and needs a judgement every few hours against a number written down in advance. Joe did that judgement by hand on ParaSight 1.3.0: 76.9% crash-free against a 95% line, halted within hours. | Shot 1 and the "Inspiration" section |
| Beyond chat? | The output is a committed Play edit, not a paragraph. Edit `06187374055212919847` took Bakedown's `alpha` release from `inProgress` 20% to `halted` on 2026-08-13, against a live store account. | Shot 4c, unedited, with the console refreshing in the same take |
| Multi-step, no human in it? | One tick reads the Play track, the crash feed and the policy, proposes, is gated, writes, logs, emails. The human is told afterwards. | Shot 4a → 4d, one recording |
| BYOF? | Joe's own release process, on Joe's own app, with his own halted release as the numbers in the fixture. | Stated in shot 1 and in "Inspiration" |
| The "Twist" | The gate refuses the agent, and the refusal is kept. A tick that wanted to widen and was stopped on the session floor is a different record from a tick that had nothing to do — both are in `attempts[]`. | Shot 4a, which is placed before the halt on purpose |

**The risk on this criterion is not the demo, it is the sentence "high-value".** The halt is
one write. What makes it high-value is the watching it removes, so the video has to say the
cost in hours and not only show the write.

### Architectural Discipline & Tech Stack — 30%

> "We are evaluating your engineering decisions, not just your ability to call an API. How
> well did your team decouple systems, manage state, and design robust, failure-tolerant
> agentic systems?"
> For The Continuous Action Engine: "Did you implement a clean, modularized, ease of
> maintenance system? How does the system handle state management? Are the tools properly
> isolated and scoped for security?"

| The question | The answer | Where the judge sees it |
|---|---|---|
| Decoupling | Every outside edge is an interface with a fixture behind it, selected by one variable each: `MARSHAL_BRAIN`, `MARSHAL_PLAY`, `MARSHAL_CRASH_FEED`, `MARSHAL_STORE`. All four default to the safe side, so a clean clone runs the whole demo with no credential and cannot touch a store. | `README.md`, shot 3, and the spin-up a judge can run |
| Modularity | `rollout_marshal/` splits agent, gate, executor, store, play, crash, log, server. The gate is pure — no I/O, no clock, no text input — which is why every rule in it is asserted rather than demoed. | `tests/test_gate.py` |
| State management | Three Firestore collections. `policies/{app}` declared before the release and immutable for its duration; `rollouts/{app}` overwritten each tick, so the service is stateless and any tick can be the first; `decisions/{ts}` append-only. | Shot 2 (the policy, with a `created_at` older than the rollout) and shot 4d |
| Tools isolated and scoped for security | The model holds no store credential. It proposes; `executor.py` is the only module permitted to write, and it writes only what the gate allowed. The service account for Firestore holds `roles/datastore.user` and nothing else; the Gemini key is restricted to `generativelanguage.googleapis.com` on a project with billing disabled. | Shot 3, and `notes/deploy.md` |
| Failure tolerance | The refusal is a tool result the agent must answer, not a boolean. A take that stops on a beat that did not happen puts the Play track back itself (`restore_track`). The published page refuses to build from an empty log. | `tests/test_tick.py`, `tests/test_take.py`, `tests/test_publish.py` |

**The cut now shows the evidence, not only the intention** (#1079). Shot 3 runs 42 seconds
and ends on a full-frame panel: the pytest run made seconds before the recorder started,
and the four `MARSHAL_*` switches with the default each module actually applies. Neither
number is typed into the page — `demo/take/shot_data.py` reads the count out of the run's
own output and each default out of the `os.environ.get` line that applies it, and refuses
to render a red suite or a default that has become the live edge. The ten seconds came out
of shots 5 and 6, so the cut is still 3:55.

### Demo & Production Readiness — 30%

> "The clarity of the technical documentation and the undeniable proof of execution in the
> video pitch. Does the 4-minute video clearly define the friction being solved and explain
> the architecture? The Proof of Action: Does the video show an unedited, live execution of
> the agent performing its task (via terminal logs, database updates, or UI changes)? The
> Documentation: Does the public GitHub repository feature a clean architecture diagram and
> reproducible setup instructions? Is there visual proof of Google Cloud deployment in the
> video?"

| The question | The answer | State |
|---|---|---|
| Friction defined, architecture explained | Shots 1 to 3, to a script whose timings are data `tests/test_narration.py` holds to the cut. | shots 2 and 3 recorded |
| "Unedited, live execution" | Shot 4 is one continuous take of a real tick against the real API. `"unedited": true` in `demo/cut.json` makes `assemble.py` refuse to pad it, so a frozen frame cannot creep in. | needs one live take at `DWELL=17` |
| Clean diagram in the repo | Two mermaid diagrams, rendered and inlined; `tests/test_shots.py` checks the node ids shot 3 rings. | done |
| Reproducible setup | Proved from an unauthenticated clone. | done |
| "Visual proof of Google Cloud deployment" | Shot 5. Cloud Run cannot be deployed: it and Cloud Build, Artifact Registry and Cloud Scheduler all answer `UREQ_PROJECT_BILLING_NOT_FOUND` on a project with no billing account (#1035). | **the one real gap** |

**The deployment gap has an answer that does not need Joe's billing account.** The rules
give the examples as "ie: Google Cloud Console, Cloud Run dashboard, Vertex AI logs, URL of
.run" — the Cloud **Console** is first in that list, and Firestore in the Cloud Console is
Google Cloud, is where the state actually lives, and is already what shot 5's slate asks
for. A pan of the `policies`, `rollouts` and `decisions` collections with the demo's own
documents in them is visual proof of a backend running on Google Cloud. Cloud Run makes it
stronger and is not what makes it pass. Do not let shot 5 wait on the billing link.

## Stage Three — the bonus, and what it is worth

> "Each Submission will receive a Final score from 1 to 6, with the highest possible Final
> score being 6."

Three bonuses: 0.2 for a public build write-up, 0.2 for a social post carrying
`#AllThingsAgenticHackathon`, and "0.2 bonus points for each additional Google AI model
successfully integrated (such as Gemma, Veo, or Lyria), up to a maximum of 0.6 total bonus
points". The arithmetic settles the ambiguity in that last clause: 5 + 0.2 + 0.2 + 0.6 = 6.0
exactly, so the 0.6 cap is on the models alone and the total bonus reaches 1.0.

**1.0 on a 6-point scale is a sixth of the score, and none of it needs the product to be
better.** Both text bonuses require the disclosure sentence — "you created the piece of
content for the purposes of entering this hackathon" — or they are not scored. Publishing
either is an outward action and Joe's to press.

The cheapest extra model is the one already in the pipeline: the narration is spoken by
Kokoro, which is not Google. Swapping it, or adding a Gemma summary of the decision log,
is 0.2 each.

## What this map exposes, ranked

1. **Shot 5 is blocked on the wrong thing.** It is waiting on a Cloud Run deploy that waits
   on billing, when the Firestore console alone satisfies the wording. Highest value, and
   the only Stage One risk left.
2. ~~Nothing in the video shows the tests or the safe defaults.~~ Done in #1079: shot 3's
   last ten seconds are the isolation panel, read at record time rather than typed.
3. **The bonus is worth up to 1.0 and none of it is built.** Two of the three are writing.
4. **"High-value" is asserted, not measured.** The video says a person has to watch; it does
   not say for how many hours a rollout.
