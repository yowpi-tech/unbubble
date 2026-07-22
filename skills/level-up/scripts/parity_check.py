#!/usr/bin/env python3
"""parity_check.py — App <-> schema parity check for the UnBubble level-up.

Detects target-schema tables and columns that the REBUILT application never
references in its source code. This catches the exact class of defect where a
field survives the whole pipeline — Bubble export -> clone AS-IS docs -> target
DATA-MODEL -> migrated schema — yet the reconstruction wires only a SUBSET of it
(classic example: a group of foreign keys and their lookup tables exist in the
migrated DB but the app's types/repository/UI never read or write them).

The clone step already guarantees "every active field appears in the docs" and
the DATA-MODEL step guarantees "every as-is field is mapped". This script closes
the loop on the last, previously-unguarded hop: **the code actually uses it.**

Deterministic and dependency-free (Python 3.8+, standard library only).
Read-only: it never modifies the app or the schema.

Usage:
  python3 parity_check.py --schema <path.sql | dir-of-sql | path.json> \
                          --app <app-source-dir> [--out <dir>]

Schema input:
  * .sql file or a directory of .sql files -> CREATE TABLE statements are parsed.
  * .json file shaped as {"tables": {"table_name": ["col", ...], ...}}.

Outputs (written to --out, default: current directory):
  parity-report.json   machine-readable coverage + orphan lists
  parity-report.md     human-readable report, orphans first

Exit code is 0 always (this is a report, not a gate) — read the report and
classify each orphan as: genuinely used elsewhere / intentionally deferred (say
why) / forgotten (fix it).
"""

import argparse
import json
import os
import re
import sys

# Columns that are structural/boilerplate and carry no parity signal: every
# table has them and they are not "features" of the model.
DEFAULT_IGNORED_COLUMNS = {
    "id",
    "organization_id",
    "created_at",
    "updated_at",
    "bubble_id",
    "deleted_at",
}

# First token of a CREATE TABLE entry that introduces a constraint, not a column.
CONSTRAINT_KEYWORDS = {
    "constraint",
    "primary",
    "foreign",
    "unique",
    "check",
    "exclude",
    "like",
}

CODE_EXTENSIONS = (
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".py",
    ".rb",
    ".go",
    ".java",
    ".kt",
    ".php",
    ".sql",
    ".prisma",
)

SKIP_DIRS = {
    "node_modules",
    ".git",
    ".next",
    "dist",
    "build",
    "coverage",
    ".turbo",
    "vendor",
    "__pycache__",
    ".venv",
}

TOKEN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def strip_sql_comments(text):
    text = re.sub(r"--[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


def split_top_level(body):
    """Split a CREATE TABLE body on commas that are at parenthesis depth 0."""
    parts = []
    depth = 0
    current = []
    for char in body:
        if char == "(":
            depth += 1
            current.append(char)
        elif char == ")":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current))
    return parts


def parse_sql(text):
    """Return {table_name: [column_name, ...]} from CREATE TABLE statements."""
    text = strip_sql_comments(text)
    tables = {}
    # Match "create table [if not exists] [schema.]name (" and capture the body
    # up to the matching close paren by scanning depth.
    for match in re.finditer(
        r"create\s+table\s+(?:if\s+not\s+exists\s+)?"
        r"(?:[\"`]?\w+[\"`]?\.)?[\"`]?(\w+)[\"`]?\s*\(",
        text,
        flags=re.I,
    ):
        table = match.group(1)
        start = match.end()
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == "(":
                depth += 1
            elif text[i] == ")":
                depth -= 1
            i += 1
        body = text[start : i - 1]
        columns = []
        for entry in split_top_level(body):
            entry = entry.strip()
            if not entry:
                continue
            first = entry.split(None, 1)[0].strip('"`').lower()
            if first in CONSTRAINT_KEYWORDS:
                continue
            token = re.match(r"[\"`]?(\w+)", entry)
            if token:
                columns.append(token.group(1))
        # de-dup, keep order
        seen = set()
        ordered = []
        for col in columns:
            if col not in seen:
                seen.add(col)
                ordered.append(col)
        tables[table] = ordered
    return tables


def load_schema(path):
    if os.path.isdir(path):
        merged = {}
        for name in sorted(os.listdir(path)):
            if name.endswith(".sql"):
                with open(os.path.join(path, name), encoding="utf-8") as handle:
                    merged.update(parse_sql(handle.read()))
        return merged
    if path.endswith(".json"):
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
        tables = data.get("tables", data)
        return {name: list(cols) for name, cols in tables.items()}
    with open(path, encoding="utf-8") as handle:
        return parse_sql(handle.read())


