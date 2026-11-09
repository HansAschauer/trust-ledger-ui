# trust-ledger-ui: specification (draft 1, 2026-11-06)

Decisions behind this document: [Design decisions](design.md). Everything here is open to correction before code.

## 1. Purpose and non-goals

Purpose: browse the trust ledger of a paper project (several papers), find claims and hypotheses that have no
attestation or a stale one, read what would be signed, and attest one or many of them (same level, same
reason) with an ssh-agent signature.

Non-goals: no editing of claims, citations or assertions (hand-edited TOML stays hand-edited); no
verification logic of its own (that is `ledger.py verify`); no storage of ledger state outside the ledger's
own files; no multi-user server (one person, one machine, 127.0.0.1). The one exception to "local only" is the
static read-only page of section 16, which is written to files and has no server at all.

## 2. Architecture

    browser (Alpine.js + KaTeX, static/)  <--JSON/SSE-->  server.py (http.server, 127.0.0.1)
                                                              |
                                                          core/  (no HTTP, no UI)
                                                              |
                                  ledger.py (imported as a module)   ssh-keygen / ssh-agent   latex (via ledger.py review)

- `core/ledgerio.py`: the only module that touches `ledger.py` internals. Loads it from the configured path
  with `importlib`, checks `__version__` and `FORMAT_VERSION` against a list of tested versions (warns on an
  untested one, refuses on a different format version). Exposes plain dataclasses: `Paper`, `Claim`,
  `Hypothesis`, `Attestation`. If `ledger.py` ever gets `--json`, only this module changes.
- `core/status.py`: view model per claim (see 4). `core/attest.py`: validate, sign, append. `core/jobs.py`:
  background commands with a log. `core/render.py`: macro collection and shims for KaTeX.
- The server is a thin layer; the whole core is testable without a browser.
- Loading goes through `Ledger(root, paper)` once per paper and is cached with the mtime of every file the
  ledger read; a changed file invalidates the cache and the page shows "changed on disk, reload?".

## 3. Configuration: `ledger-ui.toml`

Looked up in this order: `--config FILE`, `./ledger-ui.toml`, `$XDG_CONFIG_HOME/trust-ledger-ui/config.toml`.
Paths are relative to the config file. The first start without a config offers to write one (asks for the
`ledger.toml` path only).

    [ledger]
    file = "ledger/ledger.toml"                 # papers, [review], [checklist.*] come from here
    tool = "ledger/vendor/ledger.py"            # imported as a module; also used for review/lock/verify/check/extract

    [signing]
    person = "Hans Aschauer"
    key = "hans"                                # id in ledger/keys.toml; signs through ssh-agent only
    reasons = ["Checked against blind backtranslation"]   # reason templates offered in the dialog

    [metadata]                                  # optional, display and links only
    paper_toml = "paper/{name}/paper.toml"      # title, [editions] -> links; missing file = name only

    [viewer]
    pdf = "xdg-open"                            # or "embed" (default) to show review packs in the page

    [server]
    port = 0                                    # 0 = free port; the URL with the token is printed
    open_browser = true

No project data is copied into this file. Unknown keys are an error (typos must not be silent).

## 4. Data shown

Per claim (from `Ledger`): name, paper(s), label, evidence class, statement source (`tex`/`manual`), per tool
state (Lean `ok`/`assumes (k/n known thm.)`, checks pass/fail), register size, attestations (latest per
person: level, date, current/STALE, signature state), `bound` (current spec hash), uses / used-by.
Derived `attention`: `none` (no attestation), `stale` (all attestations stale), `ok`.
Per hypothesis: name, label, cites, known-theorem flag, attestations, checklist H1/H2.
Per paper: counts (green, yellow, none, stale, failed checks, open hypotheses, uncovered labels), root hash,
`title` and edition PDF links from `paper.toml` when present (cross-check: warn if its `main` differs).
Ledger warnings and errors (as `ledger.py status` prints them) are shown in a collapsible bar.

## 5. Screens

One page, three regions: header (project, paper switcher, agent/key status, job indicator), list (left),
detail (right). Keyboard shortcuts are optional extras; every action has a button.

1. **Papers**: one row per paper with the counts; click selects the paper; "all papers" merges claims
   (shared claims appear once, with their papers listed).
