import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

# ----------------------------------------------------------------------------
# Read database connection settings from environment variables
# ----------------------------------------------------------------------------

DB_USER = os.getenv("PSQL_USER", "mqtt")
DB_PASS = os.getenv("PSQL_PASS", "mqtt123")
DB_HOST = os.getenv("PSQL_HOST", "database")  # Docker compose service name
DB_PORT = os.getenv("PSQL_PORT", "5432")
DB_NAME = os.getenv("PSQL_DB", "sensors")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# ----------------------------------------------------------------------------
# Create SQLAlchemy engine
# ----------------------------------------------------------------------------
# pool_pre_ping=True prevents stale connections
# future=True enables SQLAlchemy 2.x style API
# ----------------------------------------------------------------------------

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    future=True
)

# ----------------------------------------------------------------------------
# Session factory for API layer
# ----------------------------------------------------------------------------

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    future=True
)

# ----------------------------------------------------------------------------
# Function to initialize all tables (only used by API bootstrap)
# ----------------------------------------------------------------------------

def init_db():
    """
    Creates database tables based on SQLAlchemy models.
    WARNING: Only use during development or initial deployment.
    In production, rely on schemas.sql or Alembic migrations.
    """
    Base.metadata.create_all(bind=engine)
