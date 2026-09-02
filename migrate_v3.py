"""
Script migrasi untuk database production (Supabase) dari skema 2-pihak
(Bagian UTU + Bagian Balai) ke skema 3-pihak (Katim Kompu + Bagian UTU +
Bidang/Satker), plus mengganti makna status "ditolak" jadi "revisi".

AMAN dijalankan berkali-kali (idempotent). TIDAK ADA data lama yang dihapus.

Cara pakai:
    python migrate_v3.py
"""

from sqlalchemy import text
from db import engine, init_db

STATEMENTS_POSTGRES = [
    # Role baru: Katim Kompu
    "ALTER TYPE roleenum ADD VALUE IF NOT EXISTS 'atasan_kompu';",

    # Kolom baru untuk persetujuan Katim Kompu
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS status_approval_kompu statusapprovalenum "
    "DEFAULT 'menunggu' NOT NULL;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS catatan_kompu TEXT;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS disetujui_kompu_oleh_id INTEGER "
    "REFERENCES users(id);",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS tanggal_approval_kompu TIMESTAMP;",
]

# Ganti nama nilai enum 'ditolak' -> 'revisi' (kalau masih ada / belum pernah
# di-rename sebelumnya). Dibungkus DO block + EXECUTE supaya idempotent,
# karena ALTER TYPE ... RENAME VALUE tidak punya opsi IF EXISTS bawaan.
STATEMENT_RENAME_ENUM = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON e.enumtypid = t.oid
        WHERE t.typname = 'statusapprovalenum' AND e.enumlabel = 'ditolak'
    ) THEN
        EXECUTE 'ALTER TYPE statusapprovalenum RENAME VALUE ''ditolak'' TO ''revisi''';
    END IF;
END $$;
"""


def main():
    print("Membuat tabel baru jika belum ada (aman diulang)...")
    init_db()

    is_postgres = engine.url.get_backend_name().startswith("postgresql")

    if not is_postgres:
        print(
            "\nDatabase ini bukan PostgreSQL (kemungkinan SQLite lokal).\n"
            "Untuk development lokal, cara paling gampang: hapus saja file "
            "*.db lama lalu jalankan 'python init_db.py' lagi untuk membuat "
            "skema baru dari awal.\n"
        )
        return

    print("Menjalankan migrasi skema ke PostgreSQL (Supabase)...")
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        print("  > Rename enum 'ditolak' -> 'revisi' (kalau perlu)...")
        conn.execute(text(STATEMENT_RENAME_ENUM))

        for stmt in STATEMENTS_POSTGRES:
            print(f"  > {stmt}")
            conn.execute(text(stmt))

    print("\nMigrasi selesai. Kolom & role baru sudah tersedia.")
    print("Jangan lupa: buat/update akun user dengan role 'atasan_kompu' (Katim Kompu)")
    print("lewat menu Admin > Kelola User di aplikasi.")


if __name__ == "__main__":
    main()