2. **Claim list**: columns as in `ledger.py status` plus `attention`. Quick filters: needs attention
   (none + stale), none, stale, hypotheses, Lean `assumes`, failed checks; text search over name and label;
   sort by any column and a "dependency order" sort (what a claim uses comes first). Checkbox per row,
   select all filtered, select all stale. A badge shows `seen` for claims marked seen (6).
3. **Detail**: paper statement (KaTeX), Lean statement, back-translation (the `leanreadings` text),
   uses / used-by with status colours, attestation history, "why" (what makes it this status), checks,
   register, and the buttons *Mark seen*, *Attest*, *Build review pack*. For stale claims: what changed
   since the attestation (first version: the old and new `bound` hash and the list of changed inputs if
   `ledger.py` can name them; a text diff is a later `ledger.py` feature, see 11).
4. **Hypotheses tab**: same list/detail for hypotheses, with the H1/H2 checklist and the cited source
   (link to `downloaded_papers/` if the file exists, else DOI/arXiv from the citation).
5. **Attest dialog** (single and batch, 6).
6. **Jobs panel**: running and finished jobs with a live log.

## 6. Attestation

### 6.1 Seen
"Seen" is set only explicitly (button or key `v`) on the detail view of one claim. It is stored in
the browser (`localStorage`) per claim and `bound` hash; a changed `bound` drops the marker. It is advice to
the person, not a security boundary, and it is not written to the ledger.

### 6.2 Dialog
Fields: level (green/yellow/conjecture as `ledger.py` allows; yellow requires a reason), reason (multi-line;
templates from `signing.reasons`, plus the last reasons used), checklist (checkboxes from `[checklist.*]`
that apply to the targets), person and key (defaults from the config, key must be in `keys.toml`).
Claims and hypotheses are not mixed in one batch (different checklists).

Preview table: claim, current attestation (level, date, current/STALE) -> new level, short `bound`, seen yes/no.
Claims not marked seen are highlighted and listed in a warning. Confirming such a batch needs an extra step
(type the number of unseen claims, or tick "I am attesting claims I have not marked as seen"). There is no
block: the decision stays with the person. The reason text is shown above the table exactly as it will be signed.

### 6.3 Execution (server side)
For each claim, in the order shown:
1. Re-read the ledger if any file changed; recompute `bound` from the current ledger, never take it from the
   browser. If the `bound` differs from the one the preview showed, skip that claim and report it.
2. Build the record as `cmd_attest` does (`person`, `date` = today, `level`, `reason`, `checklist`, `bound`);
   run `L.checklist_problems`.
3. Sign `attestation_message(project, rec)` with `ssh-keygen -Y sign -n <namespace> -f <pubkey file>`: the
   public key from `keys.toml` is written to a temp file, the private key stays in the agent. The tool never
   asks for a passphrase and never opens a private key file. Verify the signature with `ssh_verify` before
   writing. Agent not reachable or key not loaded: stop before the first claim with the exact `ssh-add`
   command to run.
4. Append to `ledger/attestations.toml` with `toml_record`, under a file lock, one claim at a time, so
   an interrupted batch leaves only whole records.
A failure on one claim is reported and does not stop the others. Afterwards: reload, a result table
(attested / skipped with reason / failed), and a one-line summary in the session log. *Undo last batch*
removes the records this session appended while the file's tail is still exactly that text.
Signatures are meant to be deliberate: one `ssh-keygen -Y sign` call per attestation, never a batched or
cached signature. If the agent asks for confirmation per signature (`ssh-add -c`), that is intended; the
dialog says up front how many confirmations to expect and the progress shows which claim is waiting.

## 7. Review packs

*Build review pack* runs `ledger.py [-P paper] review --for <selection or current claim>` as a job
(output directory from `[review] out`). On success the PDF opens in the embedded viewer (an `<iframe>`
below the detail) or in the system viewer, per `viewer.pdf`. A pack records when it was built and from which
`bound` hashes; the page shows "pack older than the statement" when a `bound` has changed since. Selecting
claims and pressing the button builds one pack for exactly those claims, so the usual loop is: filter to
stale, build the pack, read, mark seen, attest. Later: inline view of statement / back-translation / Lean
text without LaTeX build (11).

## 8. Jobs

`status`, `lock`, `verify`, `check`, `extract`, `review` run as subprocesses of `ledger.py` in the project
root, one job at a time per kind, and *only one Lean job at all* (`extract` and anything that starts Docker
Lean). `extract` is never started automatically and asks for confirmation (minutes of Docker). Output goes to
a log streamed over Server-Sent Events; a job ends with status, duration and a reload of the view.

