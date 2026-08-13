# Rollout Marshal: the Devpost write-up

The text of the submission, kept in the repo and not only in the form, so every claim
sits beside the code that has to back it and a run that changes a number changes this file
too.

**Category: Taskmaster** (called *The Continuous Action Engine* in the judging criteria).
A staged app rollout is a messy multi-step chore that runs for days, and this entry takes
action on it rather than reporting on it.

| Part | Where |
|---|---|
| Hosted project | http://joemuller.com/rollout-marshal/ |
| Repository | https://github.com/jtmuller5/rollout-marshal (MIT) |
| Architecture diagram | On the hosted page, rendered from the mermaid in `README.md` |
| Demo video | Recorded to the shooting script in `notes/demo-script.md`. Link goes here at submission. |
| Spin-up | `README.md`, four commands from `git clone`, no credentials |
| Build write-up (bonus) | http://joemuller.com/rollout-marshal/build-log/, source in `notes/build-writeup.md` |

> Built by an autonomous agent working for Joe Muller. The code, the diagrams, this page
> and this write-up were written by that agent; the accounts, the apps and the money are
> Joe's.

---

## Inspiration

The friction is Joe's own and it is why this exists.

A Flutter app in his portfolio shipped version 1.3.0 to Google Play. The rollout went out
at 20%, and the crash-free session rate came back at 76.9% against a line of 95% that had
been written down before the release. Somebody had to read those two numbers, know which
one was the rule, and halt the release. It was halted by hand within hours. The expensive part
was not the halt itself, which took a couple of minutes. It was a person checking a
dashboard on a schedule for something that usually has not happened.

That is work an agent should do instead of advise on. The evidence arrives on its own
schedule over several days, the decision is small and repeats, and the useful output is a
write to a store account instead of a paragraph telling somebody to go and make one.

## What it does

Rollout Marshal owns a mobile release from the moment it goes out to the moment it is
either at 100% or halted.

On every tick it reads the live state of the release from the Play Developer API, reads the
crash-free session rate and session count from Sentry release health, reads the policy that
was declared before the release, and proposes exactly one action: widen the stage, hold, or
halt. A deterministic gate re-derives the same conditions from the same documents and
either performs the write or refuses it with a reason. Then it writes an append-only
decision record and emails the human, after the fact.

What it is doing when it halts is committing a Play edit against a real store account. On
2026-08-13 it did that: one tick with the real model, the real store and the real database
took `com.mullr.abis_recipes` on the `alpha` track from `inProgress` at 20% to `halted`,
committing edit `06187374055212919847`. The write took 3 seconds of a 58-second tick; the
rest was model latency. That is in the decision log, and the hosted page is generated out
of that log instead of typed by hand.

Four things it does that a cron job with an if-statement does not:

- **It will not start without a rule.** No policy document, no rollout. The halt number is
  declared before the release and is immutable for its duration, so the number can never be
  chosen after the data arrives.
- **It refuses its own good ideas.** Widening needs both conditions and never either: six
  hours at the current stage and a crash-free rate no worse than the pre-release baseline.
  It also needs a session floor, because 100% crash-free over 9 sessions says nothing.
- **It keeps the refusals.** A tick that wanted to widen, was refused on the session floor
  and then held is a different event from a tick that simply held, and only the first one
  shows the policy did any work. Both are in `attempts[]` on the decision.
- **It tells the human afterwards.** The email carries what was decided, on what numbers,
  and the API response the store gave back.

## How we built it

The service is one container holding four parts that do not know much about each other.
It is built for Cloud Run and runs by hand today, because the project has no billing
account.

**The agent** is an ADK `LlmAgent` on Gemini 3.5 Flash with four function tools bound to
one tick: read the Play state, read the crash feed, read the policy, propose an action. It
is told to reach one proposal per tick with its reasoning attached. It runs through the Gemini API on a project with billing
switched off. The same ADK client can read the model from Vertex AI instead, which is a
credential change and not a code change, but this project has never run that path.

**The gate** is plain Python with no I/O, no clock and no text input. It takes the policy,
the rollout and the reading as values and returns allowed or refused with a reason. That
purity is the reason every rule in it is asserted in the test suite instead of demoed. The
model never reaches the Play API: the gate does, through an executor that is the only
module in the repo permitted to perform a store write.

**The state** is three Firestore collections. `policies/{app}` is the rule declared first.
`rollouts/{app}` is one document overwritten each tick, so the service itself is stateless
and any tick can be the first one. `decisions/{ts}` is append-only and is both the audit
trail and the right-hand pane of the demo.

**Every outside edge is an interface with a fixture behind it**, and one environment
variable each chooses between them: `MARSHAL_BRAIN`, `MARSHAL_PLAY`, `MARSHAL_CRASH_FEED`,
`MARSHAL_STORE`. All four default to the safe side, which is why a clean clone runs the
whole demo with no credential and cannot touch a store account by accident. It is also what
made the real halt cheap to reach: the fixture and the live Play client are the same
interface, so switching to the real one was a variable rather than a rewrite.

