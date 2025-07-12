from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import os

# Fetch the database URL from the environment variable
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///test.db")

# If the database URL is for PostgreSQL, use it directly (no need to replace 'postgres://')
if SQLALCHEMY_DATABASE_URL.startswith("postgresql://"):
    engine = create_engine(SQLALCHEMY_DATABASE_URL)
else:
    # For SQLite or other databases (handled here just in case)
    engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
