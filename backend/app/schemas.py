from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import List, Optional, Literal
import datetime
import html
from app.models import DocumentStatus


# Stores
class StoreCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)

    @field_validator("display_name")
    @classmethod
    def sanitize_display_name(cls, v: str) -> str:
        """Sanitize display name to prevent XSS and injection attacks."""
        # HTML escape
        v = html.escape(v.strip())

        # Check for forbidden patterns (script tags, event handlers, etc.)
        forbidden = ["<script", "<iframe", "javascript:", "onerror=", "onload=", "onclick=", "eval("]
        v_lower = v.lower()
        for pattern in forbidden:
            if pattern in v_lower:
                raise ValueError(f"Display name contains forbidden content: {pattern}")

        # Remove non-printable characters
        v = "".join(c for c in v if c.isprintable())

        if not v:
            raise ValueError("Display name cannot be empty after sanitization")

        return v


class StoreOut(BaseModel):
    id: int
    display_name: str
    fs_name: str


class DocumentOut(BaseModel):
    id: int
    store_id: int
    filename: str = Field(max_length=255)
    display_name: Optional[str] = Field(default=None, max_length=255)
    status: DocumentStatus
    size_bytes: int
    created_at: datetime.datetime
    gcs_uri: Optional[str] = Field(default=None, max_length=512)


# Uploads
class UploadResponse(BaseModel):
    op_id: str
    document_id: int
    file_display_name: Optional[str] = Field(default=None, max_length=255)
    estimated_tokens: Optional[int] = None
    estimated_cost_usd: Optional[float] = None


class OpStatus(BaseModel):
    status: DocumentStatus
    error: Optional[str] = None


# Chat
class QueryRequest(BaseModel):
    storeIds: List[int]
    question: str
    metadataFilter: Optional[str] = None
    model: Optional[str] = None
    sessionId: Optional[str] = None


class Citation(BaseModel):
    index: int
    source_type: str
    uri: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    store: Optional[str] = None


class QueryResponse(BaseModel):
    text: str
    inline_text: str
    citations: List[Citation]


# Auth
class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class DevLoginIn(BaseModel):
    email: EmailStr


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=72)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


# Costs
class CostsSummary(BaseModel):
    month: str
    query_cost_usd: float
    indexing_cost_usd: float
    total_usd: float
    prompt_tokens: int
    completion_tokens: int
    index_tokens: int
    monthly_budget_usd: Optional[float] = None
    remaining_budget_usd: Optional[float] = None


# Admin
class AdminUserOut(BaseModel):
    id: int
    email: EmailStr
    is_admin: bool
    is_active: bool
    admin_notes: Optional[str] = None
    monthly_limit_usd: Optional[float] = None
    created_at: datetime.datetime


class AdminUserRoleUpdate(BaseModel):
    is_admin: bool
    admin_notes: Optional[str] = None


class BudgetUpdate(BaseModel):
    monthly_limit_usd: float = Field(ge=0, le=99_999_999.99)


class AdminAuditEntry(BaseModel):
    id: int
    admin_user_id: Optional[int] = None
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    metadata_json: Optional[str] = None
    created_at: datetime.datetime


class AdminSystemSummary(BaseModel):
    users: int
    stores: int
    documents: int


class WatchdogResetResponse(BaseModel):
    reset_count: int


class DeletionAuditEntry(BaseModel):
    store_id: int
    deleted_at: datetime.datetime
    deleted_by: Optional[str] = None


# Settings
class AppSettings(BaseModel):
    app_name: str = Field(default="RAG Assistant", max_length=100)
    app_icon: str = Field(default="sparkles", max_length=50)
    theme_preset: Literal["minimal", "gradient", "classic"] = "minimal"
    primary_color: str = Field(default="#2563EB", max_length=20)
    accent_color: str = Field(default="#6366F1", max_length=20)
    app_favicon: str = Field(default="", max_length=200000)
    welcome_message: str = Field(
        default="Hi! I'm your RAG assistant. Ask me anything about your documents.",
        max_length=255,
    )
    suggested_prompt_1: Optional[str] = Field(
        default="Summarize the key findings from my uploads.",
        max_length=180,
    )
    suggested_prompt_2: Optional[str] = Field(
        default="What are the main risks or open questions?",
        max_length=180,
    )
    suggested_prompt_3: Optional[str] = Field(
        default="Create an outline using the latest documents.",
        max_length=180,
    )


class AppSettingsUpdate(BaseModel):
    app_name: Optional[str] = Field(default=None, max_length=100)
    app_icon: Optional[str] = Field(default=None, max_length=50)
    theme_preset: Optional[Literal["minimal", "gradient", "classic"]] = None
    primary_color: Optional[str] = Field(default=None, max_length=20)
    accent_color: Optional[str] = Field(default=None, max_length=20)
    app_favicon: Optional[str] = Field(default=None, max_length=200000)
    welcome_message: Optional[str] = Field(default=None, max_length=255)
    suggested_prompt_1: Optional[str] = Field(default=None, max_length=180)
    suggested_prompt_2: Optional[str] = Field(default=None, max_length=180)
    suggested_prompt_3: Optional[str] = Field(default=None, max_length=180)
