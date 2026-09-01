"""Load controlled SQL migration files without SQLAlchemy text rewriting."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Connection


def split_sql(text: str) -> tuple[str, ...]:
    """Split the v0.2 DDL subset, which contains no procedural blocks."""
    return tuple(statement.strip() for statement in text.split(";") if statement.strip())


def execute_sql_file(connection: Connection, revision_file: str, sql_name: str) -> None:
    """Execute every statement in a SQL file adjacent to a revision module."""
    path = Path(revision_file).with_name(sql_name)
    for statement in split_sql(path.read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)
