import os

class Settings:
    PSQL_HOST = os.getenv("PSQL_HOST", "database")
    PSQL_PORT = int(os.getenv("PSQL_PORT", 5432))
    PSQL_USER = os.getenv("PSQL_USER", "mqtt")
    PSQL_PASS = os.getenv("PSQL_PASS", "smartallotment2026")
    PSQL_DB   = os.getenv("PSQL_DB", "sensors")

settings = Settings()
