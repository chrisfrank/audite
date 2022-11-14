import json
import pathlib
import sqlite3
import subprocess
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


def test_it_audits_insert_update_and_delete_on_all_tables_by_default(
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
            SELECT position, tblname, rowname, operation, changed_at, newval, oldval
            from _audite_history ORDER BY position
            """
        )
    ]
    operations = [row.operation for row in history]
    assert operations == ["I", "I", "I", "I", "U", "D"]

    first_post_json = json.loads(history[0].newval or "{}")
    assert first_post_json["id"] == 1
    assert first_post_json["content"] == "first"

    deleted_post_oldval = json.loads(history[-1].oldval or "{}")
    assert deleted_post_oldval["content"] == "second"
    assert history[-1].newval is None

    update = [row for row in history if row.operation == "U"][0]
    assert json.loads(update.oldval or "")["content"] == "first comment"
    assert json.loads(update.newval or "")["content"] == "revised"


def test_it_supports_compound_primary_keys(db: sqlite3.Connection) -> None:
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
    history = list(db.execute("SELECT rowname FROM _audite_history"))
    assert history == [("hello/world/1/3.14159",)]


def test_it_does_not_miss_messages_when_recreating_tables_and_triggers(
    db: sqlite3.Connection,
) -> None:
    pass


def test_it_audits_changes_from_external_processes(db: sqlite3.Connection) -> None:
    _, _, dbpath = db.execute("PRAGMA database_list").fetchone()
    track_changes(db)
    script = [
        "import sqlite3",
        f"db = sqlite3.connect('{dbpath}', isolation_level=None)",
        """db.execute("INSERT INTO post (content) VALUES ('external')")""",
    ]
    args = ["python3", "-c", "\n".join(script)]
    subprocess.run(args, check=True)

    history = list(db.execute("SELECT tblname, rowname FROM _audite_history"))
    assert history == [("post", "1")]


def test_it_can_customize_table_name(db: sqlite3.Connection) -> None:
    track_changes(db, history_table="custom_history")
    db.execute("INSERT INTO post (content) VALUES ('first'), ('second')")

    history = list(db.execute("SELECT position FROM custom_history"))
    assert history == [(1,), (2,)]

    with pytest.raises(sqlite3.OperationalError):
        db.execute("SELECT * FROM _audite_history")


def test_it_can_audit_only_specified_tables(db: sqlite3.Connection) -> None:
    track_changes(db, tables=["post"])
    db.execute("INSERT INTO post (content) VALUES ('first')")
    db.execute(
        """
        INSERT INTO comment (id, post_id, content) VALUES
        ('comment.1', 1, 'first comment')
        """
    )
    history = list(db.execute("SELECT tblname FROM _audite_history"))
    assert history == [("post",)]


def test_it_follows_schema_changes(db: sqlite3.Connection) -> None:
    track_changes(db)

    with db:
        db.execute("INSERT INTO post (content) VALUES ('before')")
        db.execute("ALTER TABLE post ADD COLUMN version INTEGER")
        db.execute("ALTER TABLE post RENAME COLUMN content TO body")
        db.execute("CREATE TABLE not_yet_audited (value TEXT PRIMARY KEY)")

    with db:
        track_changes(db)
        db.execute("INSERT INTO post (body, version) VALUES ('after', 2)")
        db.execute("INSERT INTO not_yet_audited (value) VALUES ('audited now')")

    history = list(db.execute("SELECT newval FROM _audite_history"))
    changes = [json.loads(row[0] or "{}") for row in history]

    assert changes[0]["content"] == "before"
    assert "version" not in changes[0]

    assert "content" not in changes[1]
    assert changes[1]["body"] == "after"
    assert changes[1]["version"] == 2
    assert changes[2]["value"] == "audited now"


def test_it_raises_when_trying_to_enable_auditing_in_an_already_open_tx(
    db: sqlite3.Connection,
) -> None:
    db.execute("BEGIN")
    db.execute("INSERT INTO post (content) VALUES ('pending')")
    with pytest.raises(sqlite3.ProgrammingError):
        track_changes(db)
