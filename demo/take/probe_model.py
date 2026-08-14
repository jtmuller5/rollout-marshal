"""Ask the decision model one question before a take spends a real Play write.

A live take resumes a release on a real Play track, records for two minutes and then
asks the model to halt it. If the model is not answering, all of that happens anyway and
the take dies on the beat that matters, leaving a resumed release behind for the undo to
clean up. One request first is cheaper than that.

The status code says which failure it is, and they have different fixes. `429` is the
free tier's twenty requests a day, and only a fresh day clears it. `503` is Google's own
capacity: on 2026-08-14 `gemini-3.5-flash` answered 503 for at least 25 minutes while
`gemini-3.5-flash-lite` on the same key answered 200, so waiting is the fix for that one.

    python demo/take/probe_model.py                 # the model ADK will use
    python demo/take/probe_model.py --model gemini-3.5-flash-lite

Exit 0 means the model answered. Exit 3 means it did not, and the take should not start.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.5-flash"


def probe(model: str, key: str, timeout: float = 60.0) -> tuple[bool, str]:
    """One generate_content call. Returns whether it answered, and what it said."""
    body = json.dumps(
        {"contents": [{"parts": [{"text": "Reply with the single word OK."}]}]}
    ).encode()
    req = urllib.request.Request(
        f"{ENDPOINT}/{model}:generateContent?key={key}",
        data=body,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return True, f"HTTP {resp.status}"
    except urllib.error.HTTPError as exc:  # the useful part is in the body
        detail = exc.read().decode()[:300]
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:  # noqa: BLE001 - a DNS or TLS failure is worth printing
        return False, f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default=os.environ.get("MARSHAL_MODEL", DEFAULT_MODEL))
    args = ap.parse_args(argv)

    key = os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        print("GOOGLE_API_KEY is not set; nothing to probe", file=sys.stderr)
        return 3

    ok, said = probe(args.model, key)
    if ok:
        print(f"{args.model}: answering ({said})")
        return 0
    print(f"{args.model}: NOT answering — {said}", file=sys.stderr)
    if "429" in said:
        print(
            "That is the free tier's daily allowance, twenty requests a day per model. "
            "Only a fresh day fixes it; rehearse with the fixture brain instead.",
            file=sys.stderr,
        )
    elif "503" in said:
        print(
            "That is Google's capacity rather than anything here. Wait and probe again; "
            "another model id on the same key may well answer.",
            file=sys.stderr,
        )
    return 3


if __name__ == "__main__":
    raise SystemExit(main())
