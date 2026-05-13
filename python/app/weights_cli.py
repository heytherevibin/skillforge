"""Export / import per-user skill_weights rows (JSON snapshot)."""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from app.db_paths import resolve_orchestrator_db
from app.main import init_db


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Export or import learned skill_weights (uses, thumbs, routing bias).")
    sub = p.add_subparsers(dest="cmd", required=True)

    ex = sub.add_parser("export", help="Dump skill_weights rows to JSON (stdout unless -o).")
    ex.add_argument("-o", "--output", type=Path, default=None, help="Output file (default: stdout).")
    ex.add_argument("--user-id", default="", help="Logical user id (default '' = global row set).")
    ex.add_argument(
        "--project-root",
        default="",
        help="Resolve DB from <root>/.skillforge/orchestrator.db (else env / global).",
    )

    im = sub.add_parser("import", help="Load JSON snapshot into skill_weights.")
    im.add_argument("file", type=Path, help="JSON file from skillforge weights export.")
    im.add_argument(
        "--user-id",
        default=None,
        help="Override user_id for all imported rows (default: use file's user_id).",
    )
    im.add_argument(
        "--project-root",
        default="",
        help="Target DB path (same as export).",
    )
    im.add_argument(
        "--replace-user",
        action="store_true",
        help="Delete existing rows for the target user_id before import.",
    )
    return p.parse_args(argv)


def export_weights(con, user_id: str) -> dict:
    cur = con.execute(
        """
        SELECT skill_name, weight, uses, referenced, thumbs_up, thumbs_down, disabled, updated_at
        FROM skill_weights WHERE user_id = ? ORDER BY skill_name
        """,
        (user_id,),
    )
    rows = []
    for r in cur.fetchall():
        rows.append({
            "skill_name": r[0],
            "weight": float(r[1]),
            "uses": int(r[2]),
            "referenced": int(r[3]),
            "thumbs_up": int(r[4]),
            "thumbs_down": int(r[5]),
            "disabled": int(r[6]),
            "updated_at": float(r[7]) if r[7] is not None else None,
        })
    return {"version": 1, "user_id": user_id, "exported_at": time.time(), "rows": rows}


def import_weights(con, data: dict, *, user_id_override: str | None, replace_user: bool) -> int:
    if not isinstance(data, dict):
        raise ValueError("root must be object")
    rows = data.get("rows")
    if not isinstance(rows, list):
        raise ValueError("rows must be array")
    uid = user_id_override if user_id_override is not None else str(data.get("user_id") or "")
    if replace_user:
        con.execute("DELETE FROM skill_weights WHERE user_id = ?", (uid,))
    n = 0
    now = time.time()
    for raw in rows:
        if not isinstance(raw, dict):
            continue
        name = raw.get("skill_name")
        if not name or not isinstance(name, str):
            continue
        con.execute(
            """
            INSERT INTO skill_weights
            (user_id, skill_name, weight, uses, referenced, thumbs_up, thumbs_down, disabled, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, skill_name) DO UPDATE SET
                weight = excluded.weight,
                uses = excluded.uses,
                referenced = excluded.referenced,
                thumbs_up = excluded.thumbs_up,
                thumbs_down = excluded.thumbs_down,
                disabled = excluded.disabled,
                updated_at = excluded.updated_at
            """,
            (
                uid,
                name,
                float(raw.get("weight", 0.0)),
                int(raw.get("uses", 0)),
                int(raw.get("referenced", 0)),
                int(raw.get("thumbs_up", 0)),
                int(raw.get("thumbs_down", 0)),
                int(raw.get("disabled", 0)),
                float(raw.get("updated_at") or now),
            ),
        )
        n += 1
    con.commit()
    return n


def main(argv: list[str] | None = None) -> None:
    args = _parse_args(argv)
    pr = (getattr(args, "project_root", "") or "").strip() or None
    db_path = resolve_orchestrator_db(pr)
    con = init_db(db_path)
    try:
        if args.cmd == "export":
            payload = export_weights(con, args.user_id)
            text = json.dumps(payload, indent=2)
            if args.output:
                args.output.write_text(text + "\n", encoding="utf-8")
                print(f"Wrote {len(payload['rows'])} rows → {args.output}", file=sys.stderr)
            else:
                print(text)
            raise SystemExit(0)
        if args.cmd == "import":
            path = args.file.expanduser().resolve()
            if not path.is_file():
                print(f"skillforge weights import: not found {path}", file=sys.stderr)
                raise SystemExit(2)
            data = json.loads(path.read_text(encoding="utf-8"))
            n = import_weights(
                con,
                data,
                user_id_override=args.user_id,
                replace_user=bool(args.replace_user),
            )
            print(f"Imported {n} row(s) into {db_path}", file=sys.stderr)
            raise SystemExit(0)
    finally:
        con.close()


if __name__ == "__main__":
    main()
