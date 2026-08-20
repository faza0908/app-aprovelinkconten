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
    atasan = "atasan"
    admin = "admin"


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
    __tablename__ = "konten"

    id = Column(Integer, primary_key=True)
    link = Column(String(1000), nullable=False)
    platform = Column(String(50), nullable=True)  # Instagram, TikTok, dll (opsional)
    keterangan = Column(Text, nullable=True)

    humas_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    dibuat_oleh = relationship(
        "User", back_populates="konten_dibuat", foreign_keys=[humas_id]
    )

    status_approval = Column(
        Enum(StatusApprovalEnum), default=StatusApprovalEnum.menunggu, nullable=False
    )
    catatan_atasan = Column(Text, nullable=True)
    disetujui_oleh_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    disetujui_oleh = relationship("User", foreign_keys=[disetujui_oleh_id])
    tanggal_approval = Column(DateTime, nullable=True)

    status_upload = Column(
        Enum(StatusUploadEnum), default=StatusUploadEnum.belum, nullable=False
    )
    tanggal_upload = Column(DateTime, nullable=True)

    tanggal_input = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Riwayat perubahan status disimpan sebagai log terpisah (audit trail)
    log = relationship("LogAktivitas", back_populates="konten", cascade="all, delete-orphan")


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
