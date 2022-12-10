import pathlib
import sqlite3
import subprocess
import tempfile

from audite.__main__ import main


def test_cli() -> None:
    with tempfile.TemporaryDirectory() as workspace:
        dbpath = (workspace / pathlib.Path("test.db")).resolve()
        db = sqlite3.connect(dbpath, isolation_level=None)
        db.execute("CREATE TABLE post (id INTEGER PRIMARY KEY, content TEXT)")

        subprocess.run(
            ["python3", "-m", "audite", dbpath, "--table", "post"],
            check=True,
        )
        db.execute("INSERT INTO POST (content) VALUES ('audited')")
        history = db.execute("SELECT * FROM audite_changefeed").fetchall()
        assert len(history) == 1

def test_main() -> None:
    with tempfile.TemporaryDirectory() as workspace:
        dbpath = (workspace / pathlib.Path("test.db")).resolve()
        db = sqlite3.connect(dbpath, isolation_level=None)
        db.execute("CREATE TABLE post (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE comment (id TEXT PRIMARY KEY)")
        db.execute("CREATE TABLE author (id TEXT PRIMARY KEY)")

        main([str(dbpath), "-t", "post", "-t", "author"])

        db.execute("INSERT INTO post (id) VALUES ('post')")
        db.execute("INSERT INTO comment (id) VALUES ('comment')")
        db.execute("INSERT INTO author (id) VALUES ('comment')")

        query ="SELECT subject FROM audite_changefeed ORDER BY id"
        history = list(db.execute(query))
        assert history == [('post',),('comment',)]
