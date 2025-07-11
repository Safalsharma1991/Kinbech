from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base
import os

SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///test.db")

if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
    )
else:
    # Render's DATABASE_URL may include an unsupported check_same_thread parameter
    # copied from local settings. Clean it if present before creating the engine.
    if "check_same_thread" in SQLALCHEMY_DATABASE_URL:
        from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

        parsed = urlparse(SQLALCHEMY_DATABASE_URL)
        query = parse_qs(parsed.query)
        query.pop("check_same_thread", None)
        cleaned = parsed._replace(query=urlencode(query, doseq=True))
        SQLALCHEMY_DATABASE_URL = urlunparse(cleaned)
    engine = create_engine(SQLALCHEMY_DATABASE_URL)


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base = declarative_base()

# ✅ Add this


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
