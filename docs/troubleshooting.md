# Troubleshooting

Find the message, then the fix.

## Starting

| Message | Cause and fix |
|---|---|
| `no ledger-ui.toml here and no ~/.config/…; use --config FILE` | no config found. Run `ledger-ui --init …/ledger/ledger.toml` in the directory you will start from, or pass `--config` |
| `unknown key(s) in [signing]: persn` | a typo in the config; the message lists the known keys |
| `… lacks the library API this UI needs` | the `ledger.py` named in `[ledger] tool` is too old. Point it at a current trust-ledger checkout, or copy the current `ledger.py` into the project ([requirements](requirements.md)) |
| `ledger format X; this UI supports 0.3.0` | the ledger uses another format version than this version of the tool was tested with |
| `…/ledger.toml not found` | wrong `[ledger] file`; it must be the project's `ledger/ledger.toml` |
| the page says *No access token* | open the address that `ledger-ui` printed, including the part after `#` |
| the page shows 401 or 403 | the token is wrong (the server was restarted: use the new address), or you reached it under another host name. Use `127.0.0.1` or `localhost` |

## Reading

| Symptom | Cause and fix |
|---|---|
| the first load takes seconds | the ledger parses all papers; later requests are cached. The paper menu shows *(loading…)* meanwhile |
| a formula appears in red as source | the renderer does not know a macro or command. Hover for the reason. The paper's own `\newcommand`s are taken from its preamble; exotic packages are not |
| an amber word starting with `\` in a statement | an unknown LaTeX text command; it is shown as is |
| *Files changed on disk* keeps coming back | something rewrites a watched file (the ledger directory, the papers' `.tex` files, the review templates), for example a build that writes generated `.tex` files there |

## Attesting

| Message | Cause and fix |
|---|---|
| *not loaded in your ssh-agent: run `ssh-add`* | the key is not in the agent. `ssh-add ~/.ssh/yourkey`, then **Review** again ([signing](signing.md)) |
| *no ssh-agent reachable (SSH_AUTH_SOCK)* | the tool was started where no agent runs. Start an agent, `ssh-add`, and start `ledger-ui` from that session |
| *the signature does not verify against the registered public key* | the key loaded in the agent is not the one registered under that id in `ledger/keys.toml` |
| *key … is not in ledger/keys.toml* | register it: `ledger.py addkey ID --person "Name" --pub KEY.pub` |
| *this preview is unknown or expired* | a review can be signed within 20 minutes, once. Press **Review** again |
| *another batch is still being signed* | wait for it to finish (it may be waiting for a confirmation in your agent) |
| a claim is *skipped: … changed since the preview* | its statement or evidence changed between your review and the signing. Review again |
| *yellow needs --reason* | write a reason, or choose another level |
| *checklist item(s) … not defined for this target* | the item does not apply to claims (or hypotheses); the message lists what is defined |
| *attestations.toml has changed since that batch* | **Undo** refuses when the file changed after your batch. Remove the records by hand |

## Packs and jobs

| Message | Cause and fix |
|---|---|
| *needs one paper selected* | choose a paper in the paper menu (not *all papers*) |
| *the review pack did not build; see the job log* | open **Jobs → log**. Usually the paper does not build, or `latexmk` / `pdflatex` is missing |
| *a … job is already running* / *a Lean job is already running* | one job per kind, one Lean job overall; wait or **cancel** |
| *N not recoverable* after **Rebuild from git** | the old state is not fully in git (a generated, ignored file such as the Lean dump). Use *also text only*, or see [Snapshots](snapshots.md#rebuilding-snapshots-from-git) |
| *this project is not in a git repository* | the rebuild needs git; without it only snapshots made from now on exist |
| *no snapshot was recorded … cannot be compared* | the attestation is stale and was made before snapshots existed ([Snapshots](snapshots.md)) |

If something else goes wrong, `ledger.py` itself is the reference: run the same command in a terminal and compare
(`status`, `why CLAIM`, `diff CLAIM`).
