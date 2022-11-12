import sqlite3
import typing as t

HISTORY_TABLE = "_audite_history"


class Record(t.NamedTuple):
    position: int
    tblname: str
    rowname: str
    operation: str
    changed_at: int
    payload: str = ""


def _gen_audit_table_ddl(table_name: str) -> str:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        position INTEGER PRIMARY KEY AUTOINCREMENT,
        tblname TEXT NOT NULL,
        rowname TEXT NOT NULL,
        operation TEXT NOT NULL,
        changed_at INTEGER NOT NULL DEFAULT (strftime('%s', CURRENT_TIMESTAMP)),
        payload TEXT
    );
    """
    return ddl


def _track_table(
    db: sqlite3.Connection, table: str, event: str, history_table: str
) -> None:
    cursor = db.cursor()
    record_ref = "OLD" if event == "DELETE" else "NEW"
    trigger_name = f"_audite_audit_{table}_{event.lower()}_trigger"

    cursor.execute(f"DROP TRIGGER IF exists {trigger_name}")

    fields = cursor.execute(
        "SELECT name, pk FROM PRAGMA_TABLE_INFO(:table) order by pk", {"table": table}
    ).fetchall()

    key_columns = [f"{record_ref}.{f[0]}" for f in fields if f[1] > 0]
    all_columns = [field[0] for field in fields]

    # for tables with a single-column primary key, rowname is just the
    # primary key as text. for compound primary keys, concatenate each
    # key separated by '/'
    rowname = " || '/' || ".join(key_columns)

    # sqlite doesn't have pg's `row_to_json()`, but json_obj_pairs works just
    # fine when we know the column names in advance.
    json_obj_pairs = ", ".join([f"'{col}', {record_ref}.{col}" for col in all_columns])

    statement = f"""
    CREATE TRIGGER {trigger_name} AFTER {event} ON {table}
    BEGIN
        INSERT INTO {history_table} (tblname, rowname, operation, payload) VALUES
        ('{table}', {rowname}, '{event[:1]}', json_object({json_obj_pairs}));
    END;
    """
    cursor.execute(statement)


def track_changes(db: sqlite3.Connection, history_table: str = HISTORY_TABLE) -> None:
    events = ["INSERT", "UPDATE", "DELETE"]
    with db:
        db.execute("BEGIN")
        db.execute(_gen_audit_table_ddl(history_table))
        tables = db.execute(
            """
            SELECT tbl_name FROM sqlite_master
            WHERE type='table' AND tbl_name NOT LIKE 'sqlite%'
            AND tbl_name != :history_table
            """,
            {"history_table": history_table},
        ).fetchall()

        for table in tables:
            for event in events:
                _track_table(
                    db,
                    table=table[0],
                    event=event,
                    history_table=history_table,
                )
