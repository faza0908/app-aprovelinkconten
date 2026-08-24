"""
Script migrasi untuk database yang SUDAH JALAN di production (misal Supabase),
dari skema lama (1 atasan, 1 status approval) ke skema baru (Bagian UTU +
Bagian Balai, dual approval).

AMAN dijalankan berkali-kali (idempotent) -- kolom yang sudah ada tidak akan
dibuat ulang, dan TIDAK ADA data lama yang dihapus. Kolom-kolom lama
(platform, keterangan, status_approval, dst) dibiarkan apa adanya di database
sebagai arsip, hanya sudah tidak dipakai lagi oleh aplikasi.

Cara pakai:
    python migrate_v2.py
"""

from sqlalchemy import text
from db import engine, init_db

# Pernyataan SQL untuk PostgreSQL. Idempotent lewat "IF NOT EXISTS".
STATEMENTS_POSTGRES = [
    # Tambah nilai baru ke enum role (harus dieksekusi terpisah, tidak boleh
    # dipakai di transaksi yang sama saat query lain memakainya).
    "ALTER TYPE roleenum ADD VALUE IF NOT EXISTS 'atasan_utu';",
    "ALTER TYPE roleenum ADD VALUE IF NOT EXISTS 'atasan_balai';",

    # Kolom baru di tabel konten
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS unit_balai VARCHAR(200);",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS caption TEXT;",

    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS status_approval_utu statusapprovalenum "
    "DEFAULT 'menunggu' NOT NULL;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS catatan_utu TEXT;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS disetujui_utu_oleh_id INTEGER "
    "REFERENCES users(id);",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS tanggal_approval_utu TIMESTAMP;",

    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS status_approval_balai statusapprovalenum "
    "DEFAULT 'menunggu' NOT NULL;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS catatan_balai TEXT;",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS disetujui_balai_oleh_id INTEGER "
    "REFERENCES users(id);",
    "ALTER TABLE konten ADD COLUMN IF NOT EXISTS tanggal_approval_balai TIMESTAMP;",
]

# Migrasi data lama (kalau tabel konten sebelumnya sudah punya kolom
# status_approval / platform dari skema lama) ke kolom baru, best-effort.
STATEMENT_MIGRASI_DATA = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'konten' AND column_name = 'status_approval'
    ) THEN
        UPDATE konten
        SET status_approval_utu = status_approval::text::statusapprovalenum,
            status_approval_balai = status_approval::text::statusapprovalenum
        WHERE status_approval_utu = 'menunggu' AND status_approval_balai = 'menunggu';
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'konten' AND column_name = 'platform'
    ) THEN
        UPDATE konten SET unit_balai = platform WHERE unit_balai IS NULL;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'konten' AND column_name = 'keterangan'
    ) THEN
        UPDATE konten SET caption = keterangan WHERE caption IS NULL;
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
            "skema baru dari awal (data lokal boleh hilang, tidak masalah).\n"
        )
        return

    print("Menjalankan migrasi skema ke PostgreSQL (Supabase)...")
    # AUTOCOMMIT diperlukan khusus untuk ALTER TYPE ... ADD VALUE di Postgres.
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        for stmt in STATEMENTS_POSTGRES:
            print(f"  > {stmt}")
            conn.execute(text(stmt))

        print("  > Memindahkan data lama ke kolom baru (best-effort)...")
        conn.execute(text(STATEMENT_MIGRASI_DATA))

    print("\nMigrasi selesai. Kolom lama (platform, keterangan, status_approval, dst)")
    print("dibiarkan apa adanya di database sebagai arsip, sudah tidak dipakai kode.")
    print("\nJangan lupa: buat/update akun user dengan role 'atasan_utu' dan")
    print("'atasan_balai' lewat menu Admin > Kelola User di aplikasi.")


if __name__ == "__main__":
    main()
