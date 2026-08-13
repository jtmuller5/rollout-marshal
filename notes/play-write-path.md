# The Play write path, measured

Rollout Marshal's argument is that it takes an irreversible action against a real store
account instead of drafting text. That claim rested on an unproven half. The loop already
reads Play rollouts and Sentry crash-free rates, but nothing here had ever written a halt
or a widen. Task #1032 ran the write end to end on 2026-08-13 against
`com.mullr.abis_recipes` (Bakedown), on the `alpha` closed testing track. That track
carries no tester group, because `GET edits/{id}/testers/alpha` returns `{}`, so every
write below reached a real Play account and no device.

Written by an autonomous agent working for Joe Muller.

## The call sequence, exactly

Three calls per state change. There is no single "halt" endpoint.

```
POST   /androidpublisher/v3/applications/{package}/edits            -> {"id": "<editId>"}
PUT    /androidpublisher/v3/applications/{package}/edits/{editId}/tracks/{track}
       {"track": "alpha", "releases": [ <one release object> ]}
POST   /androidpublisher/v3/applications/{package}/edits/{editId}:commit
```

Auth is a service-account JSON with scope
`https://www.googleapis.com/auth/androidpublisher`. A failed step has to `DELETE` the edit,
or the dangling edit blocks the next one.

These are the four release objects that were committed, in order. Each was read back from a
fresh edit afterwards.

| step | request body (the `releases` entry) | read back |
|---|---|---|
| stage | `{"name":"1.0.121","versionCodes":["121"],"status":"inProgress","userFraction":0.2}` | as sent, plus the completed release the track already held |
| halt | `{"name":"1.0.121","versionCodes":["121"],"status":"halted","userFraction":0.2}` | `status: halted`, fraction kept |
| widen | `{"name":"1.0.121","versionCodes":["121"],"status":"inProgress","userFraction":0.5}` | `status: inProgress`, `userFraction: 0.5` |
| clear | `[]` | see "clearing" below |

A halted release can be resumed. The widen step took the same release from `halted` back to
`inProgress` at a higher fraction in one committed edit, and Play accepted it. The agent's
three verbs, widen and halt and resume, are all this one call with a different body.

One state change costs about 5.7 seconds of wall clock end to end, measured on the clear
step: mint the token, read the track, open the edit, PUT, commit, re-read. That is the
number the demo depends on. The halt lands well inside one polling interval, so the video
can run the wait in real time.

## Two refusals worth knowing before the demo is cut

The first release on a track cannot be staged. Staging version 121 at 20% on an empty
`alpha` failed with `HTTP 400 INVALID_ARGUMENT, "The first release on a track cannot be
staged"`. A fraction is only legal once the track already carries a release, so the track
was seeded with version code 119 at `status: completed` first. Anything that spins this up
from scratch, including a judge following the repo's instructions, needs two releases on
the demo track rather than one.

Play will also not let go of a staged release. Committing `"releases": []` is accepted and
returns 200, but the track keeps the release: the `inProgress` 50% release came back as
`halted` at 50%, and the seeded `completed` 119 stayed as well. The fun-money loop measured
the same thing on a production track in cycle 678. This run shows it is not production-only
behaviour, and that it applies to `inProgress` and not just to `halted`. In practice:

- A halt is undoable, because it can be resumed.
- Putting a release onto a track cannot be undone through the API. Removal is Play Console
  only, so the track has to be chosen before the write.

That asymmetry is why the agent runs the two directions differently. Halting is the safe
direction and runs unattended; widening is the one that has to argue against a
pre-declared number first.
