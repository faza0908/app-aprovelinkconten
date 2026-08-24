"""
Modul autentikasi.

Keamanan yang diterapkan:
- Password TIDAK PERNAH disimpan dalam bentuk plaintext, hanya hash bcrypt.
- Bcrypt otomatis menambahkan salt unik per password, jadi aman dari rainbow-table attack.
- Percobaan login gagal tidak membocorkan apakah username atau password yang salah
  (pesan error digeneralisasi) untuk mencegah user enumeration.
- Sederhana rate-limiting berbasis session untuk memperlambat brute force.
"""

import bcrypt
import os
import time
import streamlit as st
from sqlalchemy import select
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from models import User, RoleEnum

MAX_PERCOBAAN = 5
JEDA_DETIK_SETELAH_GAGAL = 30

# Token login disimpan di cookie browser agar sesi tidak hilang saat halaman
# di-refresh. Token ini ditandatangani (signed) pakai APP_SECRET_KEY, jadi
# tidak bisa dipalsukan oleh user meskipun mereka bisa melihat isi cookie-nya.
SESSION_COOKIE_NAME = "humas_app_session"
SESSION_MAX_AGE_DETIK = 60 * 60 * 24 * 7  # token berlaku 7 hari


def _get_secret_key() -> str:
    secret = os.getenv("APP_SECRET_KEY", "").strip()
    if not secret:
        # Fallback ini hanya untuk development. Untuk production, WAJIB
        # isi APP_SECRET_KEY di .env / Secrets, jika tidak sesi akan
        # otomatis logout tiap kali aplikasi restart.
        secret = "dev-only-insecure-secret-key-ganti-ini"
    return secret


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(_get_secret_key())


def buat_session_token(user: User) -> str:
    """Membuat token berisi identitas user, ditandatangani agar tidak bisa dipalsukan."""
    payload = {
        "user_id": user.id,
        "username": user.username,
        "nama_lengkap": user.nama_lengkap,
        "role": user.role.value,
    }
    return _serializer().dumps(payload)


def baca_session_token(token: str):
    """Mengembalikan payload dict jika token valid & belum kedaluwarsa, None jika tidak."""
    if not token:
        return None
    try:
        return _serializer().loads(token, max_age=SESSION_MAX_AGE_DETIK)
    except (BadSignature, SignatureExpired):
        return None


def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _init_rate_limit_state():
    if "login_gagal_count" not in st.session_state:
        st.session_state.login_gagal_count = 0
    if "login_blokir_sampai" not in st.session_state:
        st.session_state.login_blokir_sampai = 0


def sedang_diblokir() -> tuple[bool, int]:
    _init_rate_limit_state()
    sisa = st.session_state.login_blokir_sampai - time.time()
    if sisa > 0:
        return True, int(sisa)
    return False, 0


def login(session, username: str, password: str):
    """
    Mengembalikan (user, pesan_error).
    Jika berhasil: (User, None). Jika gagal: (None, "pesan error umum").
    """
    _init_rate_limit_state()

    diblokir, sisa = sedang_diblokir()
    if diblokir:
        return None, f"Terlalu banyak percobaan gagal. Coba lagi dalam {sisa} detik."

    username = username.strip()
    user = session.execute(
        select(User).where(User.username == username, User.aktif == 1)
    ).scalar_one_or_none()

    if user is None or not verify_password(password, user.password_hash):
        st.session_state.login_gagal_count += 1
        if st.session_state.login_gagal_count >= MAX_PERCOBAAN:
            st.session_state.login_blokir_sampai = time.time() + JEDA_DETIK_SETELAH_GAGAL
            st.session_state.login_gagal_count = 0
        return None, "Username atau password salah."

    # Login berhasil -> reset counter
    st.session_state.login_gagal_count = 0
    st.session_state.login_blokir_sampai = 0
    return user, None


def login_required():
    """Guard: panggil di awal halaman yang butuh login."""
    if "user_id" not in st.session_state:
        st.warning("Silakan login terlebih dahulu.")
        st.stop()


def role_required(*roles: RoleEnum):
    login_required()
    if st.session_state.get("role") not in [r.value for r in roles]:
        st.error("Anda tidak memiliki akses ke halaman ini.")
        st.stop()


def logout():
    for key in ["user_id", "username", "nama_lengkap", "role"]:
        st.session_state.pop(key, None)


def set_login_state(user: User):
    """Simpan status login ke session_state. Cookie diisi terpisah oleh app.py
    karena butuh akses ke CookieController yang diinisialisasi di sana."""
    st.session_state.user_id = user.id
    st.session_state.username = user.username
    st.session_state.nama_lengkap = user.nama_lengkap
    st.session_state.role = user.role.value
