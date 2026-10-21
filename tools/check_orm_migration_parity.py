#!/usr/bin/env python3
"""Static ORM <-> Alembic migration parity check (audit item R19). Standard library only.

It parses the SQLAlchemy models (`apps/api/app/db/models/*.py`) and replays the migrations
(`database/migrations/versions/*.py`, in revision order) with `ast`, then compares tables, columns,
nullability, type family/length, primary keys, foreign keys, unique keys and indexes. It cannot replace
`alembic check` against a real database, but it runs anywhere, in milliseconds, and it never passes
silently over something it cannot parse: unparseable operations and helper-built tables are WARN findings.

Usage: python tools/check_orm_migration_parity.py   (exit 1 if any DRIFT)
"""
from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

DRIFT, WARN = "DRIFT", "WARN"
_FAMILY = {
    "Integer": "int", "SmallInteger": "int", "BigInteger": "int", "String": "str", "Unicode": "str", "Text": "text",
    "Float": "float", "Numeric": "float", "Boolean": "bool", "DateTime": "datetime", "Date": "date", "Time": "time",
    "JSONB": "json", "JSON": "json", "UUID": "uuid", "LargeBinary": "bytes", "Enum": "str", "SAEnum": "str",
}
_PY_FAMILY = {"str": "str", "int": "int", "float": "float", "bool": "bool", "datetime": "datetime", "date": "date",
              "dict": "json", "list": "json", "UUID": "uuid", "uuid.UUID": "uuid"}


@dataclass
class Col:
    name: str
    nullable: bool
    family: str | None = None
    length: int | None = None
    pk: bool = False


@dataclass
class Table:
    name: str
    columns: dict[str, Col] = field(default_factory=dict)
    uniques: set[tuple[str, ...]] = field(default_factory=set)
    indexes: set[tuple[str, ...]] = field(default_factory=set)  # non-unique
    fks: dict[str, str] = field(default_factory=dict)  # column -> "table.column"
    partial: bool = False


@dataclass(frozen=True)
class Finding:
    severity: str
    kind: str
    table: str
    column: str | None
    detail: str


class Parsed(dict):
    """dict[str, Table] that also carries parser warnings."""

    def __init__(self) -> None:
        super().__init__()
        self.warnings: list[Finding] = []


# ---------------------------------------------------------------- ast helpers
def _callee(node: ast.AST) -> str | None:
    if isinstance(node, ast.Call):
        node = node.func
    if isinstance(node, ast.Attribute):
        return node.attr
    return node.id if isinstance(node, ast.Name) else None


def _kw(call: ast.Call, name: str) -> ast.AST | None:
    return next((k.value for k in call.keywords if k.arg == name), None)


def _lit(node: ast.AST | None):
    return node.value if isinstance(node, ast.Constant) else None


def _str_list(node: ast.AST | None) -> tuple[str, ...] | None:
    if isinstance(node, (ast.List, ast.Tuple)) and all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in node.elts):
        return tuple(e.value for e in node.elts)
    return None


def _type_info(node: ast.AST) -> tuple[str | None, int | None]:
    name = _callee(node)
    if name not in _FAMILY:
        return None, None
    length = None
    if isinstance(node, ast.Call):
        arg = node.args[0] if node.args else None
        length = _lit(arg) if isinstance(_lit(arg), int) else None
        if name in ("Enum", "SAEnum"):
            length = _lit(_kw(node, "length")) if isinstance(_lit(_kw(node, "length")), int) else None
    return _FAMILY[name], length


def _annotation_info(ann: ast.AST | None) -> tuple[bool, str | None]:
    """(allows None, python-type family) from Mapped[...]"""
    if ann is None:
        return False, None
    text = ast.unparse(ann)
    inner = text[text.index("[") + 1 : text.rindex("]")] if "Mapped[" in text else text
    allows_none = "None" in inner
    base = inner.replace("Optional[", "").replace("]", "").split("|")[0].strip().split("[")[0]
    return allows_none, _PY_FAMILY.get(base)


# ---------------------------------------------------------------- ORM side
def _add_orm_column(table: Table, attr: str, ann: ast.AST | None, call: ast.Call) -> None:
    args = list(call.args)
    name = attr
    if args and isinstance(_lit(args[0]), str):
        name = args.pop(0).value
    family, length = None, None
    for a in args:
        family, length = _type_info(a)
        if family:
            break
    allows_none, ann_family = _annotation_info(ann)
    family = family or ann_family
    pk = _lit(_kw(call, "primary_key")) is True
    nullable_kw = _lit(_kw(call, "nullable"))
    nullable = nullable_kw if isinstance(nullable_kw, bool) else (False if pk else allows_none)
    table.columns[name] = Col(name, nullable, family, length, pk)
    for a in args:
        if _callee(a) == "ForeignKey" and isinstance(a, ast.Call) and a.args and isinstance(_lit(a.args[0]), str):
            table.fks[name] = _lit(a.args[0])
    if _lit(_kw(call, "unique")) is True:
        table.uniques.add((name,))
    elif _lit(_kw(call, "index")) is True:
        table.indexes.add((name,))


