import streamlit as st
import pandas as pd
from datetime import datetime
from sqlalchemy import select, desc

from db import init_db, get_session
from models import User, Konten, LogAktivitas, RoleEnum, StatusApprovalEnum, StatusUploadEnum
import auth

st.set_page_config(page_title="Persetujuan Konten Medsos", page_icon="📋", layout="wide")

# Pastikan tabel sudah ada setiap kali app dijalankan (idempotent, aman diulang).
init_db()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def catat_log(session, konten_id: int, user_id: int, aksi: str):
    session.add(LogAktivitas(konten_id=konten_id, user_id=user_id, aksi=aksi))


def badge_approval(status: StatusApprovalEnum) -> str:
    warna = {
        StatusApprovalEnum.menunggu: "🟡 Menunggu Review",
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
    st.title("📋 Aplikasi Persetujuan Konten Media Sosial")
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
                st.session_state.user_id = user.id
                st.session_state.username = user.username
                st.session_state.nama_lengkap = user.nama_lengkap
                st.session_state.role = user.role.value
                st.rerun()
        finally:
            session.close()


# ---------------------------------------------------------------------------
# Halaman: Dashboard Humas
# ---------------------------------------------------------------------------

def halaman_humas():
    auth.role_required(RoleEnum.humas)
    st.title("📤 Dashboard Humas")

    session = get_session()
    try:
        with st.expander("➕ Tambah Konten Baru", expanded=False):
            with st.form("form_tambah_konten", clear_on_submit=True):
                link = st.text_input("Link konten (URL)")
                platform = st.selectbox(
                    "Platform", ["Instagram", "TikTok", "Facebook", "X (Twitter)", "YouTube", "Lainnya"]
                )
                keterangan = st.text_area("Keterangan (opsional)")
                submit = st.form_submit_button("Simpan & Kirim untuk Review")

                if submit:
                    if not link.strip():
                        st.error("Link konten wajib diisi.")
                    else:
                        konten = Konten(
                            link=link.strip(),
                            platform=platform,
                            keterangan=keterangan.strip() or None,
                            humas_id=st.session_state.user_id,
                        )
                        session.add(konten)
                        session.flush()
                        catat_log(session, konten.id, st.session_state.user_id, "Membuat konten & mengirim untuk review")
                        session.commit()
                        st.success("Konten berhasil dikirim untuk direview atasan.")
                        st.rerun()

        st.subheader("Daftar Konten Saya")

        filter_status = st.selectbox(
            "Filter status persetujuan", ["Semua", "Menunggu", "Disetujui", "Ditolak"], key="filter_humas"
        )

        query = select(Konten).where(Konten.humas_id == st.session_state.user_id).order_by(desc(Konten.tanggal_input))
        daftar = session.execute(query).scalars().all()

        if filter_status != "Semua":
            mapping = {
                "Menunggu": StatusApprovalEnum.menunggu,
                "Disetujui": StatusApprovalEnum.disetujui,
                "Ditolak": StatusApprovalEnum.ditolak,
            }
            daftar = [k for k in daftar if k.status_approval == mapping[filter_status]]

        if not daftar:
            st.info("Belum ada konten.")
            return

        for k in daftar:
            with st.container(border=True):
                col1, col2 = st.columns([4, 2])
                with col1:
                    st.markdown(f"**[{k.platform or 'Link'}]({k.link})**")
                    st.caption(k.link)
                    if k.keterangan:
                        st.write(k.keterangan)
                    st.caption(f"Dikirim: {k.tanggal_input.strftime('%d %b %Y %H:%M')}")
                with col2:
                    st.write(badge_approval(k.status_approval))
                    st.write(badge_upload(k.status_upload))
                    if k.catatan_atasan:
                        st.warning(f"Catatan atasan: {k.catatan_atasan}")

                    if k.status_approval == StatusApprovalEnum.disetujui and k.status_upload == StatusUploadEnum.belum:
                        if st.button("✅ Tandai Sudah Diupload", key=f"upload_{k.id}", use_container_width=True):
                            k.status_upload = StatusUploadEnum.sudah
                            k.tanggal_upload = datetime.utcnow()
                            catat_log(session, k.id, st.session_state.user_id, "Menandai konten sudah diupload")
                            session.commit()
                            st.rerun()
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Halaman: Dashboard Atasan
# ---------------------------------------------------------------------------

def halaman_atasan():
    auth.role_required(RoleEnum.atasan)
    st.title("✅ Dashboard Atasan — Review Konten")

    session = get_session()
    try:
        tab_menunggu, tab_semua = st.tabs(["Menunggu Review", "Riwayat Semua Konten"])

        with tab_menunggu:
            daftar = session.execute(
                select(Konten)
                .where(Konten.status_approval == StatusApprovalEnum.menunggu)
                .order_by(Konten.tanggal_input)
            ).scalars().all()

            if not daftar:
                st.success("Tidak ada konten yang menunggu review. 🎉")

            for k in daftar:
                with st.container(border=True):
                    col1, col2 = st.columns([4, 2])
                    with col1:
                        st.markdown(f"**[{k.platform or 'Link'}]({k.link})**")
                        st.caption(k.link)
                        if k.keterangan:
                            st.write(k.keterangan)
                        st.caption(
                            f"Diajukan oleh: {k.dibuat_oleh.nama_lengkap} · "
                            f"{k.tanggal_input.strftime('%d %b %Y %H:%M')}"
                        )
                    with col2:
                        catatan = st.text_area("Catatan (opsional)", key=f"catatan_{k.id}", height=80)
                        c1, c2 = st.columns(2)
                        with c1:
                            if st.button("✅ Setujui", key=f"setuju_{k.id}", use_container_width=True):
                                k.status_approval = StatusApprovalEnum.disetujui
                                k.catatan_atasan = catatan.strip() or None
                                k.disetujui_oleh_id = st.session_state.user_id
                                k.tanggal_approval = datetime.utcnow()
                                catat_log(session, k.id, st.session_state.user_id, "Menyetujui konten")
                                session.commit()
                                st.rerun()
                        with c2:
                            if st.button("❌ Tolak", key=f"tolak_{k.id}", use_container_width=True):
                                k.status_approval = StatusApprovalEnum.ditolak
                                k.catatan_atasan = catatan.strip() or None
                                k.disetujui_oleh_id = st.session_state.user_id
                                k.tanggal_approval = datetime.utcnow()
                                catat_log(session, k.id, st.session_state.user_id, "Menolak konten")
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
                        "Link": k.link,
                        "Platform": k.platform,
                        "Diajukan Oleh": k.dibuat_oleh.nama_lengkap,
                        "Status Approval": badge_approval(k.status_approval),
                        "Status Upload": badge_upload(k.status_upload),
                        "Tanggal Input": k.tanggal_input.strftime("%d %b %Y %H:%M"),
                        "Tanggal Upload": k.tanggal_upload.strftime("%d %b %Y %H:%M") if k.tanggal_upload else "-",
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
                new_role = st.selectbox("Role", ["humas", "atasan", "admin"])
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
                            u = User(
                                username=new_username.strip(),
                                password_hash=auth.hash_password(new_password),
                                nama_lengkap=new_nama.strip() or new_username.strip(),
                                role=RoleEnum(new_role),
                                aktif=1,
                            )
                            session.add(u)
                            session.commit()
                            st.success(f"User '{u.username}' berhasil dibuat.")
                            st.rerun()

        st.subheader("Daftar User")
        users = session.execute(select(User).order_by(User.id)).scalars().all()
        for u in users:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3, 2, 2])
                col1.write(f"**{u.nama_lengkap}** (@{u.username})")
                col2.write(f"Role: `{u.role.value}` · {'🟢 Aktif' if u.aktif else '🔴 Nonaktif'}")
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
        st.caption(f"Role: {st.session_state.role}")
        if st.button("Logout", use_container_width=True):
            auth.logout()
            st.rerun()

    role = st.session_state.role
    if role == RoleEnum.humas.value:
        halaman_humas()
    elif role == RoleEnum.atasan.value:
        halaman_atasan()
    elif role == RoleEnum.admin.value:
        tab1, tab2 = st.tabs(["⚙️ Kelola User", "📊 Lihat Semua Konten"])
        with tab1:
            halaman_admin()
        with tab2:
            halaman_atasan_readonly = None  # placeholder agar admin bisa pantau juga
            session = get_session()
            try:
                daftar_semua = session.execute(
                    select(Konten).order_by(desc(Konten.tanggal_input))
                ).scalars().all()
                if not daftar_semua:
                    st.info("Belum ada data.")
                else:
                    rows = [{
                        "Link": k.link,
                        "Diajukan Oleh": k.dibuat_oleh.nama_lengkap,
                        "Status Approval": badge_approval(k.status_approval),
                        "Status Upload": badge_upload(k.status_upload),
                        "Tanggal Input": k.tanggal_input.strftime("%d %b %Y %H:%M"),
                    } for k in daftar_semua]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            finally:
                session.close()


if __name__ == "__main__":
    main()