def collect_code_tokens(app_dir):
    """Return a set of every identifier token that appears anywhere in code."""
    tokens = set()
    files = 0
    for root, dirs, names in os.walk(app_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in names:
            if not name.endswith(CODE_EXTENSIONS):
                continue
            path = os.path.join(root, name)
            try:
                with open(path, encoding="utf-8", errors="ignore") as handle:
                    tokens.update(TOKEN_RE.findall(handle.read()))
                files += 1
            except OSError:
                continue
    return tokens, files


def is_low_signal_column(name):
    """A short, single-word column name (e.g. name, status, active) collides with
    ordinary identifiers, so its absence is not conclusive — report separately."""
    return "_" not in name and len(name) < 10


def main():
    parser = argparse.ArgumentParser(description="App<->schema parity check.")
    parser.add_argument("--schema", required=True, help=".sql file/dir or .json")
    parser.add_argument("--app", required=True, help="app source directory")
    parser.add_argument("--out", default=".", help="output directory")
    parser.add_argument(
        "--ignore-tables",
        default="",
        help="comma-separated table names to skip",
    )
    args = parser.parse_args()

    schema = load_schema(args.schema)
    ignore_tables = {t.strip() for t in args.ignore_tables.split(",") if t.strip()}
    schema = {t: cols for t, cols in schema.items() if t not in ignore_tables}
    if not schema:
        print("No tables parsed from --schema. Check the path/format.", file=sys.stderr)
        sys.exit(1)

    tokens, file_count = collect_code_tokens(args.app)

    report_tables = []
    orphan_tables = []
    orphan_columns = []       # high-confidence (composite/long names)
    ambiguous_columns = []    # low-signal names, verify manually
    total_columns = 0
    used_columns = 0

    for table in sorted(schema):
        columns = schema[table]
        table_used = table in tokens
        if not table_used:
            orphan_tables.append(table)
        col_entries = []
        for col in columns:
            if col in DEFAULT_IGNORED_COLUMNS:
                continue
            total_columns += 1
            used = col in tokens
            if used:
                used_columns += 1
            low = is_low_signal_column(col)
            col_entries.append({"name": col, "referenced": used, "low_signal": low})
            if not used:
                target = ambiguous_columns if low else orphan_columns
                target.append(f"{table}.{col}")
        report_tables.append(
            {"name": table, "referenced": table_used, "columns": col_entries}
        )

    summary = {
        "app_dir": os.path.abspath(args.app),
        "schema": os.path.abspath(args.schema),
        "code_files_scanned": file_count,
        "tables_total": len(schema),
        "tables_orphaned": len(orphan_tables),
        "columns_considered": total_columns,
        "columns_referenced": used_columns,
        "columns_orphaned_high_confidence": len(orphan_columns),
        "columns_orphaned_low_signal": len(ambiguous_columns),
        "column_coverage_pct": round(100.0 * used_columns / total_columns, 1)
        if total_columns
        else 100.0,
    }

    os.makedirs(args.out, exist_ok=True)
    json_path = os.path.join(args.out, "parity-report.json")
    with open(json_path, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "summary": summary,
                "orphan_tables": orphan_tables,
                "orphan_columns_high_confidence": sorted(orphan_columns),
                "orphan_columns_low_signal": sorted(ambiguous_columns),
                "tables": report_tables,
            },
            handle,
            indent=2,
            ensure_ascii=False,
        )

    lines = []
    lines.append("# Parity check — app vs. target schema\n")
    lines.append(
        f"- App scanned: `{summary['app_dir']}` ({file_count} code files)\n"
        f"- Schema: `{summary['schema']}` ({summary['tables_total']} tables)\n"
        f"- Column coverage: **{summary['column_coverage_pct']}%** "
        f"({used_columns}/{total_columns} non-structural columns referenced)\n"
    )
    lines.append(
        "\n> Heuristic: a table/column is 'referenced' if its exact snake_case "
        "identifier appears anywhere in the code (DB column names surface in "
        "query strings). Structural columns "
        f"({', '.join(sorted(DEFAULT_IGNORED_COLUMNS))}) are ignored. Short "
        "single-word column names are reported as *low-signal* (verify by hand).\n"
    )

    lines.append("\n## Orphan tables (never referenced)\n")
    if orphan_tables:
        for table in orphan_tables:
            lines.append(f"- `{table}` — {len(schema[table])} columns, table name absent from code\n")
    else:
        lines.append("_None._\n")

    lines.append("\n## Orphan columns — high confidence (composite/long names)\n")
    if orphan_columns:
        for item in sorted(orphan_columns):
            lines.append(f"- `{item}`\n")
    else:
        lines.append("_None._\n")

    lines.append("\n## Orphan columns — low signal (short names, verify manually)\n")
    if ambiguous_columns:
        for item in sorted(ambiguous_columns):
            lines.append(f"- `{item}`\n")
    else:
        lines.append("_None._\n")

    lines.append(
        "\n## What to do with each orphan\n"
        "Classify every item above as one of:\n"
        "1. **Used** — referenced by another name (view, generated type, RPC). "
        "Note where.\n"
        "2. **Deferred** — intentionally not built yet. Record it as a BACKLOG "
        "story with a reason.\n"
        "3. **Forgotten** — should be wired now. Fix the types/repository/UI.\n"
    )

    md_path = os.path.join(args.out, "parity-report.md")
    with open(md_path, "w", encoding="utf-8") as handle:
        handle.write("".join(lines))

    print(f"Parity check: {summary['column_coverage_pct']}% column coverage, "
          f"{len(orphan_tables)} orphan table(s), "
          f"{len(orphan_columns)} high-confidence orphan column(s).")
    print(f"  {md_path}")
    print(f"  {json_path}")


if __name__ == "__main__":
    main()
