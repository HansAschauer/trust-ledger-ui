# A page for referees and readers

!!! info "Prerequisites"
    A working `ledger-ui.toml` ([Install and first start](install.md)). No key, no ssh-agent: nothing is signed.

A referee or reader may want to see what the ledger of your paper records before installing anything. `ledger-ui --export`
writes a **static, read-only page** per paper: one HTML file with everything inside it, which opens in any browser, from
disk or from a web server.

## Write the pages

```bash
uv run ledger-ui --export public                                   # every paper of the ledger
uv run ledger-ui --export public --paper nuclear                   # one paper (repeat --paper for more)
uv run ledger-ui --export public --repo https://github.com/you/project   # also show the repository as a link
```

This writes `public/<paper>.html` for each paper and `public/index.html` with links to them, prints the root of each page and
exits. It takes a few seconds per paper.

Read the warnings it prints:

| Warning | What to do |
|---|---|
| the generated root file shows a different root | run `ledger.py -P <paper> tex` and rebuild the PDF; otherwise the page and the paper show different roots |
| no generated root file | the page cannot be compared with a root in the paper; run `ledger.py -P <paper> tex` |
| tracked files have uncommitted changes | commit first, so that the commit shown on the page holds exactly this ledger |
| the ledger reports errors | fix them; the page lists them for every reader |

Export from the same state you release the paper from: after `ledger.py lock` and `tex`, with everything committed.

## What the page shows

For every result: the paper's statement, the back-translation of its formal statement, the Lean statement, the model's
assessment, the attestations (with level, date, reason, checklist and whether `ledger.py` found the signature valid), what
changed since a stale attestation, what it uses and what it is proved given. A second tab lists the hypotheses, a third
explains the words (levels, stale, back-translation, assessment, evidence types) and how to check the ledger.

A link can point at one result: `nuclear.html#claim=exactalt`.

## What it does not do

The page **shows** the ledger; it does **not check** it. A banner on every page says so, with the root, the commit and the
command that does check (`[paper.<name>] verify` in `ledger.toml`, the same text as in the paper's appendix). The page
recomputes no hash and checks no signature in the browser. A reader who wants to check runs `ledger.py verify` on the
supplementary data.

Nothing can be attested from the page, and it stores nothing.

## Where to put it

- **With the paper:** as an ancillary file on arXiv, on Zenodo, or as supplementary material at the journal. The single
  file keeps working as long as the paper is online.
- **GitHub Pages:** commit the `public/` directory to a branch or repository that Pages serves; `index.html` is the entry.
- **Anywhere else:** any static web server, or send the file.

The page contains the statements, back-translations, assessment notes, attestation reasons and the names of the people who
attested, as they are in the ledger. Export only when all of that is meant to be public.
