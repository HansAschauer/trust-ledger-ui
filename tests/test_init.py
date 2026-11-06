import pytest

from trust_ledger_ui import cli
from trust_ledger_ui.core.config import ConfigError, guess_tool, known_keys, load_config, write_config


def project(tmp_path, tool=True, keys=True):
    (tmp_path / "proj" / "ledger" / "vendor").mkdir(parents=True, exist_ok=True)
    f = tmp_path / "proj" / "ledger" / "ledger.toml"
    f.write_text("")
    if tool:
        (tmp_path / "proj" / "ledger" / "vendor" / "ledger.py").write_text("")
    if keys:
        (tmp_path / "proj" / "ledger" / "keys.toml").write_text('[key.hans]\nperson = "Hans A."\npublic = "ssh-ed25519 AAAA"\n')
    return f


def test_write_config_roundtrip_with_relative_paths(tmp_path):
    f = project(tmp_path)
    cfg_dir = tmp_path / "work"
    cfg_dir.mkdir()
    p = write_config(cfg_dir / "ledger-ui.toml", f, guess_tool(f), "hans", "Hans A.")
    text = p.read_text()
    assert 'file = "../proj/ledger/ledger.toml"' in text and 'key = "hans"' in text
    cfg = load_config(p)
    assert cfg.ledger_file == f.resolve() and cfg.key == "hans" and cfg.person == "Hans A."
    with pytest.raises(ConfigError, match="exists"):
        write_config(p, f, guess_tool(f))


def test_guess_tool_and_known_keys(tmp_path):
    f = project(tmp_path, tool=False, keys=False)
    assert guess_tool(f) is None and known_keys(f) == []
    (tmp_path / "trust-ledger").mkdir()
    (tmp_path / "trust-ledger" / "ledger.py").write_text("")
    assert guess_tool(f) == tmp_path / "trust-ledger" / "ledger.py"
    assert known_keys(project(tmp_path, tool=True, keys=True)) == [("hans", "Hans A.")]


def test_cli_init_writes_the_config_into_the_current_directory(tmp_path, monkeypatch, capsys):
    f = project(tmp_path)
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    assert cli.main(["--init", str(f)]) == 0
    assert (work / "ledger-ui.toml").is_file() and "signing as Hans A." in capsys.readouterr().out
    assert cli.main(["--init", str(f)]) == 2                              # never overwrites
    assert cli.main(["--init", str(tmp_path / "nothing.toml")]) == 2
