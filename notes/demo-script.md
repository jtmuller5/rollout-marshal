# The demo script: what the judge sees, in order

`notes/demo-shot-list.md` decides the cut and why. This file is the thing you read on the
day: the narration word for word, the command typed at each beat, and the state the
machine has to be in before the recorder starts.

Written against the code as it stands at `93801c5`, not against the plan. Where the shot
list and this file disagree about what the software does, this one is right and the shot
list needs the correction.

**Budget.** 4:00 hard, and only the first four minutes are scored. The narration below is
453 words on the branch-B cut and 464 on branch A, of which only one version of shot 5 is
spoken. It is not an estimate: `python demo/narrate.py` reads this file, speaks every
line, and measures it. Branch B is **2:55 of talking inside 3:55 of video**, and the 60
seconds of difference is deliberate. It is the model thinking in 4c and the Play Console
refreshing. Do not fill it.

The total has not moved and may not: shot 3 grew by ten seconds for the isolation panel,
and those seconds came out of shots 5 and 6, which had the most silence in them. Adding a
window means taking one, because 4:00 is the contest's hard line and shot 4 is the
evidence.

Every heading below is therefore data as well as prose. The times in a `###` heading and
the `~Ns` on a `####` are what put each line on the clock, `tests/test_narration.py`
holds them to tiling shot 4's window exactly, and `narrate.py` exits non-zero when a beat
has more words than its window holds. Two beats failed that check the first time it ran,
and both were fixed here rather than in the edit: shot 2 lost two words, and 4b lost three
and borrowed two seconds from 4c.

## Three things the narration may not say

Each of these was in the shot list, and each is now false. Saying one on camera is worse
than losing the point it was aimed at, because the repo is submitted alongside the video.

