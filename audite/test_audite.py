import json
import pathlib
import sqlite3
import tempfile
import typing as t

import pytest

from .auditor import Record, track_changes


@pytest.fixture
def db() -> t.Iterator[sqlite3.Connection]:
    """Creates a temporary database, yields it, then cleans up."""
    with tempfile.TemporaryDirectory() as workspace:
        dbpath = (workspace / pathlib.Path("test.db")).resolve()
        db = sqlite3.connect(dbpath)
        db.execute("CREATE TABLE post (id INTEGER PRIMARY KEY, content TEXT)")
        db.execute(
            """
            CREATE TABLE comment (
                id TEXT PRIMARY KEY,
                post_id INTEGER REFERENCES post (post_id),
                content TEXT
            )
            """
        )
        yield db


def test_audits_insert_update_and_delete_on_all_tables_by_default(
    db: sqlite3.Connection,
) -> None:
    track_changes(db)
    db.execute("INSERT INTO post (content) VALUES ('first'), ('second')")
    db.execute(
        """
        INSERT INTO comment (id, post_id, content) VALUES
        ('comment.1', 1, 'first comment'), ('comment.2', 1, 'second comment')
        """
    )
    db.execute("UPDATE comment SET content = 'revised' WHERE id = 'comment.1'")
    db.execute("DELETE from post WHERE id = 2")
    history = [
        Record(*row)
        for row in db.execute(
            """
            SELECT position, tblname, rowname, operation, changed_at, payload
            from _audite ORDER BY position
            """
        )
    ]
    operations = [row.operation for row in history]
    assert operations == ["I", "I", "I", "I", "U", "D"]

    # todo split payload into 'old' and 'new'
    first_post_json = json.loads(history[0].payload)
    assert first_post_json["id"] == 1
    assert first_post_json["content"] == "first"


def test_supports_compound_primary_keys(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE compound (
            this TEXT,
            that TEXT,
            other INTEGER,
            etc FLOAT,
            PRIMARY KEY (this, that, other, etc)
        )
        """
    )
    track_changes(db)
    db.execute(
        """
        INSERT INTO compound (this, that, other, etc)
        VALUES ('hello','world', 1, 3.14159)
        """
    )
    history = list(db.execute("SELECT rowname FROM _audite"))
    assert history == [("hello/world/1/3.14159",)]


def test_it_does_not_miss_messages_when_recreating_tables_and_triggers(
    db: sqlite3.Connection,
) -> None:
    pass


def test_it_audits_changes_from_external_connections(db: sqlite3.Connection) -> None:
    _, _, dbpath = db.execute("PRAGMA database_list").fetchone()
    pass


def test_it_can_customize_table_name(db: sqlite3.Connection) -> None:
    pass


def test_it_can_audit_only_specified_tables(db: sqlite3.Connection) -> None:
    pass
