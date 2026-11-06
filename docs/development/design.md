# Design decisions (2026-11-06)

Settled in the planning discussion; the specification is in [specification](specification.md).

## Form
- Local web app (single page), not a TUI: attesting is mostly reading mathematics, and a terminal cannot
  render the formulas. A TUI can follow later on the same core.
- Python standard library only (`http.server`, no framework), `uv` project, no npm and no build step.
  Vendored JavaScript in `static/`: Alpine.js (UI state), KaTeX (formulas). Flask/Starlette is the fallback if
  the hand-written routing becomes a burden; the core is kept independent of the server.
- Core module (load ledger, compute status, write attestation, build review pack) without any UI.

## KaTeX, not MathJax
Test over all 126 .tex files of the papers (9899 distinct formulas, 32 macros taken from the preambles):
both engines render nearly everything. KaTeX is smaller (about 300 KB + 300 KB fonts vs 1.2 MB + 400 KB) and
synchronous. Needed shims: `\mathds` -> `\mathbb` (both engines), `\cite`/`\ref`/`\eqref` as placeholders,
`psmallmatrix` -> `\bigl(\begin{smallmatrix}..\end{smallmatrix}\bigr)`, `multline` -> `gather` (KaTeX only).
Do not enable MathJax's `noundefined` package (it hides unknown macros as red text). A formula that still does
not render is shown as source with a note. Open: `\mathbb{1}` is a plain 1 in KaTeX; check by eye.

## Signing
Only through ssh-agent (`ssh-keygen -Y sign` with the public key); the tool never asks for a passphrase and
never reads a private key file. It warns when the configured key is not loaded. README must explain
`ssh-add` / `AddKeysToAgent yes` for people who do not use an agent.

## Security of the local server
127.0.0.1 only; random token per start, required on every request that writes; check `Host` and `Origin`
(DNS rebinding, CSRF); no third-party scripts (everything vendored).

## Configuration
- User/environment config (`ledger-ui.toml`: path to `ledger.toml`, person, key id, PDF viewer, reason
  templates). No project data is duplicated there.
- Papers, `[review]` and `[checklist.*]` come from the ledger's `ledger.toml`.
- Optional display metadata from `paper/<name>/paper.toml` (the publish workflow's file: `title`,
  `[editions]` -> links to the reviewed/explained PDFs), found through a configurable path pattern; missing
  file = fall back to the name. Not merged with the ledger configuration (separation of concerns); `main` is
  only cross-checked.

## Batch attestation
Select claims, one dialog (level, reason, checklist, key), a preview table (old -> new, what is bound),
then sign each. A claim counts as "seen" once it was opened in the detail view or marked explicitly; unseen
claims in a batch are flagged: a warning plus an extra confirmation, no block (decided 2026-11-06). "Seen" is
set only explicitly (click or key), never automatically. A failure on one claim does not abort the batch.

## Review packs
First: a button that runs `ledger.py review --for <selection>` in the background and embeds the PDF next to
the list. Later: inline view of statement / back-translation / Lean text. Wanted in `ledger.py` itself:
"what changed since my attestation" (stale diff).
