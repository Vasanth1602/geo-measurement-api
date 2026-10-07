"""
SQLAlchemy ORM models for uploaded files and their measured features.
Compatible with Python 3.9+ using Optional[...] typing.
"""
import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PROCESSING")
    feature_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime, default=datetime.datetime.utcnow, nullable=False
    )

    features: Mapped[List["FeatureRecord"]] = relationship(
        "FeatureRecord",
        back_populates="file",
        cascade="all, delete-orphan",
        order_by="FeatureRecord.index",
    )


class FeatureRecord(Base):
    __tablename__ = "feature_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    file_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("uploaded_files.id", ondelete="CASCADE"), index=True, nullable=False
    )
    index: Mapped[int] = mapped_column(Integer, nullable=False)
    geometry_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    geometry_geojson: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    properties: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    supported: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    area_sq_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    length_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    measurement_crs: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    file: Mapped["UploadedFile"] = relationship("UploadedFile", back_populates="features")