| Do not say | What is true | Where |
|---|---|---|
| "Gemini through Vertex AI" | ADK talks to the Gemini API with an API key (`GOOGLE_API_KEY`). The framework requirement is met by ADK, the model requirement by `gemini-3.5-flash`. Vertex is a supported path in `agent.py` that this project has never run. | shot 3 |
| "Cloud Scheduler fires the tick" | There is no Scheduler job. The tick is an HTTP POST, and on the day it is `curl`. Scheduler cannot be enabled until billing is linked (task #1035). | shots 3, 4a |
| "It files the fix and patches it out" | The Shorebird patch path is not built and is marked as such in the README. | old shot 6 |

The Cloud Run claim in shot 5 has two versions below. Read the branch note there before
recording, because it is the one place where a blocked task costs presentation score.

## Before the recorder starts

**The day before**

1. `python -m rollout_marshal.cli policy set …` against Firestore, once. **Never inside the
   take.** `Policy.created_at` is stamped at write time, so a policy re-declared during the
   recording carries a timestamp seconds old, and shot 2's whole claim is that the number
   was written down first. Declare it, then leave it alone.
2. Watch the fixture rehearsal end to end: `bash demo/run_demo.sh`. It is the same beats
   with no credentials and no store account, and it costs nothing to run twice.
3. Build the narration bed. Gemini speaks it, three requests a minute, so twelve cues take
   about four minutes and `--resume` keeps anything already spoken:

   ```bash
   GOOGLE_API_KEY=… ./.venv/bin/python demo/narrate.py --out narration/ --resume
   ```

   With the day's requests gone, `--tts kokoro` speaks it locally on the CPU instead
   (`~/ai-server/.venv/bin/python`, which is where that model lives).

   It writes `narration/narration.wav`, a 3:55 bed with every line already at the
   position its heading gives it, `narration.srt` to match, and one wav per cue. Lay the
   bed under the cut and the picture follows the words rather than the other way round.
   **A non-zero exit means a beat has more words than its window holds.**
   Fix the script, not the mix. Any cue can be replaced by a human read of the same line without
   disturbing the rest, because each is its own file; only re-time that one.

**The morning of, at least 8 hours before the take**

3. `MARSHAL_PLAY=live python demo/live_alpha.py set inProgress 0.2` resumes the alpha
   release so shot 4 has something to halt. Play will not take a release off a track, so
   this is the only way back to the starting state and there is no undo other than
   `set halted <fraction>`.
4. `python -m rollout_marshal.cli rollout stamp --app bakedown --hours-ago 8`.

   Doing 3 and 4 in the morning is not tidiness. It makes "8 hours at this stage" a true
   statement rather than a number typed in five minutes earlier, and it means the refusal
   in 4a is about the session floor alone, which is the point of that beat.

**Ten minutes before**

5. `git status --short` clean, and the README diagram matching the code, because shot 3
   holds it on screen.
6. `MARSHAL_PLAY=live python demo/live_alpha.py read`, to confirm `inProgress`, `0.2`.
7. `ss -tln | grep -c ":8811"` returns 0, then start the service with the live wiring:

   ```bash
   export GOOGLE_API_KEY=…            # gemini_api_key_rollout_marshal
   export GOOGLE_APPLICATION_CREDENTIALS=…  # rollout_marshal_firestore
   export MARSHAL_BRAIN=adk MARSHAL_PLAY=live MARSHAL_STORE=firestore
   .venv/bin/python -m uvicorn rollout_marshal.server:app --host 127.0.0.1 --port 8811
   ```
8. `.venv/bin/python -m rollout_marshal.cli inject --file demo/fixtures/quiet.json`
9. Play Console open on the alpha track page, already logged in, on the tab you will
   refresh. Log out of anything that could raise a notification.

## The windows

Left half: the browser, Play Console. Right half: one terminal, two panes.

**Right-top: the agent, live.** This is the pane the judge reads, so it is not raw SSE:

```bash
curl -sN http://127.0.0.1:8811/stream \
  | grep --line-buffered '^data: ' | sed -u 's/^data: //' \
  | jq -r '"\(.ts[11:19])  \(.kind|ascii_upcase)  \(.text)"'
```

Verified against a real run: 22 events across the two ticks, one line each, ending
`TICK  tick complete: HALT (decisions/…)`.

**Right-bottom: where you type.** Three commands go in it during the take, and nothing
else. Clear it first; a scrollback of failed attempts is the one thing that makes an
unedited take look rehearsed in the wrong direction.

Clock in a corner of the screen, running, for the whole recording.

---

## The script

Times are cumulative. If it overruns, cut shot 3 to the component diagram alone.

### 1 · The 2am decision · 0:00–0:21 · *40%*

**Screen.** Full frame: the Play Console rollout page, 20%, crash-free rate beside it. No
title card.

> This is a real app release going out at twenty percent. Every few hours somebody has to
> look at one number and decide: widen it, hold it, or halt it. The rule for that decision
> was written down before the release shipped. A person still has to be awake at two in
> the morning to apply it.

### 2 · The number was written down first · 0:21–0:42 · *40%, 30%*

**Screen.** Firestore console, `policies/bakedown` open. The fields visible:
`halt_crash_free 95.0`, `stages [0.2, 0.5, 1.0]`, `min_hours_per_stage 6`,
`session_floor 120`, and `created_at`, which is older than the release.

> Rollout Marshal starts from that written rule. Halt below ninety-five percent
> crash-free. Twenty, fifty, a hundred. Six hours at each stage, and at least a hundred
> and twenty sessions before a reading counts. A human declared this days ago, and none of
> it is the model's to reinterpret.

### 3 · What happens on a tick · 0:42–1:24 · *30%*

**Screen.** The README component diagram, held still. Highlight in sequence: the ADK
agent, the gate, the Play client. Then a flash of the halt-decision diagram, and last a
full-frame card: the test run made minutes before this recording, and the four switches
that decide which outside edge is real. Both numbers on that card are read at record
time, never typed into the page.

> Here is one tick. Gemini 3.5 Flash, running as an ADK agent, reads the policy, the track
> state and the crash rate through four tools, and proposes one action. The proposal goes
> to a policy gate. The gate is plain Python with no model in it, and it re-derives the
> same conditions from Firestore and refuses the call if they do not hold. The agent has
> no store credential.
> Only the gate can reach the Play API. State and the audit log are Firestore.

> Every outside edge is off by default: a clean clone talks to fixtures, never to a store.
> The gate's rules are all under test.

### 4 · The unedited take · 1:24–3:26 · *40%, 30%*

**One recording, no cut, clock visible.** Everything from here to the end of 4d is
continuous. It has been rehearsed live: the halting tick took 58 seconds, of which the
store write was 3.

#### 4a · A tick that does nothing · ~30s

**You type:** `curl -sf -X POST http://127.0.0.1:8811/tick/bakedown | jq`

> First tick, and nobody is watching this one. It reads the policy, the track, the crash
> rate. A hundred percent crash-free, so it proposes to widen. And the gate refuses:
> forty-one sessions, against a floor of a hundred and twenty. A perfect rate over
> forty-one sessions is not evidence of anything. The refusal comes back to the agent as a
> tool result, and it has to answer it. It holds.

Let `GATE.REFUSE` land on screen before you say the word "refuses". This beat is the
differentiator and it is worth the extra two seconds.

#### 4b · The spike, said out loud · ~14s

**You type:** `.venv/bin/python -m rollout_marshal.cli inject --file demo/fixtures/spike.json`

> Now I inject a crash spike into the telemetry feed. Seventy-six point nine percent
> crash-free, over four hundred and twelve sessions. Measured, from a real release in
> this portfolio.

#### 4c · The halt · ~58s, and most of it silent

**You type:** `curl -sf -X POST http://127.0.0.1:8811/tick/bakedown | jq`

> Second tick.

Then say nothing for about twenty-five seconds. The pane fills with the reads and the
model's reasoning while Gemini works. That pause is the proof the thing is not scripted,
and narrating over it throws away the criterion the shot exists for.

When `PROPOSE` appears:

> Declared ninety-five. Measured seventy-six point nine. It proposes a halt, the gate
> confirms the breach on its own reading, and it writes to the Play Developer API.

Silence over `ACT`, `API` and the committed edit id. Then switch to the browser and
refresh the Play Console tab, in the same take. Silence while it loads. When it reads
halted:

> That is a real store account, and nothing was clicked.

#### 4d · The audit trail and the email · ~20s

**You type:** `.venv/bin/python demo/show_decisions.py bakedown`, then open the newest
`decisions/…` document in the Firestore console and scroll it once, slowly.

> Every input it used, what it proposed, what the gate allowed, the edit the store
> committed, and the model's own reasoning. Then the email, sent after the halt rather
> than before. That is the whole point: nobody had to be there.

Show the email last, with a visible timestamp after the halt.

### 5 · It runs on Google Cloud · 3:26–3:44 · *30%*

**Branch A, Cloud Run deployed** (needs #1035; use this if it exists on the day):

Four pans: the service page and its `.run` URL, the request log entry for the tick just
recorded, the Firestore documents, the container image in Artifact Registry.

> This is not running on a laptop. Cloud Run, scaled to zero between ticks, and that is
> the request log for the tick you just watched. Firestore holds the policy and the
> decision log. The Play service account key is in Secret Manager and never in the image.

**Branch B, not deployed.** Then the words above are unavailable and so is the Cloud Run
pan. Show the Firestore console with the documents that tick wrote, and the container
running locally from the same Dockerfile:

> State and the audit log are Firestore, on Google Cloud. These are the documents that
> tick wrote, with the edit id the store returned. The service is a container, and it is
> the same image either way.

Branch B is a scored loss, not a workaround: the rules name a visible Google Cloud
deployment as part of a criterion worth 30%. **The video should not be recorded on branch
B unless the deadline forces it.** #1035 is the ask that clears it.

### 6 · Who built it · 3:44–3:55 · *disclosure*

**Screen.** A still card: the repo URL and the disclosure line.

> Rollout Marshal was built by an autonomous agent working for Joe Muller. The accounts,
> the app, and the release it just halted are his.

The hotfix beat from the old shot list is cut. The patch path is not built, and promising
it here is the one line in the whole video a judge can check and find missing.

---

## Rules for the take

- **Restart the whole recording rather than repeat a beat.** The take is one continuous
  90-second block; a second attempt costs one `live_alpha.py set inProgress 0.2` and
  another eight-hour stamp is not needed, because the stamp is state, not a clock.
- **If Gemini proposes HOLD instead of HALT in 4c**, stop and keep the recording. It has
  never happened across the runs so far, but it is the model deciding, and the decision log
  will say what it read. Investigate before re-taking; a model that changed its mind on the
  same evidence is a finding, not a bad take.
- **If the Play write fails**, the pane shows `ERROR` and the tick returns non-2xx. Stop.
  Re-read the track with `live_alpha.py read` before touching anything, because a
  half-committed edit is a real store state.
- **Nothing gets narrated over an API response or the console refresh.** Those seconds are
  the evidence.
- **Do not fake the clock.** If the take slips past 3:55, cut shot 3 down, never 4c.

## After the take

Recording is internal. Uploading is an outward action: it is public on YouTube, it names
the hackathon, and it shows a real package name, so it goes in `public-log.md` with the
video id and its undo (unlist, then delete) before it is uploaded, and it counts against
the cycle's public-action budget. Submitting it to Devpost is Joe's.