def _table_args(table: Table, value: ast.AST, warnings: list[Finding]) -> None:
    items = value.elts if isinstance(value, (ast.Tuple, ast.List)) else [value]
    for item in items:
        kind = _callee(item)
        if kind not in ("UniqueConstraint", "Index") or not isinstance(item, ast.Call):
            continue
        cols = item.args[1:] if kind == "Index" else item.args
        names = tuple(_lit(c) for c in cols if isinstance(_lit(c), str))
        if len(names) != len(cols):
            table.partial = True
            warnings.append(Finding(WARN, "PARTIAL_PARSE", table.name, None, f"{kind} with non-literal columns"))
            continue
        unique = kind == "UniqueConstraint" or _lit(_kw(item, "unique")) is True
        (table.uniques if unique else table.indexes).add(names)


def parse_orm_sources(sources: list[str]) -> Parsed:
    classes: dict[str, ast.ClassDef] = {}
    for src in sources:
        for node in ast.parse(src).body:
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
    out = Parsed()

    def collect(cls: ast.ClassDef, table: Table, seen: set[str]) -> None:
        for base in cls.bases:  # mixins first, so subclasses override
            base_name = _callee(base)
            if base_name in classes and base_name not in seen:
                seen.add(base_name)
                collect(classes[base_name], table, seen)
        for stmt in cls.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name) and isinstance(stmt.value, ast.Call) \
                    and _callee(stmt.value) in ("mapped_column", "Column"):
                _add_orm_column(table, stmt.target.id, stmt.annotation, stmt.value)
            elif isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
                target = stmt.targets[0].id
                if target == "__table_args__":
                    _table_args(table, stmt.value, out.warnings)
                elif isinstance(stmt.value, ast.Call) and _callee(stmt.value) == "Column":
                    _add_orm_column(table, target, None, stmt.value)

    for cls in classes.values():
        tablename = next((_lit(s.value) for s in cls.body if isinstance(s, ast.Assign) and any(getattr(t, "id", "") == "__tablename__" for t in s.targets)), None)
        if isinstance(tablename, str):
            table = Table(tablename)
            collect(cls, table, {cls.name})
            out[tablename] = table
    return out


# ---------------------------------------------------------------- migration side
def _mig_column(table: Table, call: ast.Call) -> None:
    args = list(call.args)
    name = _lit(args[0]) if args else None
    if not isinstance(name, str):
        table.partial = True
        return
    family, length = (None, None)
    for a in args[1:]:
        family, length = _type_info(a)
        if family:
            break
    pk = _lit(_kw(call, "primary_key")) is True
    nullable_kw = _lit(_kw(call, "nullable"))
    nullable = nullable_kw if isinstance(nullable_kw, bool) else (not pk)
    table.columns[name] = Col(name, False if pk else nullable, family, length, pk)
    for a in args[1:]:
        if _callee(a) == "ForeignKey" and isinstance(a, ast.Call) and a.args and isinstance(_lit(a.args[0]), str):
            table.fks[name] = _lit(a.args[0])
    if _lit(_kw(call, "unique")) is True:
        table.uniques.add((name,))
    elif _lit(_kw(call, "index")) is True:
        table.indexes.add((name,))


def _order(sources: list[tuple[str, str]]) -> list[tuple[str, ast.Module]]:
    by_rev: dict[str, tuple[str, ast.Module, str | None]] = {}
    for fname, src in sources:
        tree = ast.parse(src)
        values = {t.id: _lit(s.value) for s in tree.body if isinstance(s, ast.Assign) for t in s.targets if isinstance(t, ast.Name)}
        rev = values.get("revision")
        if not isinstance(rev, str):
            raise ValueError(f"{fname}: no literal `revision`")
        by_rev[rev] = (fname, tree, values.get("down_revision"))
    children: dict[str | None, list[str]] = {}
    for rev, (_, _, down) in by_rev.items():
        children.setdefault(down, []).append(rev)
    ordered, current = [], None
    while current in children:
        if len(children[current]) != 1:
            raise ValueError(f"branching migration history after {current!r}: {children[current]}")
        current = children[current][0]
        ordered.append((by_rev[current][0], by_rev[current][1]))
    if len(ordered) != len(by_rev):
        raise ValueError("migration chain does not cover every revision")
    return ordered


