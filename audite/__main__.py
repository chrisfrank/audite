import argparse
import sqlite3

from .auditor import track_changes


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("db_path")
    args = parser.parse_args()

    db = sqlite3.connect(args.db_path)
    track_changes(db)
    print(f"auditing enabled for {args.db_path}")


if __name__ == "__main__":
    main()
