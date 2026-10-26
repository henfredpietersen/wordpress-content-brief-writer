from wp_brief_agent import __main__ as cli


def _state(**overrides):
    state = {
        "brief": "# Brief\n",
        "steps": 5,
        "stopped_reason": "model_finished",
        "fetched": {},
        "uncited_urls": [],
        "truncated": False,
    }
    state.update(overrides)
    return state


def test_a_brief_with_no_sources_fails_instead_of_passing(monkeypatch, capsys):
    # Live run on blacksmith.agency: every request got 403, nothing was read, yet the old CLI
    # printed "every URL in the brief was read" and exited 0. An unsourced brief is not a pass.
    monkeypatch.setattr(cli, "run", lambda *a, **k: _state())
    assert cli.main(["cold brew", "--offline"]) == 4
    out = capsys.readouterr().out
    assert "no posts were read" in out
    assert "every URL in the brief was read" not in out


def test_a_sourced_grounded_brief_still_passes(monkeypatch, capsys):
    fetched = {"https://site.test/a/": {"title": "A"}}
    monkeypatch.setattr(cli, "run", lambda *a, **k: _state(fetched=fetched))
    assert cli.main(["cold brew", "--offline"]) == 0
    assert "every URL in the brief was read" in capsys.readouterr().out
