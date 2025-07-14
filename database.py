from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models import Base

SQLALCHEMY_DATABASE_URL = "postgresql://kinbech_database_user:mi55OxsKZfBm83ziODhz9joYmIsw4O1s@dpg-d1qdci3e5dus73e59sbg-a.oregon-postgres.render.com/kinbech_database"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
