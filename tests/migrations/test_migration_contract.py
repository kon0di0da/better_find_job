"""TC-MIGRATION-001: canonical PostgreSQL migration acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Connection, Engine, create_engine
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
CANONICAL_DDL = ROOT / "specs" / "ddl" / "v0.2.sql"
SCHEMAS = ("profile", "knowledge", "interview")
UP_FILES = (
    MIGRATIONS / "profile" / "0001_initial.up.sql",
    MIGRATIONS / "knowledge" / "0001_initial.up.sql",
    MIGRATIONS / "interview" / "0001_initial.up.sql",
)
DOWN_FILES = (
    MIGRATIONS / "profile" / "0001_initial.down.sql",
    MIGRATIONS / "knowledge" / "0001_initial.down.sql",
    MIGRATIONS / "interview" / "0001_initial.down.sql",
)
REVISION_FILES = (
    MIGRATIONS / "profile" / "0001_initial.py",
    MIGRATIONS / "knowledge" / "0001_initial.py",
    MIGRATIONS / "interview" / "0001_initial.py",
)


def _split_sql(text: str) -> tuple[str, ...]:
    """Split the controlled DDL subset, which contains no procedural blocks."""
    return tuple(statement.strip() for statement in text.split(";") if statement.strip())


def _normalize(statement: str) -> str:
    return re.sub(r"\s+", " ", statement).strip()


def _alembic_config(database_url: str) -> Config:
    config = Config(str(MIGRATIONS / "alembic.ini"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config


def _reset_schemas(connection: Connection) -> None:
    connection.exec_driver_sql("DROP TABLE IF EXISTS public.alembic_version")
    for schema in reversed(SCHEMAS):
        connection.exec_driver_sql(f"DROP SCHEMA IF EXISTS {schema} CASCADE")


def _execute_script(connection: Connection, path: Path) -> None:
    for statement in _split_sql(path.read_text(encoding="utf-8")):
        connection.exec_driver_sql(statement)


def _schema_checksum(connection: Connection) -> str:
    columns = connection.exec_driver_sql(
        """
        SELECT table_schema, table_name, ordinal_position, column_name,
               data_type, udt_name, is_nullable, COALESCE(column_default, '')
        FROM information_schema.columns
        WHERE table_schema IN ('profile', 'knowledge', 'interview')
        ORDER BY table_schema, table_name, ordinal_position
        """
    ).all()
    constraints = connection.exec_driver_sql(
        """
        SELECT namespace.nspname, relation.relname, constraint_row.conname,
               constraint_row.contype,
               pg_get_constraintdef(constraint_row.oid, true)
        FROM pg_constraint AS constraint_row
        JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid
        JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace
        WHERE namespace.nspname IN ('profile', 'knowledge', 'interview')
        ORDER BY namespace.nspname, relation.relname, constraint_row.conname
        """
    ).all()
    indexes = connection.exec_driver_sql(
        """
        SELECT schemaname, tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname IN ('profile', 'knowledge', 'interview')
        ORDER BY schemaname, tablename, indexname
        """
    ).all()
    payload = {
        "columns": [list(row) for row in columns],
        "constraints": [list(row) for row in constraints],
        "indexes": [list(row) for row in indexes],
    }
    encoded = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _assert_destructive_test_database() -> str:
    assert os.getenv("ALLOW_DESTRUCTIVE_MIGRATION_TEST") == "1", (
        "set ALLOW_DESTRUCTIVE_MIGRATION_TEST=1 for the dedicated test database"
    )
    database_url = os.getenv("TEST_DATABASE_URL", "")
    assert database_url, "set TEST_DATABASE_URL to a dedicated PostgreSQL test database"
    parsed = make_url(database_url)
    assert parsed.drivername.startswith("postgresql"), "only PostgreSQL is supported"
    assert parsed.database and "test" in parsed.database.lower(), (
        "database name must contain 'test' to permit destructive migration checks"
    )
    return database_url


def test_tc_migration_001_layout_and_revision_chain() -> None:
    """All three bounded contexts participate in one deterministic chain."""
    required = (
        MIGRATIONS / "__init__.py",
        MIGRATIONS / "alembic.ini",
        MIGRATIONS / "env.py",
        MIGRATIONS / "sql_loader.py",
        *UP_FILES,
        *DOWN_FILES,
        *REVISION_FILES,
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    assert not missing, f"missing migration artifacts: {missing}"

    scripts = ScriptDirectory.from_config(_alembic_config("postgresql+psycopg://unused/test"))
    assert scripts.get_bases() == ["profile_0001"]
    assert scripts.get_heads() == ["interview_0001"]
    revisions = {revision.revision: revision.down_revision for revision in scripts.walk_revisions()}
    assert revisions == {
        "profile_0001": None,
        "knowledge_0001": "profile_0001",
        "interview_0001": "knowledge_0001",
    }


def test_tc_migration_001_sql_matches_canonical_ddl() -> None:
    """Migration SQL must contain exactly the canonical DDL statement set."""
    canonical = Counter(_normalize(item) for item in _split_sql(CANONICAL_DDL.read_text(encoding="utf-8")))
    migrated = Counter(
        _normalize(item)
        for path in UP_FILES
        for item in _split_sql(path.read_text(encoding="utf-8"))
    )
    assert migrated == canonical


def test_tc_migration_001_up_down_up_checksum() -> None:
    """A real PostgreSQL database must round-trip without schema drift."""
    database_url = _assert_destructive_test_database()
    engine: Engine = create_engine(database_url, pool_pre_ping=True)
    config = _alembic_config(database_url)

    try:
        with engine.begin() as connection:
            _reset_schemas(connection)
            _execute_script(connection, CANONICAL_DDL)
            canonical_checksum = _schema_checksum(connection)
            _reset_schemas(connection)

        command.upgrade(config, "head")
        with engine.connect() as connection:
            first_checksum = _schema_checksum(connection)
        assert first_checksum == canonical_checksum

        command.downgrade(config, "base")
        with engine.connect() as connection:
            remaining = connection.exec_driver_sql(
                "SELECT nspname FROM pg_namespace WHERE nspname IN ('profile', 'knowledge', 'interview')"
            ).all()
        assert remaining == []

        command.upgrade(config, "head")
        with engine.connect() as connection:
            second_checksum = _schema_checksum(connection)
        assert second_checksum == first_checksum
    finally:
        with engine.begin() as connection:
            _reset_schemas(connection)
        engine.dispose()
