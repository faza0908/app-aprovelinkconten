"""
Definisi struktur tabel database menggunakan SQLAlchemy ORM.
Dengan ORM ini, aplikasi bisa jalan di SQLite (development) maupun
PostgreSQL/MySQL (production) tanpa mengubah kode sama sekali.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey, Enum
)
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


class RoleEnum(str, enum.Enum):
    humas = "humas"
    atasan_utu = "atasan_utu"       # Bagian UTU
    atasan_balai = "atasan_balai"   # Bagian Balai (mencakup banyak SATKER/SNVT,
                                     # tapi tetap satu kategori user)
    admin = "admin"


ROLE_LABELS = {
    RoleEnum.humas: "Humas",
    RoleEnum.atasan_utu: "Bagian UTU",
    RoleEnum.atasan_balai: "Bagian Balai",
    RoleEnum.admin: "Admin",
}

# Daftar unit/satker di bawah Bagian Balai. Ini HANYA label informasi
# (menunjukkan konten itu terkait unit yang mana), BUKAN penentu siapa yang
# me-review -- semua user dengan role atasan_balai tetap satu kategori yang
# sama dan bisa melihat/approve semua konten, apa pun unit yang dipilih.
DAFTAR_UNIT_BALAI = [
    "SATKER BBWS",
    "SNVT Pelaksanaan Jaringan Sumber Air",
    "SNVT Pelaksanaan Jaringan Pemanfaatan Air",
    "SATKER Operasi dan Pemeliharaan SDA",
    "SNVT Pembangunan Bendungan I",
    "SNVT Pembangunan Bendungan II",
    "SNVT Air Tanah dan Air Baku",
]


class StatusApprovalEnum(str, enum.Enum):
    menunggu = "menunggu"
    disetujui = "disetujui"
    ditolak = "ditolak"


class StatusUploadEnum(str, enum.Enum):
    belum = "belum"
    sudah = "sudah"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    nama_lengkap = Column(String(150), nullable=False)
    role = Column(Enum(RoleEnum), nullable=False)
    aktif = Column(Integer, default=1)  # 1 = aktif, 0 = nonaktif (soft delete)
    dibuat_pada = Column(DateTime, default=datetime.utcnow)

    konten_dibuat = relationship(
        "Konten", back_populates="dibuat_oleh",
        foreign_keys="Konten.humas_id"
    )


class Konten(Base):
    """
    Setiap konten butuh persetujuan dari DUA pihak secara independen:
    Bagian UTU dan Bagian Balai. Karena itu status approval disimpan sebagai
    dua pasang kolom terpisah (utu & balai), bukan satu status gabungan.
    """
    __tablename__ = "konten"

    id = Column(Integer, primary_key=True)
    link = Column(String(1000), nullable=False)
    unit_balai = Column(String(200), nullable=True)  # pilihan dari DAFTAR_UNIT_BALAI
    caption = Column(Text, nullable=True)

    humas_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    dibuat_oleh = relationship(
        "User", back_populates="konten_dibuat", foreign_keys=[humas_id]
    )

    # --- Persetujuan Bagian UTU ---
    status_approval_utu = Column(
        Enum(StatusApprovalEnum), default=StatusApprovalEnum.menunggu, nullable=False
    )
    catatan_utu = Column(Text, nullable=True)
    disetujui_utu_oleh_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    disetujui_utu_oleh = relationship("User", foreign_keys=[disetujui_utu_oleh_id])
    tanggal_approval_utu = Column(DateTime, nullable=True)

    # --- Persetujuan Bagian Balai ---
    status_approval_balai = Column(
        Enum(StatusApprovalEnum), default=StatusApprovalEnum.menunggu, nullable=False
    )
    catatan_balai = Column(Text, nullable=True)
    disetujui_balai_oleh_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    disetujui_balai_oleh = relationship("User", foreign_keys=[disetujui_balai_oleh_id])
    tanggal_approval_balai = Column(DateTime, nullable=True)

    status_upload = Column(
        Enum(StatusUploadEnum), default=StatusUploadEnum.belum, nullable=False
    )
    tanggal_upload = Column(DateTime, nullable=True)

    tanggal_input = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Riwayat perubahan status disimpan sebagai log terpisah (audit trail)
    log = relationship("LogAktivitas", back_populates="konten", cascade="all, delete-orphan")

    def disetujui_penuh(self) -> bool:
        """True hanya jika KEDUA pihak (UTU dan Balai) sudah menyetujui."""
        return (
            self.status_approval_utu == StatusApprovalEnum.disetujui
            and self.status_approval_balai == StatusApprovalEnum.disetujui
        )

    def ada_penolakan(self) -> bool:
        return (
            self.status_approval_utu == StatusApprovalEnum.ditolak
            or self.status_approval_balai == StatusApprovalEnum.ditolak
        )


class LogAktivitas(Base):
    """Audit trail: mencatat siapa melakukan apa dan kapan, untuk akuntabilitas."""
    __tablename__ = "log_aktivitas"

    id = Column(Integer, primary_key=True)
    konten_id = Column(Integer, ForeignKey("konten.id"), nullable=False)
    konten = relationship("Konten", back_populates="log")

    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user = relationship("User")

    aksi = Column(String(200), nullable=False)  # contoh: "Membuat konten", "Menyetujui", dst
    waktu = Column(DateTime, default=datetime.utcnow)