def parse_migration_sources(sources: list[tuple[str, str]]) -> Parsed:
    out = Parsed()
    index_names: dict[str, tuple[str, tuple[str, ...], bool]] = {}

    def warn(fname: str, node: ast.AST, what: str) -> None:
        out.warnings.append(Finding(WARN, "UNPARSED_OPERATION", "*", None, f"{fname}:{getattr(node, 'lineno', '?')} {what}"))

    def drop_from(table: Table, col: str) -> None:
        table.columns.pop(col, None)
        table.fks.pop(col, None)
        table.uniques = {u for u in table.uniques if col not in u}
        table.indexes = {i for i in table.indexes if col not in i}

    for fname, tree in _order(sources):
        upgrade = next((n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None)
        if upgrade is None:
            continue
        calls = sorted((c for c in ast.walk(upgrade) if isinstance(c, ast.Call) and isinstance(c.func, ast.Attribute)
                        and isinstance(c.func.value, ast.Name) and c.func.value.id == "op"), key=lambda c: (c.lineno, c.col_offset))
        for call in calls:
            op, args = call.func.attr, call.args
            tname = _lit(args[0]) if args else None
            if op == "create_table":
                if not isinstance(tname, str):
                    warn(fname, call, "create_table with non-literal name")
                    continue
                table = Table(tname)
                for item in args[1:]:
                    kind = _callee(item)
                    if kind == "Column" and isinstance(item, ast.Call):
                        _mig_column(table, item)
                    elif kind == "UniqueConstraint" and isinstance(item, ast.Call):
                        cols = tuple(_lit(a) for a in item.args)
                        table.uniques.add(cols) if all(isinstance(c, str) for c in cols) else setattr(table, "partial", True)
                    elif kind == "ForeignKeyConstraint" and isinstance(item, ast.Call) and len(item.args) >= 2:
                        src, dst = _str_list(item.args[0]), _str_list(item.args[1])
                        if src and dst and len(src) == len(dst):
                            table.fks.update({s: d for s, d in zip(src, dst)})
                        else:
                            table.partial = True
                    elif kind == "PrimaryKeyConstraint" and isinstance(item, ast.Call):
                        for a in item.args:
                            if isinstance(_lit(a), str) and _lit(a) in table.columns:
                                table.columns[_lit(a)].pk, table.columns[_lit(a)].nullable = True, False
                    elif kind in ("CheckConstraint", "Index"):
                        continue
                    else:
                        table.partial = True
                for col in table.columns:
                    if (col,) in table.indexes:
                        index_names[f"ix_{tname}_{col}"] = (tname, (col,), False)
                if table.partial:
                    out.warnings.append(Finding(WARN, "PARTIAL_PARSE", tname, None, f"{fname}: columns built by helpers/expressions"))
                out[tname] = table
            elif op == "drop_table" and isinstance(tname, str):
                out.pop(tname, None)
            elif op == "add_column" and isinstance(tname, str) and len(args) > 1 and tname in out and _callee(args[1]) == "Column":
                _mig_column(out[tname], args[1])
            elif op == "drop_column" and isinstance(tname, str) and len(args) > 1 and tname in out and isinstance(_lit(args[1]), str):
                drop_from(out[tname], _lit(args[1]))
            elif op == "alter_column" and isinstance(tname, str) and len(args) > 1 and tname in out and _lit(args[1]) in out[tname].columns:
                col = out[tname].columns[_lit(args[1])]
                if isinstance(_lit(_kw(call, "nullable")), bool):
                    col.nullable = _lit(_kw(call, "nullable"))
                if _kw(call, "type_") is not None:
                    col.family, col.length = _type_info(_kw(call, "type_"))
            elif op == "create_index" and len(args) >= 3 and isinstance(_lit(args[0]), str) and isinstance(_lit(args[1]), str) and _str_list(args[2]):
                iname, table_name, cols = _lit(args[0]), _lit(args[1]), _str_list(args[2])
                unique = _lit(_kw(call, "unique")) is True
                if table_name in out:
                    (out[table_name].uniques if unique else out[table_name].indexes).add(cols)
                index_names[iname] = (table_name, cols, unique)
            elif op == "drop_index" and isinstance(tname, str):
                info = index_names.pop(tname, None)
                if info and info[0] in out:
                    (out[info[0]].uniques if info[2] else out[info[0]].indexes).discard(info[1])
                elif not info:
                    warn(fname, call, f"drop_index {tname!r}: index not created by a parsed operation")
            elif op == "create_unique_constraint" and len(args) >= 3 and isinstance(_lit(args[1]), str) and _str_list(args[2]):
                if _lit(args[1]) in out:
                    out[_lit(args[1])].uniques.add(_str_list(args[2]))
                index_names[tname] = (_lit(args[1]), _str_list(args[2]), True)
            elif op == "drop_constraint" and isinstance(tname, str) and _lit(_kw(call, "type_")) == "unique" and tname in index_names:
                info = index_names.pop(tname)
                if info[0] in out:
                    out[info[0]].uniques.discard(info[1])
            elif op in ("bulk_insert",):
                continue
            elif op == "execute":
                sql = " ".join(str(_lit(a) or "") for a in args).upper()
                if any(word in sql for word in ("ALTER ", "CREATE ", "DROP ")):
                    warn(fname, call, f"op.execute DDL: {sql[:60]!r}")
            else:
                warn(fname, call, f"op.{op}")
    return out


# ---------------------------------------------------------------- comparison
def compare(orm: Parsed, mig: Parsed) -> list[Finding]:
    out: list[Finding] = list(getattr(orm, "warnings", [])) + list(getattr(mig, "warnings", []))
    for name in sorted(set(orm) | set(mig)):
        if name not in mig:
            out.append(Finding(DRIFT, "TABLE_MISSING_IN_MIGRATIONS", name, None, "ORM model has no migration"))
            continue
        if name not in orm:
            out.append(Finding(DRIFT, "TABLE_MISSING_IN_ORM", name, None, "migrations create a table with no ORM model"))
            continue
        o, m = orm[name], mig[name]
        if m.partial or o.partial:
            out.append(Finding(WARN, "PARTIAL_PARSE", name, None, "column-level comparison skipped"))
            continue
        for col in sorted(set(o.columns) | set(m.columns)):
            if col not in m.columns:
                out.append(Finding(DRIFT, "COLUMN_MISSING_IN_MIGRATIONS", name, col, "in ORM, not in migrations"))
            elif col not in o.columns:
                out.append(Finding(DRIFT, "COLUMN_MISSING_IN_ORM", name, col, "in migrations, not in ORM"))
            else:
                a, b = o.columns[col], m.columns[col]
                if a.nullable != b.nullable:
                    out.append(Finding(DRIFT, "NULLABLE_MISMATCH", name, col, f"ORM nullable={a.nullable}, migrations nullable={b.nullable}"))
                if a.family and b.family and a.family != b.family:
                    out.append(Finding(DRIFT, "TYPE_MISMATCH", name, col, f"ORM {a.family}, migrations {b.family}"))
                elif a.family == b.family == "str" and a.length and b.length and a.length != b.length:
                    out.append(Finding(DRIFT, "LENGTH_MISMATCH", name, col, f"ORM {a.length}, migrations {b.length}"))
                if a.pk != b.pk:
                    out.append(Finding(DRIFT, "PK_MISMATCH", name, col, f"ORM pk={a.pk}, migrations pk={b.pk}"))
        for label, kind, ours, theirs in (("unique key", "UNIQUE_MISMATCH", o.uniques, m.uniques), ("index", "INDEX_MISMATCH", o.indexes, m.indexes)):
            for cols in sorted(ours - theirs):
                out.append(Finding(DRIFT, kind, name, ",".join(cols), f"{label} on ({', '.join(cols)}) in ORM, not in migrations"))
            for cols in sorted(theirs - ours):
                out.append(Finding(DRIFT, kind, name, ",".join(cols), f"{label} on ({', '.join(cols)}) in migrations, not in ORM"))
        for col in sorted(set(o.fks) | set(m.fks)):
            if o.fks.get(col) != m.fks.get(col):
                out.append(Finding(DRIFT, "FK_MISMATCH", name, col, f"ORM {o.fks.get(col)}, migrations {m.fks.get(col)}"))
    return out


def check_repo(root: Path) -> list[Finding]:
    models = sorted((root / "apps/api/app/db/models").glob("*.py"))
    versions = sorted((root / "database/migrations/versions").glob("*.py"))
    orm = parse_orm_sources([p.read_text(encoding="utf-8-sig") for p in models if p.name != "__init__.py"])  # utf-8-sig: 0007 starts with a BOM
    mig = parse_migration_sources([(p.name, p.read_text(encoding="utf-8-sig")) for p in versions])
    return compare(orm, mig)


def main() -> int:
    findings = check_repo(Path(__file__).resolve().parents[1])
    for f in findings:
        print(f"{f.severity:5s} {f.kind:30s} {f.table}.{f.column or '*'}  {f.detail}")
    drift = [f for f in findings if f.severity == DRIFT]
    print(f"\n{len(drift)} drift, {len(findings) - len(drift)} warnings")
    return 1 if drift else 0


if __name__ == "__main__":
    sys.exit(main())
