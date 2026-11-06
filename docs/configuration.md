# Configuration

The tool reads one file, `ledger-ui.toml`. It holds *where the ledger is* and *who you are*, nothing about the project: the
papers, the checklist and the review settings come from the project's own `ledger/ledger.toml`. Create it with
`ledger-ui --init` ([install](install.md)).

**Where it is looked for:** `--config FILE`; else `./ledger-ui.toml`; else `~/.config/trust-ledger-ui/config.toml`
(`$XDG_CONFIG_HOME` is respected). **Paths** in it are relative to the config file.

**Unknown tables or keys are an error**, so a typo cannot pass silently.

## Reference

```toml
[ledger]
file = "../project/ledger/ledger.toml"   # required
tool = "../trust-ledger/ledger.py"       # required

[signing]
person = "Your Name"                     # shown in the header; the signing person comes from keys.toml
key = "yourid"                           # default key: its id in ledger/keys.toml
reasons = ["Checked against the paper and the Lean statement"]   # templates offered in the attest dialog

[metadata]
paper_toml = "paper/{name}/paper.toml"   # optional: titles and PDF links

[viewer]
pdf = "embed"                            # accepted; has no effect yet (packs are always shown in the page)

[server]
port = 0                                 # 0: a free port; set a number to have the same address every time
open_browser = true
```

| Key | Default | Meaning |
|---|---|---|
| `[ledger] file` | required | the project's `ledger/ledger.toml`; the project root is two levels up |
| `[ledger] tool` | required | a trust-ledger `ledger.py` **with the library API**; see [requirements](requirements.md) |
| `[signing] key` | first key of the ledger | key id preselected in the dialog |
| `[signing] reasons` | none | templates under the reason field |
| `[metadata] paper_toml` | none | pattern for a paper's `paper.toml`, relative to the project root; `{name}` is the paper's name in the ledger |
| `[server] port` | `0` | `0` picks a free port; see [From another device](remote.md) for a fixed one |
| `[server] open_browser` | `true` | open the browser at start |

## `paper.toml`

If `paper_toml` is set and the file exists, the page shows the paper's **title** in the paper menu and links to its **PDFs**:
the paper itself and, if the file's `[editions]` table names them, the *reviewed* and *explained* editions. Only files that
exist are linked. The file is the one your publishing workflow already uses; the tool reads `[paper] title`, `main` and
`[editions]` and ignores the rest. It warns if `name` or `main` disagrees with the ledger.

## Command line

| Option | Effect |
|---|---|
| `--config FILE` | use this config file |
| `--init LEDGER_TOML` | write `./ledger-ui.toml` for that ledger and exit; never overwrites |
| `--summary` | print the papers with their counts and exit (no server) |
| `--no-browser` | print the address without opening the browser |

## Files

Next to the config file: `ledger-ui.log` (one JSON line per signing, skip, failure or undo) and `.ledger-ui/packs/`
(review packs). In the project: `ledger/attestations.toml`, `ledger/snapshots/`, and what the jobs write
([Security and what is written](security.md)).
