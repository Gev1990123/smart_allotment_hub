import psycopg2
from psycopg2.extras import RealDictCursor
import os

def get_connection():
    return psycopg2.connect(
        host=os.getenv("PSQL_HOST", "database"),
        port=os.getenv("PSQL_PORT", "5432"),
        user=os.getenv("PSQL_USER", "mqtt"),
        password=os.getenv("PSQL_PASS", "smartallotment2026"),
        database=os.getenv("PSQL_DB", "sensors")
    )