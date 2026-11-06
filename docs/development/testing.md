# Tests and screenshots

The tool is developed against the **trust-ledger** repository, expected next to this one (or at `$TRUST_LEDGER`). Tests that
need it use trust-ledger's public `egg` example on a scratch copy; nothing touches a real project.

## Unit and integration tests

```bash
uv sync
uv run pytest
```

They cover the configuration, access to `ledger.py`, rendering macros, signing with a real `ssh-agent` (a private agent is
started per test), batches, undo, jobs, the HTTP server (token, Host and Origin checks, paths, keep-alive behaviour), and the
two JavaScript modules under node (`texlite.js`, `diff.js`). Tests that need `ssh-keygen`, `ssh-agent` or `node` skip when
they are missing.

## Browser test

`tests/e2e/run_e2e.py` drives the page in a real Chrome (attest, batch, hypothesis, jobs, snapshots, diff):

```bash
npm install playwright-core          # in any directory
uv run python tests/e2e/run_e2e.py --playwright DIR_WITH_node_modules --trust-ledger ../trust-ledger
```

## The screenshots of this manual

They are generated, not taken by hand, so they can be regenerated when the page changes:

```bash
uv run python tools/make_screenshots.py --trust-ledger ../trust-ledger --playwright DIR_WITH_node_modules
```

It builds a scratch project from the `egg` example (two invented people, one with a key loaded in a private agent), walks through
the workflows and writes `docs/images/*.png`. Needs node with `playwright-core`, Google Chrome, and `latexmk` for the review
pack picture.

## The manual

```bash
uv run mkdocs serve          # live preview at http://127.0.0.1:8000
uv run mkdocs build --strict
```
