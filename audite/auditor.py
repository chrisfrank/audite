import sqlite3
import typing as t

HISTORY_TABLE = "_audite_history"


class Record(t.NamedTuple):
    position: int
    tblname: str
    rowname: str
    operation: str
    changed_at: int
    newval: t.Optional[str] = None
    oldval: t.Optional[str] = None


def _gen_audit_table_ddl(table_name: str) -> str:
    ddl = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        position INTEGER PRIMARY KEY AUTOINCREMENT,
        tblname TEXT NOT NULL,
        rowname TEXT NOT NULL,
        operation TEXT NOT NULL,
        changed_at INTEGER NOT NULL DEFAULT (strftime('%s', CURRENT_TIMESTAMP)),
        newval TEXT,
        oldval TEXT
    );
    """
    return ddl


def _json_object_sql(ref: t.Literal["OLD", "NEW"], cols: t.List[str]) -> str:
    """
    Approximates pg's 'row_to_json()' function by inspecting the table schema
    and building a json_object(label1, value1, label2, value2...) expression.

    https://www.sqlite.org/json1.html#jobj
    """

    sql = "json_object(" + ", ".join([f"'{col}', {ref}.{col}" for col in cols]) + ")"
    return sql


def _build_newval_oldval_sql(cols: t.List[str], event: str) -> t.Tuple[str, str]:
    if event == "DELETE":
        return "NULL", _json_object_sql("OLD", cols)
    elif event == "UPDATE":
        return _json_object_sql("NEW", cols), _json_object_sql("OLD", cols)
    elif event == "INSERT":
        return _json_object_sql("NEW", cols), "NULL"

    raise ValueError(f"{event} is not one of INSERT, UPDATE, or DELETE")


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

    # for tables with a single-column primary key, rowname is just the primary
    # key as text. for compound primary keys, concatenate each key separated by
    # '/', so that e.g. (1,) becomes '1' and (1, 'abc') becomes '1/abc'
    rowname = " || '/' || ".join(key_columns)

    newval, oldval = _build_newval_oldval_sql(all_columns, event)

    statement = f"""
    CREATE TRIGGER {trigger_name} AFTER {event} ON {table}
    BEGIN
        INSERT INTO {history_table} (tblname, rowname, operation, newval, oldval)
        VALUES ('{table}', {rowname}, '{event[:1]}', json({newval}), json({oldval}));
    END;
    """
    cursor.execute(statement)


def _create_indices(db: sqlite3.Connection, history_table: str) -> None:
    # Support querying the history of a particular record:
    # SELECT * from _audite_history WHERE (tablename, rowname) = ('post', '123')
    db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {history_table}_tblname_rowname_position_idx
        ON {history_table} (tblname, rowname, position)
        """
    )

    # Support querying by timestamp:
    # SELECT * from _audite_history WHERE changed_at > 123 AND changed_at < 456;
    db.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {history_table}_changed_at_position_idx
        ON {history_table} (changed_at, position)
        """
    )


def track_changes(
    db: sqlite3.Connection,
    history_table: str = HISTORY_TABLE,
    tables: t.Optional[t.List[str]] = None,
    autoindex: bool = True,
) -> None:
    events = ["INSERT", "UPDATE", "DELETE"]
    with db:
        if db.in_transaction:
            msg = (
                "Cannot enable auditing: this connection already has a "
                "transaction in progress. COMMIT or ROLLBACK and try again."
            )
            raise sqlite3.ProgrammingError(msg)
        db.execute("BEGIN")
        db.execute(_gen_audit_table_ddl(history_table))

        if tables is None:
            tables = [
                row[0]
                for row in db.execute(
                    """
                    SELECT tbl_name FROM sqlite_master
                    WHERE type='table' AND tbl_name NOT LIKE 'sqlite%'
                    AND tbl_name != :history_table
                    """,
                    {"history_table": history_table},
                )
            ]

        for table in tables:
            for event in events:
                _track_table(
                    db,
                    table=table,
                    event=event,
                    history_table=history_table,
                )

        if autoindex:
            _create_indices(db, history_table)
