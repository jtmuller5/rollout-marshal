# Experiments

One line per attempt, appended by the cycle that ran it. **Read this before proposing work
and append before ending a cycle** — it is what stops the next cycle re-running what the
last one already measured.

| date | rung | what changed | local | leaderboard / demo | cycles | keep? |
|---|---|---|---|---|---|---|
| 2026-08-13 | 2 | Built the spine to shot 4 (#1034): service, ADK agent, gate, executor, Play client, crash feed, store, email, streamed log, CLI, 23 tests. `bash demo/run_demo.sh` runs refusal → spike → halt → email on one command. Ran it on the real Gemini 3.5 Flash: the model proposed WIDEN, took the gate's session-floor refusal, held, then halted on the spike. Live Play client verified read-only against the real `alpha` track. | 23 tests pass; demo green on both brains | shot 4 exists outside the fixture Play client; nothing deployed | 1 | keep |
| 2026-08-13 | 2 | Proved the Play WRITE path (#1032): stage, halt, resume-and-widen, clear, all committed on Bakedown's `alpha` closed testing track with no testers. 5 committed edits, raw bodies in `notes/play-write-path.md`. Two Play refusals found: a track's first release cannot be staged, and a release cannot be removed from a track by API. | n/a | the demo's central action is real, not a mock | 1 | keep |
| 2026-08-13 | 1 | Wrote the four-minute shot list before any code: halt path as the centrepiece, gate refusal before the halt, one unedited take. Rung 0 criteria weights read off the rules page and written into the project prompt. | n/a | shot list exists; no footage yet | 1 | keep |
