import hashlib
import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "src" / "trust_ledger_ui" / "static"


def test_vendored_files_match_vendor_md():
    rows = re.findall(r"\| (vendor/\S+) \| ([0-9a-f]{64}) \|", (STATIC / "VENDOR.md").read_text())
    assert len(rows) == 3
    for name, digest in rows:
        assert hashlib.sha256((STATIC / name).read_bytes()).hexdigest() == digest, name


def test_katex_fonts_match_sha256sums():
    fonts = STATIC / "vendor" / "katex" / "fonts"
    for line in (fonts / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split()
        assert hashlib.sha256((fonts / name).read_bytes()).hexdigest() == digest, name
