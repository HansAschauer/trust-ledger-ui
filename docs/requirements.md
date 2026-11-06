# Before you start

What you need depends on what you want to do. Find your task in the table; each page of the manual repeats its own
prerequisites at the top.

## Requirements per task

| Task | You need |
|---|---|
| **Run the tool at all** | Python 3.11 or newer, [uv](https://docs.astral.sh/uv/), a checkout of trust-ledger (its `ledger.py`), a project with `ledger/ledger.toml`, a modern browser |
| **Browse** claims and hypotheses, read statements, filter, search | nothing more |
| **Attest** (one or many) | an SSH key that is **registered in the ledger** (`ledger.py addkey`), **loaded in your ssh-agent**, and listed in the project's `ledger/keys.toml` with your name |
| **Review packs** (PDF) | `latexmk` and `pdflatex`, and a paper that builds; back-translations appear in the pack if the ledger has a `[review]` section |
| **Jobs** `lock`, `verify`, `check` | nothing more (`check` runs whatever the project's `[check.*]` entries say) |
| **Job `extract`** | whatever the project's adapter needs (for Lean: Docker and the project's `dump.sh`) |
| **Paper titles and PDF links** | a `paper.toml` per paper (optional) |
| **Diffs of what changed** | snapshots, which are written whenever the tool attests; for older attestations record them once, [see here](snapshots.md) |

!!! warning "The vendored `ledger.py` of an older project"
    Many projects keep a copy of `ledger.py` under `ledger/vendor/`. A copy made before 2026-11-06 lacks the library API
    this tool uses. Either copy the current `ledger.py` from trust-ledger into the project, or point the tool at a
    trust-ledger checkout with `[ledger] tool = "…/trust-ledger/ledger.py"` (what `ledger-ui --init` does when it finds one).
    The error message says "lacks the library API" when this is the problem.

!!! tip "No ledger yet?"
    Run `python3 path/to/trust-ledger/ledger.py init` in the project directory. It finds your paper, writes `ledger/` with
    a claim for every labelled theorem, lemma and so on, and can register your SSH key (`--key ~/.ssh/id_ed25519.pub
    --person "Your Name"`). Then continue with [Install and first start](install.md). `ledger-ui --init` is a different
    command: it writes the *tool's* own configuration file for a ledger that already exists.

## A checklist before the first attestation

- [ ] `uv run ledger-ui --summary` lists your papers with their counts (the tool can read the ledger).
- [ ] `ssh-add -l` shows your key (the agent holds it).
- [ ] The key's id appears in `ledger/keys.toml` with `person = "Your Name"`.
- [ ] You can open a claim and read its statement (rendering works).

If one of these fails, [Troubleshooting](troubleshooting.md) has the message and the fix.

## Which page next?

=== "I am new"

    [Install and first start](install.md), then [Setting up signing](signing.md).

=== "I edited the paper or the Lean code"

    [After you edited the paper](after-edit.md).

=== "I want to attest what I have read"

    [Attest claims](attesting.md).

=== "I want to see what changed since I signed"

    [Snapshots and diffs](snapshots.md).
