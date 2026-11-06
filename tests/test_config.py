import pytest

from trust_ledger_ui.core.config import ConfigError, find_config, load_config


def write(tmp_path, text):
    p = tmp_path / "ledger-ui.toml"
    p.write_text(text)
    return p


def test_paths_are_relative_to_the_config_file(tmp_path):
    (tmp_path / "proj" / "ledger").mkdir(parents=True)
    (tmp_path / "proj" / "ledger" / "ledger.toml").write_text("")
    (tmp_path / "ledger.py").write_text("")
    cfg = load_config(write(tmp_path, '[ledger]\nfile = "proj/ledger/ledger.toml"\ntool = "ledger.py"\n'))
    assert cfg.ledger_file == tmp_path / "proj" / "ledger" / "ledger.toml"
    assert cfg.root == tmp_path / "proj"
    assert cfg.pdf_viewer == "embed" and cfg.port == 0 and cfg.open_browser


def test_unknown_key_and_table_are_errors(tmp_path):
    with pytest.raises(ConfigError, match="unknown key.*persn"):
        load_config(write(tmp_path, '[ledger]\nfile="a"\ntool="b"\n[signing]\npersn = "x"\n'))
    with pytest.raises(ConfigError, match="unknown table"):
        load_config(write(tmp_path, '[ledgr]\nfile="a"\n'))


def test_required_keys_and_existing_files(tmp_path):
    with pytest.raises(ConfigError, match="needs `tool`"):
        load_config(write(tmp_path, '[ledger]\nfile="a"\n'))
    with pytest.raises(ConfigError, match="does not exist"):
        load_config(write(tmp_path, '[ledger]\nfile="a"\ntool="b"\n'))


def test_find_config_explicit_cwd_and_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    with pytest.raises(ConfigError):
        find_config(None, tmp_path)
    p = write(tmp_path, "")
    assert find_config(None, tmp_path) == p
    assert find_config(str(p)) == p
    with pytest.raises(ConfigError, match="no such file"):
        find_config(str(tmp_path / "nope.toml"))
