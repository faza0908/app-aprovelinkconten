"""
Pengelolaan koneksi database.

- Jika environment variable DATABASE_URL diisi -> pakai itu (misal PostgreSQL).
- Jika kosong -> otomatis fallback ke SQLite lokal (file humas_app.db),
  cocok untuk development/testing.
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv
from models import Base

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

if not DATABASE_URL:
    # Fallback aman untuk lokal/dev. File disimpan di folder yang sama.
    DATABASE_URL = "sqlite:///humas_app.db"

connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, connect_args=connect_args, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db():
    """Membuat semua tabel jika belum ada. Aman dipanggil berkali-kali."""
    Base.metadata.create_all(bind=engine)


def get_session():
    """Mengembalikan session database baru. Wajib ditutup (session.close()) setelah dipakai."""
    return SessionLocal()
