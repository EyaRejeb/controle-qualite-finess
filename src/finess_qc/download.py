"""Téléchargement des sources dans data/ (ignoré par git)."""
import shutil
import urllib.request
from pathlib import Path

from .config import DATA_DIR, SOURCES


def download_all(force: bool = False, raw_dir: Path | None = None) -> None:
    """Télécharge chaque source, ou la copie depuis raw_dir si elle y est déjà."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        target = DATA_DIR / name
        if target.exists() and not force:
            print(f"  [ok] {name} déjà présent")
            continue
        if raw_dir and (raw_dir / name).exists():
            shutil.copy(raw_dir / name, target)
            print(f"  [copie] {name} depuis {raw_dir}")
            continue
        print(f"  [téléchargement] {name}")
        req = urllib.request.Request(url, headers={"User-Agent": "controle-qualite-finess"})
        with urllib.request.urlopen(req, timeout=300) as r, open(target, "wb") as f:
            shutil.copyfileobj(r, f)