## 9. Formula rendering

Statements, back-translations and Lean text are LaTeX fragments (Pandoc-style, `\leandisplay{...}`,
`\ensuremath{...}`, `\(..\)`, `\[..\]`, environments). `core/render.py`:
- collects `\newcommand`, `\renewcommand`, `\DeclareMathOperator` from the preamble of each paper's `main`
  file (balanced-brace parse; 32 macros in the current papers) and delivers them as KaTeX `\def`s (needed:
  `\ket` etc. clash with KaTeX built-ins);
- adds the shim list: `\mathds`->`\mathbb`, `\cite`/`\ref`/`\eqref` placeholders, `psmallmatrix`, `multline`;
- a fragment that fails to render is shown as source with a note and counted in the paper's counts, so a
  rendering gap is visible, not hidden.
A script `tools/render_check.py` (the 9899-formula test, rewritten as a test) guards this.

## 10. Server API and security

Local only: bind `127.0.0.1`; a random token per start in the URL fragment, sent as `Authorization` on every
call; reject requests whose `Host` is not the bound address or whose `Origin` is present and different;
no CORS headers; all JavaScript vendored (`static/vendor/`, with version and SHA-256 in `VENDOR.md`).

| Method, path | Writes | Purpose |
|---|---|---|
| GET `/api/papers` | no | papers with counts, titles, edition links |
| GET `/api/claims?paper=` | no | claim view models |
| GET `/api/claims/{name}` | no | detail incl. why, history, render macros |
| GET `/api/hypotheses?paper=` | no | hypothesis view models |
| GET `/api/status` | no | agent/key state, ledger warnings, changed-on-disk flag |
| POST `/api/attest/preview` | no | validated preview table for a batch |
| POST `/api/attest` | **yes** | execute a batch (6.3); needs token and a preview id |
| POST `/api/attest/undo` | **yes** | undo the last batch of this session |
| POST `/api/jobs` | yes (runs commands) | start a job from a fixed list, no free command strings |
| GET `/api/jobs/{id}/events` | no | SSE log |
| GET `/api/packs/{id}.pdf` | no | built review pack |

Rules: no endpoint takes a path or command from the client; file names come from the ledger/config. The
server logs every write to `ledger-ui.log` next to the config.

## 11. Changes to `ledger.py` (trust-ledger repo)

`ledger.py` may be changed for this tool; the changes are made in the trust-ledger repository (format
version, tests and docs there) and then copied into `ledger/vendor/` of a project as usual. Wanted, in order
of need:

1. *Library API without `sys.exit`*: `sign_attestation`, `append_attestation` (and `ssh_sign`) raise a
   `LedgerError` instead of exiting; `cmd_attest` becomes a thin wrapper. Needed by milestone 2.
2. *Structured status*: `status --json` (claims, per tool states, attestation state with signature state,
   hypotheses, warnings), built from the same function as the text output. Then `ledgerio.py` calls this API
   instead of reading `Ledger` attributes; the version check stays.
3. *Stale diff*: "what changed since the attestation of claim X": the inputs whose hash differs from the
   attested one and, for the statement, the old and new text. This needs the ledger to keep the attested
   inputs retrievable (an attestation only stores the `bound` hash today); the design of that (store the
   text in the attestation, or recover it from the previous lock file / a snapshot) is part of the task.
   Milestone 6.
4. *Batch attestation in the library* (one reason, many claims, per-claim result) if it turns out cleaner
   there than in `core/attest.py`; the CLI could then offer it too.

Until a change exists, the UI uses the import-based fallback described in 2 and says what is missing.

## 12. Tests

Pytest on the core with the `examples/egg` ledger of trust-ledger as a fixture (it ships keys and
attestations; its private keys live in `private/`, so a test ssh-agent can sign for real). Cases: status view
equals `ledger.py status` output; batch attestation writes records that `verify` accepts; a stale `bound`
is skipped; an unloaded key stops the batch before the first claim; a half-written file never results.
Server tests check token/Host/Origin handling. Rendering test as in 9. Browser behaviour is checked by hand
for the first milestones.

## 13. Milestones

