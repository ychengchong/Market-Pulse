"""Set up a private local database connection once for the app and refresh CLI."""
import argparse
import getpass
import json
from pathlib import Path

from src.db_config import prepare_driver
prepare_driver()
import psycopg
from psycopg.conninfo import make_conninfo


def connection_failure_reason(error):
    """Explain common setup failures without printing server text or credentials."""
    message = str(error).lower()
    if "password authentication failed" in message:
        return "PostgreSQL rejected the password for this user. Check the PostgreSQL password and keyboard layout."
    if "no password supplied" in message:
        return "No password reached PostgreSQL. Type your PostgreSQL password at the hidden prompt and press Enter."
    if "database" in message and "does not exist" in message:
        return "The database name was not found. Check the exact name in pgAdmin and pass it with --database."
    if "connection refused" in message or "timeout" in message or "timed out" in message:
        return "The PostgreSQL server could not be reached. Check that its service is running and the host/port are correct."
    return "Check the server, database name and credentials."


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--database", default="Market Pulse")
    parser.add_argument("--user", default="postgres")
    parser.add_argument("--replace", action="store_true", help="Replace an existing private local configuration")
    args = parser.parse_args(argv)
    path = Path(".streamlit/secrets.toml")
    if path.exists() and not args.replace:
        print("Local database settings already exist. Use --replace only if you intend to change them.")
        return 1
    password = getpass.getpass("PostgreSQL password (saved only in ignored local secrets.toml): ")
    dsn = make_conninfo(host=args.host, port=args.port, dbname=args.database, user=args.user, password=password)
    try:
        with psycopg.connect(dsn, connect_timeout=10) as conn:
            conn.execute("SELECT 1")
    except psycopg.Error as error:
        print("Connection failed. " + connection_failure_reason(error))
        print("No settings were saved. Fix the connection before running refresh_data.py.")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    # JSON string escaping is compatible with TOML basic string values.
    path.write_text("[database]\nurl = " + json.dumps(dsn) + "\n", encoding="utf-8", newline="\n")
    print("Connection verified and saved locally. Keep .streamlit/secrets.toml private; it is ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
