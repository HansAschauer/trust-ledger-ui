# Install and first start

!!! info "Prerequisites"
    Python 3.11+, [uv](https://docs.astral.sh/uv/), a trust-ledger checkout, a project with `ledger/ledger.toml`
    ([details](requirements.md)).

## 1. Get the two repositories

Put them next to each other (the tests expect that; the tool itself only needs the path to `ledger.py`).

```bash
git clone <url of trust-ledger>
git clone git@github.com:HansAschauer/trust-ledger-ui.git
cd trust-ledger-ui
uv sync
```

`uv sync` creates a virtual environment. The tool itself has **no runtime dependencies** (Python's standard library only);
the JavaScript it needs is included in the repository.

## 2. Write the configuration once

Go to the directory where you want the config file to live (the project root is a good place) and run:

```bash
uv run ledger-ui --init path/to/your/project/ledger/ledger.toml
```

This writes `ledger-ui.toml` into the current directory:

```toml
[ledger]
file = "../your-project/ledger/ledger.toml"
tool = "../trust-ledger/ledger.py"   # a trust-ledger ledger.py with the library API

[signing]
person = "Your Name"
key = "yourkey"   # id in ledger/keys.toml; signs through ssh-agent

[metadata]
# paper_toml = "paper/{name}/paper.toml"   # titles and edition PDFs, if you have such files
```

It finds `ledger.py` in `ledger/vendor/` of the project or in a `trust-ledger` directory next to it, and takes the first key
of `ledger/keys.toml` as the signing key. Change anything that is not right. Paths are relative to the config file. The
command never overwrites an existing file. All keys are described in [Configuration](configuration.md).

## 3. Check that the tool can read the ledger

```console
$ uv run ledger-ui --summary
nuclear      claims  32  none  13  stale   9  green   1  yellow   9  hypotheses open 0/1
threshold    claims  23  none   9  stale  10  green   0  yellow   4  hypotheses open 1/1
```

One line per paper. The first call takes a few seconds per paper, because the ledger parses the papers.

## 4. Start

```bash
uv run ledger-ui
```

It prints an address and opens your browser:

```
ledger-ui: http://127.0.0.1:41873/#Xq3…
```

!!! note "The part after `#` is an access token"
    The server listens on `127.0.0.1` only, and every request needs the token. The page keeps it for the session and removes
    it from the address bar. If you close the tab, use the printed address again. `--no-browser` prints it without opening
    a browser; `Ctrl+C` stops the server.

Where the config file is searched: `--config FILE`, then `./ledger-ui.toml`, then
`~/.config/trust-ledger-ui/config.toml`.

## 5. The first screen

On the first start the page may offer to record **snapshots** (the blue bar in the picture on the [home page](index.md)).
That is explained in [Snapshots and diffs](snapshots.md); you can do it right away.

Next: [Setting up signing](signing.md), unless you only want to browse.
