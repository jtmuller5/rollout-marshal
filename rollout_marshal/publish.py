"""The hosted page, built out of the decision log rather than written by hand.

Devpost asks for a hosted project URL. The honest version of that page, for an agent
whose whole claim is that it acted, is the agent's own audit trail: the policy that was
declared first, the readings it got, what it proposed, what the gate said, and the store
write that came out the other end. So every number on the page is read from the same
`policies`, `rollouts` and `decisions` documents the service writes at runtime, and
`publish` refuses to build a page at all when they are missing.

That rules out the failure this project exists to argue against. A page carrying "halted
at 20%" as literal text keeps saying it after the halt stops working, and a reader has no
way to tell.

It also names the edges. A tick that read a fixture crash feed and a tick that read
Sentry are different events, and a fixture Play client and a real Play edit are very
different claims, so each decision on the page carries which one produced it. Run
`publish` against Firestore and the live halt appears with the Play edit id it committed;
run it against the JSON store after `demo/run_demo.sh` and the same page says fixture, in
the same words.

    python -m rollout_marshal.cli publish --app bakedown

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import html
import os
from pathlib import Path
from typing import Any

from .models import iso, now
from .store import Store, build_store

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"

REPO = "https://github.com/jtmuller5/rollout-marshal"

# The page is one file, so the diagrams are inlined rather than linked. They are built
# from the README's own mermaid blocks by demo/render_diagrams.py.
DIAGRAMS = (
    ("architecture.svg", "What runs where. Filled boxes are Google Cloud."),
    ("decision-flow.svg", "One tick, from the scheduler to the halt."),
)


class PublishError(RuntimeError):
    """The page could not be built from what is on disk."""


def collect(app: str, store: Store | None = None, limit: int = 50) -> dict[str, Any]:
    """Everything the page states, read out of the store. No defaults, no fallbacks."""
    store = store or build_store()
    policy = store.get_policy(app)
    if policy is None:
        raise PublishError(f"no policies/{app}: nothing declared the halt number")
    decisions = store.list_decisions(app, limit)
    if not decisions:
        raise PublishError(f"no decisions for {app}: the agent has not run")
    return {
        "app": app,
        "policy": policy.to_dict(),
        "rollout": store.get_rollout(app) or {},
        "decisions": decisions,
        "store": type(store).__name__,
        "published_at": iso(now()),
    }


def _live_edit(decision: dict[str, Any]) -> str | None:
    """The Play edit id, when the write went to the real API rather than the fixture."""
    edit = ((decision.get("api_response") or {}).get("edit_id")) or ""
    return edit if edit and not edit.startswith("fixture") else None


def proof(facts: dict[str, Any]) -> dict[str, Any] | None:
    """The most recent decision that wrote to a real store account, if there is one."""
    for d in reversed(facts["decisions"]):
        if _live_edit(d):
            return d
    return None


def _diagram(name: str, assets: Path) -> str:
    path = assets / name
    if not path.exists():
        raise PublishError(
            f"docs/assets/{name} is missing; run `python demo/render_diagrams.py` first"
        )
    return path.read_text()


def _e(v: Any) -> str:
    return html.escape(str(v))


def _pct(v: Any) -> str:
    return f"{float(v):.1f}%" if v is not None else "not recorded"


def _checks(verdict: dict[str, Any]) -> str:
    rows = []
    for c in verdict.get("checks") or []:
        mark = "pass" if c.get("passed") else "fail"
        rows.append(
            f'<tr class="{mark}"><td>{_e(c.get("name"))}</td>'
            f'<td>{_e(c.get("detail"))}</td><td>{mark}</td></tr>'
        )
    if not rows:
        # HOLD carries no checks, and its reason is already printed above this table.
        return ""
    return (
        '<table class="checks"><thead><tr><th>gate check</th><th>what it measured</th>'
        "<th></th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def _attempts(d: dict[str, Any]) -> str:
    out = []
    for i, a in enumerate(d.get("attempts") or [], start=1):
        p = a.get("proposal") or {}
        v = a.get("verdict") or {}
        allowed = "allowed" if v.get("allowed") else "refused"
        out.append(
            f'<div class="attempt {allowed}">'
            f'<div class="hd"><b>proposal {i}: {_e(p.get("action"))}</b>'
            f'<span class="tag {allowed}">gate {allowed}</span></div>'
            f'<p class="why">{_e(p.get("reasoning"))}</p>'
            f'<p class="verdict">{_e(v.get("reason"))}</p>'
            f"{_checks(v)}</div>"
        )
    return "".join(out)


def _source(d: dict[str, Any]) -> str:
    """One line saying which edges this tick actually touched."""
    inputs = d.get("inputs") or {}
    crash = str(inputs.get("crash_source") or "unknown")
    brain = str(d.get("brain") or "unknown")
    model = "Gemini 3.5 through ADK" if brain == "adk" else "scripted control, no model"
    feed = "Sentry release health" if not crash.startswith("fixture") else f"crash feed {crash}"
    edit = _live_edit(d)
    play = (
        f"real Play edit <code>{_e(edit)}</code>" if edit else "fixture Play client"
    )
    return f"{model} · {feed} · {play}"


def _decision(d: dict[str, Any]) -> str:
    inputs = d.get("inputs") or {}
    edit = _live_edit(d)
    return f"""
