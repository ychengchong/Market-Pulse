"""Migrate and load a user-configured PostgreSQL database."""
import argparse
import json
import os
from pathlib import Path

from src.database import database_status, import_dataset, migrate
import psycopg


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("migrate", "import", "status"))
    parser.add_argument("--input", type=Path, default=Path("data/financial_facts.json"))
    args = parser.parse_args(argv)
    dsn = os.environ.get("DATABASE_URL")
    if not dsn:
        parser.error("Set DATABASE_URL locally; do not put credentials in source files")
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10, application_name="market-pulse") as conn:
            if args.command == "migrate":
                print(f"Database ready: {migrate(conn)} migration(s) verified")
            elif args.command == "import":
                print(json.dumps(import_dataset(conn, args.input), indent=2))
            else:
                print(json.dumps(database_status(conn), indent=2))
    except (psycopg.Error, OSError, ValueError, KeyError, TypeError) as error:
        print(f"Database operation failed ({type(error).__name__}). Check database configuration, migration status and input/snapshot integrity.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
