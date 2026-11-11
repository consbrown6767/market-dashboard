"""Rebuild a database from the backup files (options-core.db.gz + options-YYYY-MM.db.gz).

Usage: python restore_backup.py OUTPUT_DB [BACKUP_DIR]
  OUTPUT_DB    where to write the restored database (must not exist yet), e.g. ~/MarketData/options.db
  BACKUP_DIR   default: the backups/ folder in iCloud (Vibe Coding/Market Dashboard/backups)

The core file becomes the database (all schemas, views and small tables); each monthly file's rows
are then added to it. The option-price backfill isn't in the backup: re-run backfill_alpaca.py after.
"""

from __future__ import annotations

import gzip
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

from options_collector import BACKUP_DIR


def gunzip(src: Path, dst: Path) -> None:
    with gzip.open(src, "rb") as gz, open(dst, "wb") as out:
        shutil.copyfileobj(gz, out, 1 << 20)


def restore(out: Path, backup_dir: Path) -> dict:
    if out.exists():
        raise SystemExit(f"{out} already exists; move it aside first")
    core = backup_dir / "options-core.db.gz"
    if not core.exists():
        raise SystemExit(f"no {core.name} in {backup_dir}")
    gunzip(core, out)
    db = sqlite3.connect(out)
    months = sorted(backup_dir.glob("options-[0-9][0-9][0-9][0-9]-[0-9][0-9].db.gz"))
    with tempfile.TemporaryDirectory() as tmp:
        for f in months:
            part = Path(tmp) / f.name[:-3]
            gunzip(f, part)
            db.execute("ATTACH DATABASE ? AS m", (str(part),))
            for (name,) in db.execute("SELECT name FROM m.sqlite_master WHERE type = 'table'").fetchall():
                db.execute(f'INSERT OR IGNORE INTO main."{name}" SELECT * FROM m."{name}"')
            db.commit()
            db.execute("DETACH DATABASE m")
            part.unlink()
    counts = {n: db.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
              for (n,) in db.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name").fetchall()}
    db.close()
    print(f"restored {out} from {core.name} + {len(months)} monthly files")
    for n, c in counts.items():
        print(f"  {n:20} {c:>12,}")
    return counts


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    restore(Path(sys.argv[1]).expanduser(), Path(sys.argv[2]).expanduser() if len(sys.argv) > 2 else BACKUP_DIR)