0. **Done 2026-11-06:** library API in trust-ledger (11.1, 11.2; and the agent-only signing fix, see below); Alpine and KaTeX vendored (`static/VENDOR.md`); config loader; `core/ledgerio.py` + `ledger-ui --summary`, tested against `ledger.py status`.
1. **Done 2026-11-06:** server, token/Host/Origin/CSP, paper switcher + claim list + filters + sort + search, detail with KaTeX (statement, back-translation, Lean text, uses/used-by, attestation history, rests-on), changed-on-disk banner, deep links (`?paper=&claim=`). Not yet: checkboxes/selection (milestone 3), hypotheses tab (5), `paper.toml` titles/edition links (5).
2. **Done 2026-11-06:** attesting through ssh-agent (core is already batch-capable: preview, signing job with per-claim progress, undo, session log `ledger-ui.log`); attest dialog for one claim, explicit "seen" marker (button / key `v`, kept in the browser per claim and bound hash), unseen warning with extra confirmation, key `a` opens the dialog. Hypotheses can be attested through the same API (UI in milestone 5).
3. **Done 2026-11-06:** batch: checkboxes in the list, *Select* menu (all shown / stale / without attestation / shown-but-unseen / clear), "N selected, M seen", *Next unseen* (opens the next selected claim you have not marked), keys `x` select, `j`/`k` move, `a` attests the selection (or the current claim); one dialog for the whole selection; attested claims leave the selection afterwards.
4. **Done 2026-11-06:** jobs (review, lock, verify, check, extract) with live log, cancel, one job per kind and one Lean job at a time; *Review pack* for the current claim or the selection (one paper at a time); embedded PDF viewer with a "statement changed since the pack was built" warning; *Run…* menu. Progress is polled (every 0.8 s), not streamed with Server-Sent Events: same effect, no long-lived connections.
5. **Done 2026-11-06:** hypotheses tab (list with status, detail with the statement, cited sources as links, H-checklist, history, the claims proved given it; attest as a known theorem, same dialog, kind `hypothesis`; key `t` switches tabs); `paper.toml` metadata: title in the paper menu, links to the paper/reviewed/explained PDFs (only those that exist), warnings for a mismatching `name`/`main`. Phone layout (one column, fewer columns, no horizontal overflow) checked at 390 px.
6. **Done 2026-11-06:** stale diff (see below); config bootstrap (`ledger-ui --init path/to/ledger/ledger.toml` writes `ledger-ui.toml`: finds a `ledger.py`, takes the first key of `keys.toml`; never overwrites). The "inline review view" is the detail page itself: statement, back-translation and Lean text are shown there without building a pack.

## 14. Notes from milestone 0

- `ssh-keygen -Y sign -f KEY.pub` falls back to the private key file next to the `.pub` when the agent lacks the
  key (and then asks for its passphrase on a terminal, which a server cannot answer). `ledger.py ssh_sign` therefore
  copies a `.pub` file into a scratch directory first; a key that is not in the agent is a `LedgerError`.
- The vendored `ledger/vendor/ledger.py` of the paper project predates the API; until it is re-copied from
  trust-ledger, point `[ledger] tool` at the trust-ledger checkout.

- Milestone 1: `texlite.js` renders every statement and back-translation of the nuclear, threshold and reach papers
  (136 texts, about 7000 formulas) with no failed formula and no unknown command. The ledger's statements are
  blocks `[label] kind: [title] body`; an `equation`/`align` block is the bare formula and is rendered as display math.
- Alpine calls `init()` itself; do not also put `x-init="init()"` on the element (it ran twice and the second run lost
  the query string).
- `ledger.py` got `why_data` / `claim_detail` (the detail view's data) in addition to `status_data`.

- Milestone 2: the agent must hold the key *before* the batch starts (checked at preview and again at the start); the dialog
  shows the agent state and the `ssh-add` hint. `Preview` stores what will be signed on the server; `POST /api/attest` takes only
  the preview's id (single use, 20 minutes). An end-to-end browser test is `tests/e2e/run_e2e.py` (needs node, playwright-core
  and Google Chrome; not part of `pytest`).
- A Unix socket path is limited to about 100 characters; test agents therefore live in short temporary paths.

- Milestone 4: packs are built with `--out <config dir>/.ledger-ui/packs/<job id>/`, so the project's own `review/` files are
  never overwritten; add `.ledger-ui/` and `ledger-ui.log` to the project's ignore file. The PDF is fetched with the token and
  shown from a `blob:` URL (an iframe cannot send an Authorization header, and the token stays out of URLs). A pack for
  `balanced` in the nuclear paper takes about 10 s (the paper is built once, then the packet twice).
