# Security and what is written

The tool can sign attestations in your name, so its defaults are strict. This page says what it does, and what it writes.

## What protects it

- **Local only.** The server listens on `127.0.0.1`. Requests with another `Host` header are refused (this stops DNS-rebinding
  tricks from other websites), and so are requests with a foreign `Origin`.
- **A token per start.** Every call to the API needs the random token printed at start. It travels in the address after `#`,
  which a browser never sends to a server, and the page forwards it in a header and removes it from the address bar.
- **Nothing is signed that you did not review.** Signing takes only the id of a review you have seen. The server computes
  the state being attested itself, and skips a claim whose state changed after your review.
- **Signing only through `ssh-agent`.** The tool never asks for a passphrase and never opens a private key file. It copies
  the *public* key to a scratch directory for the signing call, so `ssh-keygen` cannot fall back to the private key next to
  it.
- **No outside scripts.** The JavaScript (Alpine.js, KaTeX) is part of the repository, with versions and checksums in
  `src/trust_ledger_ui/static/VENDOR.md`. The page loads nothing from the network, and a strict content-security policy
  allows only its own files (`unsafe-eval` is needed because Alpine compiles its expressions; only same-origin scripts may
  run).
- **A fixed list of jobs.** The page cannot send a command line or a path; the server builds the arguments from checked names.

## What it does not protect against

Anyone who can already run programs as you can use your ssh-agent anyway, and can read the token from the process list. On a
shared machine, other users can connect to the port but need the token. Keep the agent's keys protected by a passphrase, and
use `ssh-add -c` if you want a confirmation for every signature.

## What is written, and where

| File | Written by | Contents |
|---|---|---|
| `ledger/attestations.toml` | **Sign** (appends); **Undo** (removes the last batch) | the attestation records |
| `ledger/snapshots/<hash>.json` | signing; **Record snapshots now** | what an attestation bound to ([Snapshots](snapshots.md)) |
| `ledger/lock*.json`, `ledger/checks.json`, `ledger/lean.json` | jobs *lock*, *check*, *extract* | the files `ledger.py` itself writes for those commands |
| `ledger-ui.log` (next to the config) | every signing, skip, failure and undo | one JSON line each: time, claim, level, key, person, state hash |
| `.ledger-ui/packs/` (next to the config) | review packs | the PDFs and their LaTeX body |
| *(in the browser)* | **Mark as seen** | which claims you marked, per claim and state; not shared, not in the ledger |

Everything else about the ledger stays as it is on disk. The tool keeps no database and makes no network connections other than
its own page.