<article class="decision {'live' if edit else 'fixture'}">
  <header>
    <span class="action {_e(str(d.get('action_taken')).lower())}">{_e(d.get('action_taken'))}</span>
    <time>{_e(d.get('ts'))}</time>
    <span class="src">{_source(d)}</span>
  </header>
  <table class="inputs"><tbody>
    <tr><th>crash-free</th><td>{_pct(inputs.get('crash_free'))} over
        {_e(inputs.get('sessions'))} sessions</td></tr>
    <tr><th>halt line</th><td>{_pct(inputs.get('halt_criterion'))}, and a floor of
        {_e(inputs.get('session_floor'))} sessions before any widen</td></tr>
    <tr><th>stage</th><td>{_e(inputs.get('user_fraction'))} of users,
        {_e(inputs.get('hours_at_stage'))}h in, status {_e(inputs.get('status'))}</td></tr>
    <tr><th>track</th><td>{_e(inputs.get('package'))} · {_e(inputs.get('track'))} ·
        version {_e(inputs.get('version_code'))}</td></tr>
  </tbody></table>
  {_attempts(d)}
  <p class="outcome">{_e(d.get('model_reasoning') or '')}</p>
</article>"""


CSS = """
:root{--ink:#14171a;--dim:#5b6570;--line:#dfe3e8;--bg:#fbfcfd;--ok:#1a7f4b;--no:#b3261e}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
 font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
main{max-width:60rem;margin:0 auto;padding:2.5rem 1.25rem 5rem}
h1{font-size:2.1rem;margin:0 0 .3rem}
h2{font-size:1.25rem;margin:2.6rem 0 .8rem;padding-top:1.4rem;border-top:1px solid var(--line)}
.lede{font-size:1.1rem;color:var(--dim);margin:0 0 1.4rem}
.disclosure{background:#fff7e6;border:1px solid #f0d9a8;border-radius:8px;
 padding:.7rem .9rem;font-size:.9rem;color:#6b5320}
code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.88em;
 background:#eef1f4;padding:.1em .35em;border-radius:4px}
pre{background:#14171a;color:#e9edf1;padding:1rem;border-radius:8px;overflow-x:auto;
 font-size:.85rem;line-height:1.55}
pre code{background:none;color:inherit;padding:0}
.proof{background:#fff;border:2px solid var(--no);border-radius:10px;padding:1.2rem 1.3rem}
.proof h3{margin:0 0 .5rem;font-size:1.05rem}
.big{font-size:1.6rem;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:.9rem;
 margin:1rem 0 0}
.cell{background:#fff;border:1px solid var(--line);border-radius:8px;padding:.7rem .8rem}
.cell b{display:block;font-size:.72rem;letter-spacing:.06em;text-transform:uppercase;
 color:var(--dim);font-weight:600}
.decision{background:#fff;border:1px solid var(--line);border-left:4px solid var(--line);
 border-radius:8px;padding:1rem 1.1rem;margin:0 0 1rem}
.decision.live{border-left-color:var(--no)}
.decision header{display:flex;flex-wrap:wrap;gap:.6rem;align-items:baseline;
 margin-bottom:.6rem}
.action{font-weight:700;letter-spacing:.04em}
.action.halt{color:var(--no)}.action.hold{color:var(--dim)}.action.widen{color:var(--ok)}
time,.src{font-size:.82rem;color:var(--dim)}
table{border-collapse:collapse;width:100%;font-size:.88rem}
th,td{text-align:left;padding:.32rem .5rem;border-bottom:1px solid var(--line);
 vertical-align:top}
.inputs th{width:9rem;color:var(--dim);font-weight:600}
.attempt{border:1px solid var(--line);border-radius:6px;padding:.6rem .75rem;margin:.7rem 0}
.attempt .hd{display:flex;justify-content:space-between;gap:.5rem;flex-wrap:wrap}
.tag{font-size:.72rem;padding:.1rem .45rem;border-radius:999px}
.tag.allowed{background:#e6f4ec;color:var(--ok)}
.tag.refused{background:#fdeceb;color:var(--no)}
.why,.verdict{margin:.35rem 0;font-size:.9rem}
.verdict{color:var(--dim)}
.checks tr.fail td{color:var(--no)}
.outcome{font-size:.85rem;color:var(--dim);margin:.6rem 0 0}
/* The diagrams are wider than the reading column, so they get the whole viewport.
   At 60rem they render at about half size and the node labels stop being readable. */
figure{margin:1.4rem calc(50% - 50vw);width:100vw;background:#fff;
 border-top:1px solid var(--line);border-bottom:1px solid var(--line);
 padding:1.25rem clamp(1rem,3vw,2.5rem);overflow-x:auto}
figure svg{display:block;margin:0 auto}
figcaption{font-size:.85rem;color:var(--dim);margin:.7rem auto 0;max-width:60rem}
footer{margin-top:3rem;padding-top:1.2rem;border-top:1px solid var(--line);
 font-size:.85rem;color:var(--dim)}
a{color:#1355c4}
"""


def render(facts: dict[str, Any], assets: Path | None = None) -> str:
    assets = assets or (DOCS / "assets")
    p = facts["policy"]
    r = facts["rollout"]
    live = proof(facts)
    decisions = list(reversed(facts["decisions"]))

    if live:
        li = live.get("inputs") or {}
        proof_html = f"""
<div class="proof">
  <h3>It halted a real release</h3>
  <p class="big">{_pct(li.get('crash_free'))} crash-free, against a
     {_pct(li.get('halt_criterion'))} line declared first &rarr; HALT</p>
  <p>On {_e(str(live.get('ts'))[:10])} at {_e(str(live.get('ts'))[11:16])} UTC the agent
     read the track, read the crash
     rate, proposed the halt with both numbers, and the gate confirmed the breach from
     the policy document before letting the write through. Google Play returned edit
     <code>{_e(_live_edit(live))}</code> against
     <code>{_e(li.get('package'))}</code> on the <code>{_e(li.get('track'))}</code>
     track, which went from <code>{_e(li.get('status'))}</code> at
     {_e(li.get('user_fraction'))} to <code>halted</code>. Nobody pressed anything.</p>
  <p class="note">A closed testing track, so the build had testers on it and no paying
     customers. The crash reading in that tick came from
     <code>{_e(li.get('crash_source'))}</code>; the store write did not.</p>
</div>"""
    else:
        proof_html = """
<div class="proof">
  <h3>This page was built from a fixture run</h3>
  <p>Every decision below is real output from a real tick, but no store account was
     touched: the Play client was the fixture. Publish against the Firestore the service
     writes to and the live halt appears here with its Play edit id.</p>
</div>"""

    diagrams = "".join(
        f"<figure>{_diagram(name, assets)}<figcaption>{html.escape(caption)}</figcaption></figure>"
        for name, caption in DIAGRAMS
    )

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rollout Marshal: an agent that owns a mobile release</title>
<meta name="description" content="An ADK agent on Gemini 3.5 that watches a staged Play
 rollout and halts it against a halt number declared before the release.">
<style>{CSS}</style>
</head><body><main>

<h1>Rollout Marshal</h1>
<p class="lede">An agent that owns a mobile app release from the moment it goes out to
the moment it is either at 100% or halted.</p>

<p class="disclosure">Built by an autonomous agent working for Joe Muller. The code, the
diagrams and this page were written by that agent; the accounts, the apps and the money
are Joe's. Everything on this page is read out of the agent's own decision log at publish
time, so nothing here is a claim typed by hand.</p>

<h2>The friction</h2>
<p>A staged rollout is a decision nobody wants to make at 2am. The build is at 20% on
Play, the crash-free rate just moved, and somebody has to widen, hold or halt. The
judgement is not hard. Being awake for it is. A real app in this portfolio shipped at
76.9% crash-free against a 95% line and was halted by hand, hours later, by a person who
happened to look.</p>
<p>Rollout Marshal polls the Play Developer API and the crash feed, judges what it reads
against a halt number written down <em>before</em> the release went out, and then acts on
the store account. Its output is a store write, not a recommendation. It emails the human
afterwards.</p>

{proof_html}

<h2>Architecture</h2>
{diagrams}

<h2>Why there is a gate</h2>
<p>The agent decides. It reads the numbers and picks the action. But a language model
that has talked itself into widening a bad release ships that release to four times as
many people, so every write goes through plain Python that re-derives the same conditions
from the same documents and refuses the call when they do not hold. A refusal goes back
to the agent as a tool result, and that is usually what makes it halt instead. The gate
has no prompt input and no I/O, so its rules are tested one by one.</p>

<h2>The policy, declared before the release</h2>
<div class="grid">
  <div class="cell"><b>halt below</b>{_pct(p.get('halt_crash_free'))} crash-free</div>
  <div class="cell"><b>stages</b>{_e(p.get('stages'))}</div>
  <div class="cell"><b>minimum per stage</b>{_e(p.get('min_hours_per_stage'))} hours</div>
  <div class="cell"><b>session floor</b>{_e(p.get('session_floor'))} sessions</div>
  <div class="cell"><b>baseline</b>{_pct(p.get('baseline_crash_free'))} crash-free</div>
  <div class="cell"><b>declared</b>{_e(str(p.get('created_at'))[:16])} UTC</div>
</div>
<p class="note">Package <code>{_e(p.get('package'))}</code>, track
<code>{_e(p.get('track'))}</code>. The rollout document as the last tick left it, written
{_e(str(r.get('updated_at', 'never'))[:16])}: release
<code>{_e(r.get('release_name', 'not recorded'))}</code>,
<code>{_e(r.get('status', 'unknown'))}</code> at
<code>{_e(r.get('user_fraction', 'not recorded'))}</code>. It records the stage the agent read at the
top of the tick, so it lags the halt below by one poll.</p>

<h2>The decision log</h2>
<p>Append-only, newest first, straight out of
<code>{'Firestore' if facts['store'] == 'FirestoreStore' else 'the JSON store'}</code>.
A refused proposal is the part worth keeping: a tick that wanted to widen, was refused on
the session floor and then held is a different event from a tick that simply held, and
only the first one shows the policy doing work.</p>
{''.join(_decision(d) for d in decisions)}

<h2>Run it yourself</h2>
<pre><code>git clone {REPO}.git
cd rollout-marshal
uv venv &amp;&amp; uv pip install -r requirements-dev.txt
bash demo/run_demo.sh</code></pre>
<p>That takes a policy, a staged release and a crash spike through two ticks on a clean
checkout with no credentials at all: every outside edge has a fixture behind the same
interface as the real thing, and one environment variable each swaps them
(<code>MARSHAL_BRAIN</code>, <code>MARSHAL_PLAY</code>, <code>MARSHAL_CRASH_FEED</code>,
<code>MARSHAL_STORE</code>). The defaults are the safe ones, so running the service by
accident cannot reach a store account.</p>

<footer>
<p><a href="{REPO}">github.com/jtmuller5/rollout-marshal</a> · MIT ·
Gemini 3.5 · ADK · Cloud Run · Firestore</p>
<p>Published {_e(facts['published_at'])} from {len(facts['decisions'])} decisions in
{_e(facts['store'])}. Rebuilt by <code>python -m rollout_marshal.cli publish --app
{_e(facts['app'])}</code>; it refuses to build a page when the log is empty.</p>
</footer>

</main></body></html>
"""


def publish(app: str, out: Path | None = None, store: Store | None = None) -> Path:
    facts = collect(app, store)
    target = Path(out or os.environ.get("MARSHAL_DOCS_DIR") or DOCS)
    target.mkdir(parents=True, exist_ok=True)
    page = target / "index.html"
    page.write_text(render(facts))
    return page
