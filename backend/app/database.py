import os
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


load_dotenv(Path(__file__).resolve().parents[1] / '.env')
DATABASE_URL = os.getenv('DATABASE_URL', '')
if DATABASE_URL:
    if not DATABASE_URL.startswith(('postgresql://', 'postgresql+psycopg://')):
        raise RuntimeError('DATABASE_URL must point to PostgreSQL; SQLite is not supported.')
else:
    password = os.getenv('POSTGRES_PASSWORD')
    if not password:
        raise RuntimeError('Set POSTGRES_PASSWORD or DATABASE_URL in backend/.env.')
    DATABASE_URL = URL.create(
        drivername='postgresql+psycopg',
        username=os.getenv('POSTGRES_USER', 'postgres'),
        password=password,
        host=os.getenv('POSTGRES_HOST', 'localhost'),
        port=int(os.getenv('POSTGRES_PORT', '5432')),
        database=os.getenv('POSTGRES_DB', 'obalai'),
    ).render_as_string(hide_password=False)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
