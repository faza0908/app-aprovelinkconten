import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import select, desc
from streamlit_cookies_controller import CookieController

from db import init_db, get_session
from models import (
    User, Konten, LogAktivitas,
    RoleEnum, ROLE_LABELS, DAFTAR_UNIT_BALAI,
    StatusApprovalEnum, StatusUploadEnum,
)
import auth

st.set_page_config(page_title="Persetujuan Konten Medsos", page_icon="images.png", layout="wide")


def inject_custom_theme():
    """
    Styling tambahan di luar yang bisa diatur lewat .streamlit/config.toml,
    supaya tampilan makin dekat dengan warna referensi:
    - Sidebar biru tua dengan teks putih (biar tetap kebaca)
    - Tombol utama warna kuning emas (aksen), teks gelap
    - Garis aksen kuning emas tipis di bawah judul halaman
    """
    st.markdown(
        """
        <style>
        /* Sidebar biru tua, teks putih supaya kontras */
        [data-testid="stSidebar"] {
            background-color: #0B6E9E;
        }
        [data-testid="stSidebar"] * {
            color: #FFFFFF !important;
        }

        /* Tombol utama: kuning emas dengan teks gelap */
        div.stButton > button {
            background-color: #F5B301;
            color: #132A3A;
            border: none;
            font-weight: 600;
        }
        div.stButton > button:hover {
            background-color: #d99e10;
            color: #FFFFFF;
        }
        [data-testid="stSidebar"] div.stButton > button {
            background-color: #F5B301;
            color: #132A3A;
        }

        /* Garis aksen kuning emas tipis di bawah judul halaman */
        h1 {
            border-bottom: 4px solid #0B6E9E;
            padding-bottom: 0.4rem;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )


inject_custom_theme()

# Pastikan tabel sudah ada setiap kali app dijalankan (idempotent, aman diulang).
init_db()

# Cookie controller: dipakai supaya status login tetap tersimpan walau
# halaman di-refresh (F5), karena st.session_state biasa akan hilang saat itu.
cookies = CookieController()


def _pulihkan_sesi_dari_cookie():
    """Kalau session_state kosong (misal karena baru refresh) tapi ada cookie
    login yang valid, pulihkan status login dari situ tanpa perlu login ulang."""
    if "user_id" in st.session_state:
        return  # sudah login di sesi ini, tidak perlu apa-apa

    token = cookies.get(auth.SESSION_COOKIE_NAME)
    payload = auth.baca_session_token(token) if token else None
    if payload:
        st.session_state.user_id = payload["user_id"]
        st.session_state.username = payload["username"]
        st.session_state.nama_lengkap = payload["nama_lengkap"]
        st.session_state.role = payload["role"]


_pulihkan_sesi_dari_cookie()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def catat_log(session, konten_id: int, user_id: int, aksi: str):
    session.add(LogAktivitas(konten_id=konten_id, user_id=user_id, aksi=aksi))


def badge_approval(status: StatusApprovalEnum) -> str:
    warna = {
        StatusApprovalEnum.menunggu: "🟡 Menunggu",
        StatusApprovalEnum.disetujui: "🟢 Disetujui",
        StatusApprovalEnum.ditolak: "🔴 Ditolak",
    }
    return warna.get(status, str(status))


def badge_upload(status: StatusUploadEnum) -> str:
    return "✅ Sudah Diupload" if status == StatusUploadEnum.sudah else "⏳ Belum Diupload"


# ---------------------------------------------------------------------------
# Halaman: Login
# ---------------------------------------------------------------------------

def halaman_login():
    st.title("Aplikasi Persetujuan Konten Media Sosial")
    st.caption("Silakan login untuk melanjutkan.")

    diblokir, sisa = auth.sedang_diblokir()

    with st.form("form_login"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login", disabled=diblokir, use_container_width=True)

    if diblokir:
        st.error(f"Terlalu banyak percobaan gagal. Coba lagi dalam {sisa} detik.")

    if submit and not diblokir:
        session = get_session()
        try:
            user, error = auth.login(session, username, password)
            if error:
                st.error(error)
            else:
                auth.set_login_state(user)
                # Simpan token ke cookie supaya sesi bertahan walau di-refresh.
                token = auth.buat_session_token(user)
                cookies.set(
                    auth.SESSION_COOKIE_NAME,
                    token,
                    max_age=auth.SESSION_MAX_AGE_DETIK,
                )
                st.rerun()
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Halaman: Dashboard Humas
# ---------------------------------------------------------------------------

def halaman_humas():
    auth.role_required(RoleEnum.humas)
    st.title("📤 Dashboard Konten")

    session = get_session()
    try:
        with st.expander("➕ Tambah Konten Baru", expanded=False):
            with st.form("form_tambah_konten", clear_on_submit=True):
                unit_balai = st.selectbox("Bagian Balai", DAFTAR_UNIT_BALAI)
                link = st.text_input("Link konten (URL)")
                caption = st.text_area("Caption")
                submit = st.form_submit_button("Simpan & Kirim untuk Review")

                if submit:
                    if not link.strip():
                        st.error("Link konten wajib diisi.")
                    else:
                        konten = Konten(
                            link=link.strip(),
                            unit_balai=unit_balai,
                            caption=caption.strip() or None,
                            humas_id=st.session_state.user_id,
                        )
                        session.add(konten)
                        session.flush()
                        catat_log(
                            session, konten.id, st.session_state.user_id,
                            "Membuat konten & mengirim untuk review ke Bagian UTU & Bagian Balai"
                        )
                        session.commit()
                        st.success("Konten berhasil dikirim untuk direview Bagian UTU dan Bagian Balai.")
                        st.rerun()

        st.subheader("Daftar Konten Saya")

        query = select(Konten).where(
            Konten.humas_id == st.session_state.user_id
        ).order_by(desc(Konten.tanggal_input))
        daftar = session.execute(query).scalars().all()

        if not daftar:
            st.info("Belum ada konten.")
            return

        for k in daftar:
            with st.container(border=True):
                col1, col2 = st.columns([4, 3])
                with col1:
                    st.markdown(f"**{k.unit_balai or '-'}**")
                    st.caption(k.link)
                    if k.caption:
                        st.write(k.caption)
                    st.caption(f"Dikirim: {k.tanggal_input.strftime('%d %b %Y %H:%M')}")
                with col2:
                    c1, c2 = st.columns(2)
                    c1.markdown("**Bagian UTU**")
                    c1.write(badge_approval(k.status_approval_utu))
                    if k.catatan_utu:
                        c1.warning(k.catatan_utu)

                    c2.markdown("**Bagian Balai**")
                    c2.write(badge_approval(k.status_approval_balai))
                    if k.catatan_balai:
                        c2.warning(k.catatan_balai)

                    st.write(badge_upload(k.status_upload))

                    if k.disetujui_penuh() and k.status_upload == StatusUploadEnum.belum:
                        if st.button("✅ Tandai Sudah Diupload", key=f"upload_{k.id}", use_container_width=True):
                            k.status_upload = StatusUploadEnum.sudah
                            k.tanggal_upload = datetime.utcnow()
                            catat_log(session, k.id, st.session_state.user_id, "Menandai konten sudah diupload")
                            session.commit()
                            st.rerun()
                    elif not k.disetujui_penuh() and not k.ada_penolakan():
                        st.caption("Menunggu persetujuan dari kedua pihak sebelum bisa ditandai upload.")
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Halaman: Dashboard Atasan (dipakai bersama oleh Bagian UTU & Bagian Balai)
# ---------------------------------------------------------------------------

def halaman_atasan(role: RoleEnum):
    auth.role_required(role)

    if role == RoleEnum.atasan_utu:
        label_pihak = "Bagian UTU"
        kolom_status = "status_approval_utu"
        kolom_catatan = "catatan_utu"
        kolom_oleh = "disetujui_utu_oleh_id"
        kolom_tanggal = "tanggal_approval_utu"
    else:
        label_pihak = "Bagian Balai"
        kolom_status = "status_approval_balai"
        kolom_catatan = "catatan_balai"
        kolom_oleh = "disetujui_balai_oleh_id"
        kolom_tanggal = "tanggal_approval_balai"

    st.title(f"✅ Dashboard {label_pihak} — Review Konten")

    session = get_session()
    try:
        tab_menunggu, tab_semua = st.tabs(["Menunggu Review", "Riwayat Semua Konten"])

        with tab_menunggu:
            daftar = session.execute(
                select(Konten)
                .where(getattr(Konten, kolom_status) == StatusApprovalEnum.menunggu)
                .order_by(Konten.tanggal_input)
            ).scalars().all()

            if not daftar:
                st.success("Tidak ada konten yang menunggu review dari pihak Anda. 🎉")

            for k in daftar:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 2])
                    with col1:
                        st.markdown(f"**{k.unit_balai or '-'}**")
                        st.caption(k.link)
                        if k.caption:
                            st.write(k.caption)
                        st.caption(
                            f"Diajukan oleh: {k.dibuat_oleh.nama_lengkap} · "
                            f"{k.tanggal_input.strftime('%d %b %Y %H:%M')}"
                        )
                        st.caption(
                            f"Status pihak lain — "
                            f"Bagian UTU: {badge_approval(k.status_approval_utu)} · "
                            f"Bagian Balai: {badge_approval(k.status_approval_balai)}"
                        )
                    with col2:
                        catatan = st.text_area("Catatan (opsional)", key=f"catatan_{role.value}_{k.id}", height=80)
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Setujui", key=f"setuju_{role.value}_{k.id}", use_container_width=True):
                                setattr(k, kolom_status, StatusApprovalEnum.disetujui)
                                setattr(k, kolom_catatan, catatan.strip() or None)
                                setattr(k, kolom_oleh, st.session_state.user_id)
                                setattr(k, kolom_tanggal, datetime.utcnow())
                                catat_log(session, k.id, st.session_state.user_id, f"{label_pihak} menyetujui konten")
                                session.commit()
                                st.rerun()
                        with c2:
                            if st.button("❌ Tolak", key=f"tolak_{role.value}_{k.id}", use_container_width=True):
                                setattr(k, kolom_status, StatusApprovalEnum.ditolak)
                                setattr(k, kolom_catatan, catatan.strip() or None)
                                setattr(k, kolom_oleh, st.session_state.user_id)
                                setattr(k, kolom_tanggal, datetime.utcnow())
                                catat_log(session, k.id, st.session_state.user_id, f"{label_pihak} menolak konten")
                                session.commit()
                                st.rerun()

        with tab_semua:
            daftar_semua = session.execute(
                select(Konten).order_by(desc(Konten.tanggal_input))
            ).scalars().all()

            if not daftar_semua:
                st.info("Belum ada data.")
            else:
                rows = []
                for k in daftar_semua:
                    rows.append({
                        "Bagian Balai": k.unit_balai,
                        "Link": k.link,
                        "Diajukan Oleh": k.dibuat_oleh.nama_lengkap,
                        "Status UTU": badge_approval(k.status_approval_utu),
                        "Status Balai": badge_approval(k.status_approval_balai),
                        "Status Upload": badge_upload(k.status_upload),
                        "Tanggal Input": k.tanggal_input.strftime("%d %b %Y %H:%M"),
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Halaman: Admin (kelola user)
# ---------------------------------------------------------------------------

def halaman_admin():
    auth.role_required(RoleEnum.admin)
    st.title("⚙️ Panel Admin — Kelola User")

    session = get_session()
    try:
        with st.expander("➕ Tambah User Baru"):
            with st.form("form_tambah_user", clear_on_submit=True):
                new_username = st.text_input("Username")
                new_nama = st.text_input("Nama Lengkap")
                new_role_label = st.selectbox("Role", list(ROLE_LABELS.values()))
                new_password = st.text_input("Password Awal", type="password")
                submit = st.form_submit_button("Buat User")

                if submit:
                    if not new_username.strip() or not new_password:
                        st.error("Username dan password wajib diisi.")
                    else:
                        existing = session.execute(
                            select(User).where(User.username == new_username.strip())
                        ).scalar_one_or_none()
                        if existing:
                            st.error("Username sudah dipakai.")
                        else:
                            role_terpilih = next(
                                r for r, label in ROLE_LABELS.items() if label == new_role_label
                            )
                            u = User(
                                username=new_username.strip(),
                                password_hash=auth.hash_password(new_password),
                                nama_lengkap=new_nama.strip() or new_username.strip(),
                                role=role_terpilih,
                                aktif=1,
                            )
                            session.add(u)
                            session.commit()
                            st.success(f"User '{u.username}' ({new_role_label}) berhasil dibuat.")
                            st.rerun()

        st.subheader("Daftar User")
        users = session.execute(select(User).order_by(User.id)).scalars().all()
        for u in users:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.write(f"**{u.nama_lengkap}** (@{u.username})")
                label_role = ROLE_LABELS.get(u.role, u.role.value)
                col2.write(f"Role: `{label_role}` · {'🟢 Aktif' if u.aktif else '🔴 Nonaktif'}")
                with col3:
                    if u.id != st.session_state.user_id:
                        label = "Nonaktifkan" if u.aktif else "Aktifkan"
                        if st.button(label, key=f"toggle_{u.id}"):
                            u.aktif = 0 if u.aktif else 1
                            session.commit()
                            st.rerun()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Routing utama
# ---------------------------------------------------------------------------

def main():
    if "user_id" not in st.session_state:
        halaman_login()
        return

    with st.sidebar:
        st.markdown(f"👤 **{st.session_state.nama_lengkap}**")
        label_role = ROLE_LABELS.get(RoleEnum(st.session_state.role), st.session_state.role)
        st.caption(f"Role: {label_role}")
        if st.button("Logout", use_container_width=True):
            auth.logout()
            cookies.remove(auth.SESSION_COOKIE_NAME)
            st.rerun()

    role = st.session_state.role
    if role == RoleEnum.humas.value:
        halaman_humas()
    elif role == RoleEnum.atasan_utu.value:
        halaman_atasan(RoleEnum.atasan_utu)
    elif role == RoleEnum.atasan_balai.value:
        halaman_atasan(RoleEnum.atasan_balai)
    elif role == RoleEnum.admin.value:
        tab1, tab2 = st.tabs(["⚙️ Kelola User", "📊 Lihat Semua Konten"])
        with tab1:
            halaman_admin()
        with tab2:
            session = get_session()
            try:
                daftar_semua = session.execute(
                    select(Konten).order_by(desc(Konten.tanggal_input))
                ).scalars().all()
                if not daftar_semua:
                    st.info("Belum ada data.")
                else:
                    rows = [{
                        "Bagian Balai": k.unit_balai,
                        "Link": k.link,
                        "Diajukan Oleh": k.dibuat_oleh.nama_lengkap,
                        "Status UTU": badge_approval(k.status_approval_utu),
                        "Status Balai": badge_approval(k.status_approval_balai),
                        "Status Upload": badge_upload(k.status_upload),
                        "Tanggal Input": k.tanggal_input.strftime("%d %b %Y %H:%M"),
                    } for k in daftar_semua]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            finally:
                session.close()


if __name__ == "__main__":
    main()
