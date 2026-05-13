from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import os

# Create engine with PostgreSQL optimizations
# For PostgreSQL, we use connection pooling for better concurrency
if "postgresql" in settings.DATABASE_URL:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,
        pool_size=20,  # Base pool size for 100 concurrent users
        max_overflow=30,  # Allow up to 30 additional connections
        pool_recycle=3600,  # Recycle connections after 1 hour
        pool_timeout=30,  # Wait up to 30 seconds for a connection
        echo=False,  # Set to True for SQL debugging
    )
else:
    # SQLite fallback for development
    os.makedirs("./data", exist_ok=True)
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def ensure_schema_compatibility():
    """Apply small additive schema updates for deployments without Alembic.

    This project currently creates tables with SQLAlchemy metadata but does not
    run migrations. Keep this limited to nullable/additive columns so existing
    production data is not rewritten or made incompatible.
    """
    user_columns = {
        "display_name": "VARCHAR(255)",
        "plan": "VARCHAR(100)",
        "admin_notes": "TEXT",
        "last_login_at": "TIMESTAMP",
    }
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("users")}
    missing = [(name, column_type) for name, column_type in user_columns.items() if name not in existing]
    if not missing:
        return

    with engine.begin() as connection:
        for name, column_type in missing:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {column_type}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
