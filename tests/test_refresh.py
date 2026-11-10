"""Financial refresh failures and persistent private connection settings."""
import contextlib
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

from scripts import configure_database, refresh_data
import psycopg
from src.db_config import connection_string
from test_database import DatasetWorkspace


class RefreshTests(DatasetWorkspace):
    def test_setup_explains_authentication_failure_without_server_text(self):
        reason=configure_database.connection_failure_reason(psycopg.OperationalError('password authentication failed for user "private-user"'))
        self.assertIn("rejected the password",reason)
        self.assertNotIn("private-user",reason)

    def test_setup_distinguishes_missing_database_and_unreachable_server(self):
        reason=configure_database.connection_failure_reason(psycopg.OperationalError('database "private-name" does not exist'))
        self.assertIn("database name was not found",reason)
        self.assertNotIn("private-name",reason)
        self.assertIn("could not be reached",configure_database.connection_failure_reason(psycopg.OperationalError("connection refused")))

    def run_refresh(self, ingestion=0, connection_error=None, import_error=None):
        with patch.object(refresh_data,"connection_string",return_value="private-test-dsn"), \
             patch.object(refresh_data.psycopg,"connect") as connect, \
             patch.object(refresh_data,"migrate") as migrate, \
             patch.object(refresh_data.ingest_financials,"main",return_value=ingestion) as ingest, \
             patch.object(refresh_data,"import_dataset",return_value=dict(companies=1,selected_observations=2)) as publish, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            connect.side_effect=connection_error
            publish.side_effect=import_error
            code=refresh_data.main(["--offline"])
        return code,json.loads(Path("data/refresh_status.json").read_text()),ingest,publish,output.getvalue()

    def test_connection_failure_does_not_fetch_or_import(self):
        code,report,ingest,publish,output=self.run_refresh(connection_error=psycopg.OperationalError("secret-dsn"))
        self.assertEqual(code,1); self.assertEqual(report["stage"],"connection")
        ingest.assert_not_called();publish.assert_not_called()
        self.assertNotIn("secret-dsn",output+json.dumps(report))

    def test_failed_ingestion_cannot_import_old_json_as_new(self):
        code,report,ingest,publish,_=self.run_refresh(ingestion=1)
        self.assertEqual((code,report["status"],report["stage"]),(1,"failed","ingestion"))
        publish.assert_not_called()

    def test_rejected_import_is_reported(self):
        code,report,*_=self.run_refresh(import_error=ValueError("invalid snapshot"))
        self.assertEqual((code,report["stage"]),(1,"import"))

    def test_success_publishes_one_batch_and_forwards_offline(self):
        code,report,ingest,publish,_=self.run_refresh()
        self.assertEqual((code,report["status"]),(0,"success"))
        ingest.assert_called_once_with(["--offline"]);publish.assert_called_once()

    def test_private_settings_persist_without_terminal_environment(self):
        Path(".streamlit").mkdir()
        Path(".streamlit/secrets.toml").write_text('[database]\nurl = "local-connection"\n')
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(connection_string(),"local-connection")
        with patch.dict(os.environ,{"DATABASE_URL":"override"}):
            self.assertEqual(connection_string(),"override")

    def test_setup_verifies_before_saving_and_preserves_quoted_password(self):
        with patch.object(configure_database.getpass,"getpass",return_value="a'b\\c"), \
             patch.object(configure_database.psycopg,"connect"):
            self.assertEqual(configure_database.main([]),0)
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(psycopg.conninfo.conninfo_to_dict(connection_string())["password"],"a'b\\c")

    def test_setup_failure_cannot_replace_existing_settings(self):
        Path(".streamlit").mkdir(); path=Path(".streamlit/secrets.toml");path.write_text("original")
        with patch.object(configure_database.getpass,"getpass",return_value="private"), \
             patch.object(configure_database.psycopg,"connect",side_effect=psycopg.OperationalError("private")):
            self.assertEqual(configure_database.main(["--replace"]),1)
        self.assertEqual(path.read_text(),"original")

