# Aplikasi Persetujuan Konten Media Sosial

Alur kerja: **Humas mengajukan link konten → Atasan review & approve/tolak →
Humas menandai sudah upload → Atasan bisa pantau semua statusnya.**

## Fitur

- Login dengan password ter-hash (bcrypt), bukan plaintext.
- 3 role: **humas**, **atasan**, **admin**.
- Humas: input link konten, lihat status approval, tandai "sudah diupload"
  (tombol ini baru muncul setelah disetujui atasan).
- Atasan: review konten yang menunggu, approve/tolak + catatan, lihat riwayat
  semua konten & status upload.
- Admin: kelola user (buat akun humas/atasan baru, nonaktifkan user).
- Audit trail (`log_aktivitas`): siapa melakukan apa dan kapan, untuk jejak
  akuntabilitas — penting kalau dipakai serius/formal.
- Rate limiting sederhana saat login gagal berulang kali.
- Database lewat SQLAlchemy: jalan di SQLite untuk development, tinggal ganti
  `DATABASE_URL` ke PostgreSQL untuk production (tanpa ubah kode).

## Instalasi (Development / Lokal)

```bash
pip install -r requirements.txt

cp .env.example .env
# lalu isi ADMIN_USERNAME, ADMIN_PASSWORD, ADMIN_NAMA di .env

python init_db.py       # membuat tabel + akun admin pertama
streamlit run app.py
```

Login sebagai admin, lalu buat akun **humas** dan **atasan** dari menu
"⚙️ Kelola User".

## Menyiapkan Database yang Aman untuk Production

SQLite (default) itu **hanya cocok untuk development/testing**, karena:
- Data disimpan sebagai 1 file lokal — kalau di-deploy ke platform seperti
  Streamlit Community Cloud, file ini bisa hilang tiap kali app di-restart.
- Tidak dirancang untuk banyak user yang menulis data bersamaan.

Untuk pemakaian serius, gunakan **PostgreSQL** terkelola (managed), misalnya:
- [Supabase](https://supabase.com) (ada tier gratis)
- [Neon](https://neon.tech) (ada tier gratis)
- [Railway](https://railway.app)
- Atau PostgreSQL di server institusi/kampus/perusahaan sendiri

Langkah:
1. Buat database PostgreSQL di penyedia pilihan, catat *connection string*-nya.
2. Install driver: `pip install psycopg2-binary` (sudah ada contohnya di
   `requirements.txt`, tinggal uncomment).
3. Isi `DATABASE_URL` di `.env`, contoh:
   ```
   DATABASE_URL=postgresql+psycopg2://USER:PASSWORD@HOST:5432/NAMA_DB?sslmode=require
   ```
4. Jalankan lagi `python init_db.py` untuk membuat tabel di database baru.

**Jangan pernah commit file `.env` ke Git** — file ini berisi password.
`.env.example` sudah disediakan sebagai template tanpa data sensitif.

## Checklist Keamanan Sebelum Dipakai Serius

- [ ] Ganti `ADMIN_PASSWORD` default sebelum deploy, lalu ganti lagi lewat
      aplikasi setelah login pertama (fitur ganti password bisa ditambahkan
      belakangan jika perlu).
- [ ] Gunakan PostgreSQL (bukan SQLite) untuk data yang harus persisten.
- [ ] Pastikan koneksi database pakai SSL (`sslmode=require` di connection
      string, biasanya sudah default di penyedia managed).
- [ ] Deploy di platform yang mendukung HTTPS (Streamlit Community Cloud
      otomatis HTTPS).
- [ ] Simpan `.env` / secrets di secret manager platform deploy, jangan di
      dalam kode.
- [ ] Backup database secara berkala (kebanyakan penyedia managed Postgres
      punya fitur backup otomatis).

## Struktur File

```
app.py          -> Aplikasi utama (semua halaman & routing)
models.py       -> Struktur tabel database (User, Konten, LogAktivitas)
db.py           -> Koneksi & session database
auth.py         -> Hashing password, login, rate limiting
init_db.py      -> Script setup awal (buat tabel + akun admin)
requirements.txt-> Daftar dependency
.env.example    -> Template konfigurasi (salin jadi .env)
```

## Deploy ke Streamlit Community Cloud (gratis)

1. Push project ini ke repository GitHub (pastikan `.env` ada di `.gitignore`,
   **jangan** ikut ter-push).
2. Buka [share.streamlit.io](https://share.streamlit.io), hubungkan repo.
3. Di menu **App settings → Secrets**, isi `DATABASE_URL` dan variabel
   lain dari `.env.example` (format TOML).
4. Deploy. Jalankan `init_db.py` sekali (bisa lewat halaman Streamlit dengan
   menambah tombol admin, atau jalankan manual dari environment yang sama
   dengan akses ke database production).
