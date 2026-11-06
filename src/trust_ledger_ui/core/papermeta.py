"""Display metadata from a paper's `paper.toml` (the publish workflow's file), SPEC.md section 3.

Read-only and optional: the title, and the editions (reviewed / explained) as links to their PDFs. The ledger's own
configuration stays authoritative; `main` in paper.toml is only cross-checked against it."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

EDITION_KINDS = ("paper", "reviewed", "explained")


@dataclass
class PaperMeta:
    title: str | None = None
    pdfs: dict[str, Path] = field(default_factory=dict)        # kind -> an existing PDF
    warnings: list[str] = field(default_factory=list)


def load(pattern: str | None, root: Path, name: str, ledger_main: str | None) -> PaperMeta:
    """`pattern` is [metadata] paper_toml (with {name}), relative to the project root; None or a missing file gives an empty
    PaperMeta (the page then shows the paper's name)."""
    meta = PaperMeta()
    if not pattern:
        return meta
    f = (root / pattern.format(name=name)).resolve()
    if not f.is_file():
        return meta
    try:
        raw = tomllib.loads(f.read_text())
    except (tomllib.TOMLDecodeError, OSError) as e:
        meta.warnings.append(f"{f.name}: {e}")
        return meta
    paper = raw.get("paper", {})
    if paper.get("name") and paper["name"] != name:
        meta.warnings.append(f"{f.name}: [paper] name is {paper['name']!r}, the ledger's paper is {name!r}")
    meta.title = paper.get("title")
    here = f.parent
    main = paper.get("main")
    if main and ledger_main and (here / main).resolve() != (root / ledger_main).resolve():
        meta.warnings.append(f"{f.name}: main is {main}, the ledger says {ledger_main}")
    files = {"paper": main}
    for kind in ("reviewed", "explained"):
        files[kind] = raw.get("editions", {}).get(kind)
    for kind, tex in files.items():
        if tex:
            pdf = (here / tex).with_suffix(".pdf")
            if pdf.is_file():
                meta.pdfs[kind] = pdf
    return meta