- The stale warning compares the claims' statement hashes (`bound`) at build time with the current ones; it does not
  notice changes to the packet's other claims (what the targets rest on).

- Milestone 5: a hypothesis whose statement is hand-written in a scope (`text`, because its paper is not part of that scope)
  has another `bound` than in the paper's own scope, so an attestation made there shows as stale in the other scopes (the nuclear
  paper's Banach lemma is current in `-P nuclear`, stale in `-P reach`). That is the ledger's rule, shown as it is.
- Two `section.detail` elements exist now (claims, hypotheses): address them by id (`#detail-claim`, `#detail-hyp`).

- Milestone 6, stale diff: no format change. `ledger.py` writes `ledger/snapshots/<bound>.json` whenever it attests (statement
  text, spec hashes and spec content of the evidence nodes and their declarations, statements of used claims); `diff_since`
  compares the latest attestation that has a snapshot with the current state: statement (word diff of the LaTeX source),
  claims it uses, and the changed evidence nodes field by field (Lean type, value). The page shows it for every claim or
  hypothesis that has a stale attestation, and offers "Record snapshots now" (`ledger.py snapshot`) for current attestations
  that have none. An attestation that is already stale and has no snapshot cannot be compared; the page says so.
- The Egg end-to-end test found that POST endpoints which never read their body corrupted keep-alive connections (the next
  request was parsed as `{}GET ...`); the server now always consumes the body.

## 15. Open

- `\mathbb{1}` for `\mathds{1}` looks different in KaTeX; check by eye at milestone 1.
- Several projects in one config (list of `[[ledger]]`): the schema leaves room, not in the first version.

## 16. Static read-only page (export)

For referees and readers who want to see what a paper's ledger records before installing anything.
`ledger-ui --export DIR [--paper NAME]... [--repo URL]` writes `DIR/<paper>.html` per paper and `DIR/index.html`,
and exits; no server runs. Code: `core/export.py`, page: `static/reader.html`, `reader.js`, `reader.css`.

- **Self-contained.** Each page inlines its data (one `<script type="application/json" id="ledger-data">` block),
  the scripts (KaTeX, Alpine.js, `texlite.js`, `diff.js`, `reader.js`), the styles and the KaTeX `.woff2` fonts as
  `data:` URIs. It works from disk (`file://`), from any web server and from GitHub Pages, and loads nothing from
  the network. About 1.5 MB for a paper with 30 results.
- **A preview, not a check.** The page recomputes no hash and checks no signature, and says so in a banner that is
  always shown, with the root, the commit and the command that does check (`[paper.<name>] verify` in
  `ledger.toml`, as in the paper's appendix). Signature states are shown as `ledger.py` found them when the page
  was generated, and labelled that way.
- **Read-only.** No attesting, no jobs, no "seen" marks, no storage. The address carries the selection
  (`#claim=NAME`, `#hyp=NAME`, `#view=about`), so a link can point at one result.
- **Data** (`EXPORT_FORMAT` 0.1): `status_data()` (without author-facing notes), `claim_detail` of every claim,
  `hypothesis_detail` of every hypothesis, `diff_since` for every stale attestation, the attestation records as
  written (reason, checklist, signature, signature state), the vocabulary (evidence types, checklist, levels,
  verdicts, public keys), the paper's KaTeX macros, `lock()` (node kinds and full hashes, claim and hypothesis
  spec hashes, the root), the git commit and uncommitted tracked files, the root in the generated
  `ledger-<paper>-root.tex`, generation time and versions. Paths are relative to the project root. The node
  payloads are not included (17 MB for one of our papers, mostly Lean terms), so the page cannot recompute the
  root by itself; a later version can compare the node hashes with a lock file or recompute the tree above them.
- **Warnings** at export time (printed, and shown on the page): the generated root file shows a different root
  than the ledger (the PDF and the page would disagree), there is no generated root file, tracked files have
  uncommitted changes, the ledger reports errors.
- **Safety of the inlined data.** In the JSON block every `<` is written as `\u003c`, so no text from the ledger can
  end the element; inlined scripts have `</script` escaped. Texts are rendered by `texlite.js`, which escapes
  everything it does not turn into markup.
- **Later:** recompute the root in the browser (WebCrypto SHA-256 over canonical JSON) and check the SSH
  signatures (Ed25519), once someone asks for it; the data block already carries the hashes, signatures and keys.

