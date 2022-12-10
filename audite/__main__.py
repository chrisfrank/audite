import argparse
import sqlite3
import sys
import typing as t

from .auditor import track_changes


def main(args: t.List[str]) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path")
    parser.add_argument("-t", "--table", action="append")

    config = parser.parse_args(args)
    db = sqlite3.connect(config.db_path)
    track_changes(
        db,
        tables=config.table,
    )
    print(f"auditing enabled for {config.db_path}")


if __name__ == "__main__":
    main(sys.argv[1:])