The demo is a shell script, so no presenter has to remember a sequence. `bash
demo/run_demo.sh` declares the policy, seeds a track at 20%, runs a quiet tick that ends in
a refusal and a hold, injects the spike, runs a second tick that halts, and reads the
decision log back.

## Data sources

- **Google Play Developer API v3**, `edits.insert → tracks.get → tracks.patch →
  edits.commit`. Read for the release state, written for the halt and the widen. The call
  sequence and the raw bodies are in `notes/play-write-path.md`, measured against a real
  closed testing track.
- **Sentry release health**, the sessions endpoint grouped by release, for the crash-free
  session rate and the session count the floor is measured against.
- **Firestore**, for the policy, the rollout and the decision log.
- **Fixtures** in `demo/fixtures/`: quiet, spike and healthy. They are the readings the demo
  runs on, and the honesty rule around them is enforced in code and not by care: a page
  published from a fixture run says so in the same place the real one names the Play edit
  id.

## Challenges we ran into

**Google Play refuses two things nobody documents in the order you meet them.** A track's
first release cannot be staged, so a rollout has to exist at 100% before a percentage means
anything, and a release cannot be removed from a track by API at all. That makes the track
choice permanent, and it is why the demo runs against a closed testing track with no
testers rather than anything a customer can reach.

**Cloud Run will not enable on a project with no billing account.** Neither will Cloud
Build, Artifact Registry or Cloud Scheduler: all four answer
`UREQ_PROJECT_BILLING_NOT_FOUND`. Firestore does enable, on the free tier, and so the
database is live and the deploy is not. The container is real and was run locally against
that same database. `notes/deploy.md` holds the measurement and the exact commands the
deploy needs.

**A fresh IAM binding is not live for about a minute**, and the denial it gives in the
meantime is word for word the denial a missing role gives. That cost a working session
before it was written down.

**The gate had to be able to say no to the model and be believed.** The first version
returned a boolean, and a refused proposal left no trace, so a tick that was stopped looked
identical to a tick that had nothing to do. The refusal became a tool result with a reason
attached, which the agent then has to respond to, and the whole attempt sequence became
part of the record.

## Accomplishments

- **It halted a real release.** Not a mock and not a staging account: a Play edit committed
  against a live app, with the edit id in the audit trail and readable from the store.
- **The demo is one command and it is not a script in the theatrical sense.** `bash
  demo/run_demo.sh` reaches the halt end to end, and the tests run that script itself and
  read it shot by shot, so the take cannot drift from the code.
- **106 tests, about six seconds, from a clean clone with no credentials.** They cover the
  gate rule by rule, a whole tick with every collaborator faked, the CLI, the HTTP surface,
  the published page and the recorder. Two of them read the numbers out of the fixtures and
  require the shooting script to still speak them, so editing a fixture without the
  voiceover fails in the suite instead of at the cut. One holds the recorder to never
  seeding or wiping state while it is wired to the live store account, which is the one
  mistake in this repository that has no undo.
- **The hosted page is generated from the decision log.** It refuses to build when the log
  is empty, so it cannot go on claiming a halt that has stopped happening.

## What we learned

**The refused tick turned out to be the most useful record in the log.** It is the one
where the agent proposed the wrong action and the gate stopped it, and it is what tells a
reviewer afterwards that the policy did something. A system that logs only what happened
throws that away, and then a tick that was stopped is indistinguishable from a tick that
had nothing to do.

**Where the model helps is narrower than it looks, and that is fine.** The gate could hold
the whole decision, and on the happy path it very nearly does. What the model adds is
reading evidence that arrives in different shapes from two APIs, and stating the case in
words a human can audit at 2am. Keeping the model out of the write path is what made it
safe to let it decide at all.

**Putting the fixture behind the same interface as the real client paid for itself twice.**
Every wrong command during development hit a JSON file instead of a store account, because
the defaults point that way. And when the real halt was attempted, it was one variable
changed at a time rather than a new code path written under pressure.

**Most of the argument about whether to halt disappears once the number is written down
first.** Very little of the work here went into the prompt. It went into making the
declaration impossible to skip and impossible to edit while a release is running.

## What's next

- The Cloud Run deploy and the Cloud Scheduler heartbeat, both of which wait on a billing
  account rather than on code. The image builds and runs today.
- The Shorebird hotfix patch. Halting stops the bleeding; a Dart-only patch is the other
  half of the loop, and the diagram marks it as not built instead of implying it.
- More than one app per scheduler job, which the state model already allows because every
  tick reads its own facts.

## Built with

`google-adk` 2.6.3 · `google-genai` 2.18.0 · Gemini 3.5 Flash · Firestore (nam5, free tier)
· Cloud Run · Cloud Scheduler · Secret Manager · FastAPI · uvicorn · Python 3.13 · Google
Play Developer API v3 · Sentry release health · Shorebird · Docker

The three required technologies are load-bearing and not added to qualify: Gemini 3.5
reads the evidence and picks the action, ADK carries the tools and the refusal loop, and
Firestore holds the policy and the audit trail a multi-day rollout has nowhere else to
live.
