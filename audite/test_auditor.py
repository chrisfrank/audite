import datetime
import json
import pathlib
import sqlite3
import subprocess
import tempfile
import typing as t

import cloudevents.http  # type: ignore
import pytest

from .auditor import Event, track_changes


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
        Event(*row)
        for row in db.execute(
            """
            SELECT id, source, subject, type, time, specversion, data
            from audite_history ORDER BY id
            """
        )
    ]
    operations = [row.type for row in history]
    assert operations == [
        "post.created",
        "post.created",
        "comment.created",
        "comment.created",
        "comment.updated",
        "post.deleted",
    ]

    first_post_json = json.loads(history[0].data or "{}")
    assert first_post_json["new"]["id"] == 1
    assert first_post_json["new"]["content"] == "first"

    last_post_json = json.loads(history[-1].data or "{}")
    assert last_post_json["old"]["content"] == "second"

    update = [row for row in history if row.type == "comment.updated"][0]
    assert json.loads(update.data or "")["new"]["content"] == "revised"
    assert json.loads(update.data or "")["old"]["content"] == "first comment"


def test_it_supports_compound_primary_keys(db: sqlite3.Connection) -> None:
    db.execute(
        """
        CREATE TABLE "namespace.with_compound_pk" (
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
        INSERT INTO "namespace.with_compound_pk" (this, that, other, etc)
        VALUES ('hello','world', 1, 3.14159)
        """
    )
    history = list(db.execute("SELECT source, type, subject FROM audite_history"))

    assert history == [
        (
            "namespace.with_compound_pk",
            "namespace.with_compound_pk.created",
            "hello:world:1:3.14159",
        )
    ]


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

    history = list(db.execute("SELECT source, subject FROM audite_history"))
    assert history == [("post", "1")]


def test_it_can_audit_only_specified_tables(db: sqlite3.Connection) -> None:
    track_changes(db, tables=["post"])
    db.execute("INSERT INTO post (content) VALUES ('first')")
    db.execute(
        """
        INSERT INTO comment (id, post_id, content) VALUES
        ('comment.1', 1, 'first comment')
        """
    )
    history = list(db.execute("SELECT source FROM audite_history"))
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

    events = list(db.execute("SELECT data FROM audite_history"))
    changes = [json.loads(e[0] or "{}")["new"] for e in events]

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


def test_it_adds_indices_by_default(db: sqlite3.Connection) -> None:
    track_changes(db)
    idx_name = "audite_history_source_subject_id_idx"
    q = f"SELECT name FROM sqlite_master WHERE type='index' AND name = '{idx_name}'"

    idx = db.execute(q).fetchone()[0]
    assert idx

    db.execute(f"DROP INDEX {idx_name}")
    track_changes(db, autoindex=False)

    idx = db.execute(q).fetchone()
    assert idx is None


def test_it_conforms_to_the_cloudevents_spec(db: sqlite3.Connection) -> None:
    track_changes(db)
    db.execute("INSERT INTO post (content) VALUES ('p1'), ('p2'), ('p3');")

    q = "SELECT cloudevent FROM audite_cloudevents ORDER BY id"
    events = [cloudevents.http.from_json(row[0]) for row in db.execute(q)]

    # id should be a string
    assert events[0]["id"] == "1"
    # sequence should be the same 'number' as id but with enough zero-padding
    # to account for all the largest 64-bit unsigned integer
    assert events[0]["sequence"] == "00000000000000000001"
    # time should be parsable as ISO-8601
    assert datetime.datetime.fromisoformat(events[0]["time"])

    assert events[0]["source"] == "post"
    assert events[0]["subject"] == "1"
    assert events[0]["specversion"] == "1.0"
    assert events[0]["type"] == "post.created"
    assert events[0].data["new"]["content"] == "p1"

    # filtering by id with a string should work
    q = "SELECT cloudevent FROM audite_cloudevents WHERE id > :offset"
    filtered = [
        cloudevents.http.from_json(row[0])
        for row in db.execute(q, {"offset": events[0]["id"]})
    ]
    assert [e["id"] for e in filtered] == ["2", "3"]
