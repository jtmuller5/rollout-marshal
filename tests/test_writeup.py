"""The public build write-up, and the sentence it is worthless without.

The hackathon awards the write-up bonus only when the post says it was created to enter
the hackathon. That makes the disclosure a build-time precondition rather than an editing
habit, so `render` refuses without it and these tests hold it to that. The rest is the
narrow markdown subset: if the renderer ever leaves raw `##` or `**` on the page, the
published post reads as a draft somebody pasted.

Written by an autonomous agent working for Joe Muller.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from rollout_marshal import cli, writeup  # noqa: E402

SOURCE = writeup.SOURCE.read_text()


def test_the_source_carries_both_disclosures():
    assert writeup.DISCLOSURE in SOURCE
    assert writeup.AUTHORSHIP in SOURCE


def test_render_refuses_a_post_that_would_not_be_scored():
    without = SOURCE.replace(writeup.DISCLOSURE, "written for fun")
    with pytest.raises(writeup.WriteupError) as e:
        writeup.render(without)
    assert writeup.DISCLOSURE in str(e.value)


def test_render_refuses_a_post_that_hides_who_wrote_it():
    anon = SOURCE.replace(writeup.AUTHORSHIP, "somebody")
    with pytest.raises(writeup.WriteupError):
        writeup.render(anon)


def test_the_page_carries_the_disclosures_where_a_reader_sees_them():
    page = writeup.render(SOURCE)
    assert writeup.DISCLOSURE in page
    assert writeup.AUTHORSHIP in page
    assert page.count('class="disclosure"') >= 2


def test_no_markdown_survives_into_the_page():
    body = writeup.render(SOURCE).split("<main>", 1)[1]
    assert "**" not in body
    assert not re.search(r"(?m)^#{1,3} ", body)
    assert "](" not in body
    # Every heading in the source became a heading on the page.
    assert body.count("<h2>") == len(re.findall(r"(?m)^## ", SOURCE))
    assert body.count("<h1>") == 1


def test_code_spans_and_links_render():
    page = writeup.render(SOURCE)
    assert "<code>MARSHAL_PLAY</code>" in page
    assert 'href="https://github.com/jtmuller5/rollout-marshal"' in page


def test_a_source_with_no_title_is_an_error():
    with pytest.raises(writeup.WriteupError):
        writeup.to_html(SOURCE.replace("# Building", "Building"))


def test_cli_writes_the_page(tmp_path: Path, capsys):
    assert cli.main(["writeup", "--out", str(tmp_path)]) == 0
    page = tmp_path / "index.html"
    assert page.exists()
    assert "Rollout Marshal" in page.read_text()
    assert str(page) in capsys.readouterr().out


def test_the_published_page_on_disk_matches_the_source():
    """docs/build-log/ is what the world reads; regenerate it when the prose changes."""
    published = writeup.OUT / "index.html"
    assert published.exists(), "run `python -m rollout_marshal.cli writeup`"
    assert published.read_text() == writeup.render(SOURCE)
