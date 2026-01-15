"""Schema Loader Lambda – executes uploaded .sql files against PostgreSQL and
writes a JSON status artefact next to the original object.

Environment variables expected:
  DB_SECRET_ARN – Secrets Manager ARN with { "username": "…", "password": "…" }
  DB_ENDPOINT   – <hostname>[:port]
  DB_NAME       – database name (default: capstonedb)

The secret may also include the host/port; adjust as needed.
"""

import json
import os
import tempfile
import traceback
from datetime import datetime


import boto3
import psycopg  # type: ignore

s3 = boto3.client("s3")
secrets_client = boto3.client("secretsmanager")

def _download_object(bucket: str, key: str, local_path: str):
    s3.download_file(bucket, key, local_path)


def _get_db_credentials(secret_arn: str):
    resp = secrets_client.get_secret_value(SecretId=secret_arn)
    return json.loads(resp["SecretString"])


def handler(event, _context):
    db_secret_arn = event.get('db_secret_arn', os.environ.get('DB_SECRET_ARN'))
    creds = _get_db_credentials(db_secret_arn)

    # Require all DB connection info from the secret
    required_fields = ["host", "port", "dbname", "username", "password"]
    missing = [f for f in required_fields if f not in creds or not creds[f]]
    if missing:
        raise ValueError(f"Missing required DB connection fields in secret: {', '.join(missing)}")

    host = creds["host"]
    port = int(creds["port"])
    dbname = creds["dbname"]
    user = creds["username"]
    password = creds["password"]

    # Accept S3 location or SQL text from event
    bucket = event.get('s3_bucket')
    key = event.get('s3_key')
    sql_text = event.get('sql_text')

    status = {
        "executed_at": datetime.utcnow().isoformat() + "Z",
    }

    try:
        if sql_text is None:
            if not bucket or not key:
                raise ValueError("Must provide either sql_text or both s3_bucket and s3_key in event")
            sql_fd, sql_path = tempfile.mkstemp(suffix=".sql")
            os.close(sql_fd)
            _download_object(bucket, key, sql_path)
            with open(sql_path, "r", encoding="utf-8") as fh:
                sql_text = fh.read()
            status["executed_file"] = key
        else:
            status["executed_file"] = "inline_sql"

        with psycopg.connect(
            host=host,
            port=port,
            dbname=dbname,
            user=user,
            password=password,
        ) as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)  # type: ignore[arg-type]
            with conn.cursor() as verify:
                verify.execute(
                    """
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_type = 'BASE TABLE'
                      AND table_schema NOT IN ('pg_catalog', 'information_schema')
                    ORDER BY table_schema, table_name
                    """
                )
                rows = verify.fetchall()
                status["tables"] = json.dumps([
                    {"schema": r[0], "table": r[1]} for r in rows
                ])
                status["schemas"] = json.dumps(sorted({r[0] for r in rows}))
        status["status"] = "SUCCESS"
    except Exception as exc:
        status["status"] = "FAILED"
        status["error"] = str(exc)
        status["traceback"] = traceback.format_exc()

    # Optionally write status artefact back to S3 if bucket/key provided
    if bucket and key:
        status_key = key.replace("schema/", "schema-status/") + ".json"
        s3.put_object(
            Bucket=bucket,
            Key=status_key,
            Body=json.dumps(status, indent=2).encode("utf-8"),
            ContentType="application/json",
        )

    return status