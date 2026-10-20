"""python -m app.ingest [datasets|news|all]"""
from __future__ import annotations

import os
import sys

from ..db import get_conn, init_db
from ..routes.data import datasets_dir
from . import news, opendata


def main(argv: list[str]) -> None:
    what = argv[0] if argv else "all"
    if what not in ("datasets", "news", "all"):
        raise SystemExit(__doc__)
    init_db()
    with get_conn() as conn:
        start = conn.execute("SELECT COALESCE(MAX(id), 0) FROM ingest_runs").fetchone()[0]
        if what in ("datasets", "all"):
            print("datasets:", opendata.run(conn, os.path.abspath(datasets_dir())))
        if what in ("news", "all"):
            print("news:", news.run(conn))
        for r in conn.execute("SELECT kind, status, source, message FROM ingest_runs WHERE id > ? ORDER BY id", (start,)):
            print(f"  [{r['kind']}:{r['status']}] {r['source']} — {r['message']}")


if __name__ == "__main__":
    main(sys.argv[1:])
