"""
Jalankan sekali di awal untuk:
1. Membuat semua tabel di database.
2. Membuat akun admin pertama (kredensial diambil dari file .env).

Cara pakai:
    python init_db.py
"""

import os
from dotenv import load_dotenv
from sqlalchemy import select

from db import init_db, get_session
from models import User, RoleEnum
from auth import hash_password

load_dotenv()


def main():
    print("Membuat tabel database (jika belum ada)...")
    init_db()

    session = get_session()
    try:
        admin_username = os.getenv("ADMIN_USERNAME", "admin").strip()
        admin_password = os.getenv("ADMIN_PASSWORD", "").strip()
        admin_nama = os.getenv("ADMIN_NAMA", "Administrator").strip()

        if not admin_password or admin_password == "admin":
            print(
                "\n⚠️  PERINGATAN: ADMIN_PASSWORD di file .env belum diganti dari nilai "
                "default. Silakan ubah dulu di .env sebelum menjalankan script ini di "
                "environment production.\n"
            )

        existing = session.execute(
            select(User).where(User.username == admin_username)
        ).scalar_one_or_none()

        if existing:
            print(f"Akun admin '{admin_username}' sudah ada, tidak dibuat ulang.")
        else:
            admin = User(
                username=admin_username,
                password_hash=hash_password(admin_password or "admin123"),
                nama_lengkap=admin_nama,
                role=RoleEnum.admin,
                aktif=1,
            )
            session.add(admin)
            session.commit()
            print(f"Akun admin '{admin_username}' berhasil dibuat.")
            print("Silakan login lalu segera buat akun humas & atasan dari menu Admin,")
            print("dan pertimbangkan mengganti password admin ini.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
