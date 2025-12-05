# SPDX-License-Identifier: Apache-2.0

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, JSON, Numeric, String, Text, event
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
import enum
import datetime
import uuid
from .db import Base


class DocumentStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    ERROR = "ERROR"


DocumentStatusEnumType = Enum(
    DocumentStatus,
    name="documentstatus",
    native_enum=True,
)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="1")
    email_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="0")
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    stores = relationship("Store", back_populates="user", foreign_keys="Store.user_id")
    query_logs = relationship("QueryLog", back_populates="user")
    budget = relationship("Budget", back_populates="user", uselist=False)
    admin_logs = relationship("AdminAuditLog", back_populates="admin_user")


class SoftDeleteMixin:
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def soft_delete(self, *, user_id: int | None = None) -> datetime.datetime:
        ts = datetime.datetime.now(datetime.timezone.utc)
        self.deleted_at = ts
        if hasattr(self, "deleted_by"):
            setattr(self, "deleted_by", user_id)
        return ts

    def restore(self) -> None:
        self.deleted_at = None
        if hasattr(self, "deleted_by"):
            setattr(self, "deleted_by", None)


class Store(SoftDeleteMixin, Base):
    __tablename__ = "stores"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    fs_name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)  # Unique constraint added
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="stores", foreign_keys=[user_id])
    documents = relationship("Document", back_populates="store")
    query_logs = relationship("QueryLog", back_populates="store")
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])


class Document(SoftDeleteMixin, Base):
    __tablename__ = "documents"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    store_id: Mapped[int] = mapped_column(ForeignKey("stores.id"), nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        DocumentStatusEnumType,
        nullable=False,
        default=DocumentStatus.PENDING,
        server_default=DocumentStatus.PENDING.value,
    )
    status_updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    op_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    gcs_uri: Mapped[str | None] = mapped_column(String(512), nullable=True)
    gemini_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    deleted_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    store = relationship("Store", back_populates="documents")
    deleted_by_user = relationship("User", foreign_keys=[deleted_by])

    def set_status(self, status: DocumentStatus) -> None:
        self.status = status
        self.status_updated_at = datetime.datetime.now(datetime.timezone.utc)

    def touch_status(self) -> None:
        """Bump status_updated_at without changing the current status."""
        self.status_updated_at = datetime.datetime.now(datetime.timezone.utc)


@event.listens_for(Document, "before_insert", propagate=True)
def _init_status_timestamp(mapper, connection, target: Document) -> None:
    """
    Ensure status_updated_at tracks the initial status timestamp, falling back to created_at.

    This keeps watchdog logic aligned with initial creation times when status is preset.
    """
    if target.status_updated_at is None:
        target.status_updated_at = target.created_at or datetime.datetime.now(datetime.timezone.utc)


class QueryLog(Base):
    __tablename__ = "query_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    model: Mapped[str | None] = mapped_column(String(100))
    project_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tags: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="query_logs")
    store = relationship("Store", back_populates="query_logs")


class Budget(Base):
    __tablename__ = "budgets"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), primary_key=True)
    monthly_limit_usd: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="budget")


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin_user = relationship("User", back_populates="admin_logs")


class ChatHistory(Base):
    __tablename__ = "chat_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    session_id: Mapped[str] = mapped_column(String(64), ForeignKey("chat_sessions.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    session = relationship("ChatSession", back_populates="messages")


class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id"), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    messages = relationship("ChatHistory", back_populates="session", passive_deletes=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
