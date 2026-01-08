from __future__ import annotations

import ipaddress
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import AnyHttpUrl, Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine.url import make_url

from app.file_types import (
    ALL_SUPPORTED_UPLOAD_MIMES,
    GEMINI_SUPPORTED_MIMES,
    OFFICE_UPLOAD_MIMES,
    SAFE_DEFAULT_UPLOAD_MIMES,
)


DEV_DEFAULT_JWT_SECRET = "dev_secret_DO_NOT_USE_IN_PRODUCTION_generate_real_secret_with_secrets_module"
DEFAULT_DB_PASSWORDS = {
    "localdev_password_change_in_production",
    "postgres",
    "password",
    "changeme_demo_password",
    "",
}
SECRET_FILE_KEYS = ("JWT_SECRET", "GEMINI_API_KEY", "DATABASE_URL", "REDIS_URL")
DEFAULT_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # Reasoning / thinking tiers
    "gemini-3.0-pro-thinking": {"input_price": 2.0, "output_price": 12.0, "index_price": 0.0015},
    "gemini-3-pro-preview": {"input_price": 2.0, "output_price": 12.0, "index_price": 0.0015},
    # Performance tiers
    "gemini-2.5-pro": {"input_price": 1.25, "output_price": 10.0, "index_price": 0.0015},
    "gemini-2.0-pro": {"input_price": 1.0, "output_price": 5.0, "index_price": 0.0015},
    "gemini-1.5-pro": {"input_price": 1.25, "output_price": 5.0, "index_price": 0.0015},
    # Efficiency tiers
    "gemini-2.5-flash": {"input_price": 0.30, "output_price": 2.50, "audio_input_price": 1.0, "index_price": 0.0015},
    "gemini-2.5-flash-lite": {
        "input_price": 0.10,
        "output_price": 0.40,
        "audio_input_price": 0.30,
        "index_price": 0.0015,
    },
    "gemini-2.0-flash": {"input_price": 0.10, "output_price": 0.40, "audio_input_price": 0.70, "index_price": 0.0015},
    "gemini-1.5-flash": {"input_price": 0.075, "output_price": 0.30, "index_price": 0.0015},
    # Fallback default
    "default": {"input_price": 0.30, "output_price": 2.50, "audio_input_price": 1.0, "index_price": 0.0015},
}


def _load_secret_files() -> dict[str, str | None]:
    """
    Allow secrets to come from file paths referenced via {NAME}_FILE env vars
    (Docker/K8s secrets). Returns a partial settings dict.
    """
    values: dict[str, str | None] = {}
    for key in SECRET_FILE_KEYS:
        path = os.getenv(f"{key}_FILE")
        if not path:
            continue
        try:
            content = Path(path).read_text().strip()
        except FileNotFoundError as exc:
            raise ValueError(f"{key}_FILE points to missing file: {path}") from exc
        values[key] = content
    return values


class Settings(BaseSettings):
    """Application configuration with strong validation and production safety checks."""

    # Environment / mode
    ENVIRONMENT: str = "development"  # development | test | staging | production
    GEMINI_MOCK_MODE: bool = True
    ALLOW_MOCK_IN_PROD: bool = False  # Explicit opt-in override for staging/production

    # Core behavior toggles
    STRICT_MODE: bool = True

    # Secrets
    JWT_SECRET: str = DEV_DEFAULT_JWT_SECRET
    GEMINI_API_KEY: str | None = None

    # Database
    DATABASE_URL: str = "sqlite:///./rag.db"

    # Redis / rate limiting
    REDIS_URL: Optional[str] = None
    REQUIRE_REDIS_IN_PRODUCTION: bool = True

    # Security toggles
    ALLOW_DEV_LOGIN: bool = False
    REQUIRE_CSRF_HEADER: bool = True
    ALLOW_METADATA_FILTERS: bool = False
    METADATA_FILTER_ALLOWED_KEYS: List[str] = []

    # Auth / JWT
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_ISSUER: str = "rag-assistant"
    JWT_AUDIENCE: str = "rag-users"

    # CORS / rate limiting
    CORS_ORIGINS: List[AnyHttpUrl] = Field(default_factory=list)
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    CORS_ALLOW_HEADERS: List[str] = ["Authorization", "Content-Type", "X-Requested-With", "X-Request-ID"]
    RATE_LIMIT_PER_MINUTE: int = 120
    CHAT_RATE_LIMIT_PER_MINUTE: int = 10
    UPLOAD_RATE_LIMIT_PER_MINUTE: int = 10
    LOGIN_RATE_LIMIT_PER_MINUTE: int = 20
    TRUSTED_PROXY_IPS: List[str] = []
    METRICS_ALLOW_ALL: bool = False

    # Uploads / storage
    MAX_UPLOAD_MB: int = 25
    UPLOAD_PROFILE: str = "safe"  # safe | office | all-supported | custom
    ALLOWED_UPLOAD_MIMES: List[str] = list(SAFE_DEFAULT_UPLOAD_MIMES)
    TMP_DIR: str = Field(
        default="/tmp/rag_uploads",
        validation_alias="UPLOAD_FOLDER",  # support UPLOAD_FOLDER env for portability
    )
    TMP_MAX_AGE_HOURS: int = 24
    MAX_STORES_PER_USER: int = 10
    MAX_JSON_MB: int = 10
    GCS_ARCHIVE_BUCKET: Optional[str] = None

    # Gemini / model settings
    DEFAULT_MODEL: str = "gemini-2.5-flash"
    GEMINI_HTTP_TIMEOUT_S: int = 60
    GEMINI_RETRY_ATTEMPTS: int = 3
    GEMINI_STREAM_RETRY_ATTEMPTS: int = 2
    STREAM_KEEPALIVE_SECS: float = 10.0
    MAX_CONCURRENT_STREAMS: int = 50
    GEMINI_INGESTION_TIMEOUT_S: int = 180

    # Watchdog for stuck documents
    WATCHDOG_TTL_MINUTES: int = 60
    WATCHDOG_CRON_MINUTES: int = 15

    # Cost tracking
    PRICE_PER_MTOK_INPUT: float = 0.30
    PRICE_PER_MTOK_OUTPUT: float = 2.50
    PRICE_PER_MTOK_INDEX: float = 0.0015
    MODEL_PRICING: Dict[str, Dict[str, float]] = Field(
        default_factory=lambda: {k: dict(v) for k, v in DEFAULT_MODEL_PRICING.items()}
    )
    BUDGET_HOLD_USD: float = 0.05
    PRICE_CHECK_STRICT: bool = False

    _env_file = ".env" if (os.getenv("ENVIRONMENT") or "development").lower() != "production" else None

    model_config = SettingsConfigDict(
        env_file=_env_file,
        case_sensitive=False,
        extra="ignore",  # allow forward-compatible env vars
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: Any,
        env_settings: Any,
        dotenv_settings: Any,
        file_secret_settings: Any,
    ) -> tuple[Any, ...]:
        # Read *_FILE secrets before environment variables for predictable overrides.
        return (
            init_settings,
            _load_secret_files,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )

    # ----- Field-level validation -------------------------------------------------

    @field_validator("JWT_SECRET")
    @classmethod
    def validate_jwt_secret(cls, value: str, _info: ValidationInfo) -> str:
        if not value:
            raise ValueError("JWT_SECRET must be set")
        if len(value) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters long")
        return value

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def validate_gemini_api_key(cls, value: str | None, info: ValidationInfo) -> str | None:
        mock_mode = bool(info.data.get("GEMINI_MOCK_MODE"))
        if mock_mode:
            return value
        if not value:
            raise ValueError("GEMINI_API_KEY must be set when GEMINI_MOCK_MODE is false")
        return value

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> Any:
        """Allow both JSON array and comma-separated string for CORS_ORIGINS."""
        if isinstance(value, str):
            import json

            # Try JSON array first
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                # Fallback to single origin or comma-separated
                parts = [v.strip() for v in value.split(",") if v.strip()]
                return parts
            else:
                if isinstance(parsed, list):
                    return parsed
        return value

    @field_validator("TRUSTED_PROXY_IPS", mode="before")
    @classmethod
    def parse_trusted_proxies(cls, value: Any) -> List[str]:
        """Allow JSON array or comma-separated string for trusted proxies."""
        if value is None:
            return []
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [v.strip() for v in value.split(",") if v.strip()]
            else:
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
                if isinstance(parsed, str):
                    return [parsed.strip()]
                return []
        return value

    @field_validator("TRUSTED_PROXY_IPS")
    @classmethod
    def validate_trusted_proxies(cls, value: List[str]) -> List[str]:
        """Ensure each trusted proxy entry is a valid IP or CIDR."""
        networks = []
        for cidr in value:
            try:
                networks.append(str(ipaddress.ip_network(cidr, strict=False)))
            except ValueError as exc:
                raise ValueError(f"Invalid TRUSTED_PROXY_IPS entry '{cidr}': {exc}")
        return networks

    @field_validator("CORS_ALLOW_CREDENTIALS")
    @classmethod
    def validate_cors_credentials(cls, value: bool, info: ValidationInfo) -> bool:
        if value:
            origins = info.data.get("CORS_ORIGINS") or []
            if any(str(o).strip() == "*" for o in origins):
                raise ValueError("CORS_ORIGINS cannot include '*' when CORS_ALLOW_CREDENTIALS=true")
        return value

    @field_validator("ENVIRONMENT")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        value = value.lower()
        if value not in {"development", "test", "staging", "production"}:
            raise ValueError("ENVIRONMENT must be one of: development, test, staging, production")
        return value

    @field_validator("UPLOAD_PROFILE")
    @classmethod
    def validate_upload_profile(cls, value: str) -> str:
        value = value.lower()
        if value not in {"safe", "office", "all-supported", "custom"}:
            raise ValueError("UPLOAD_PROFILE must be one of: safe, office, all-supported, custom")
        return value

    @field_validator("METADATA_FILTER_ALLOWED_KEYS", mode="before")
    @classmethod
    def parse_metadata_filter_keys(cls, value: Any) -> List[str]:
        """Allow JSON array or comma-separated string for allowed metadata keys."""
        if value is None:
            return []
        if isinstance(value, str):
            import json

            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return [v.strip() for v in value.split(",") if v.strip()]
            else:
                if isinstance(parsed, list):
                    return [str(v).strip() for v in parsed if str(v).strip()]
                if isinstance(parsed, str):
                    return [parsed.strip()] if parsed.strip() else []
                return []
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return []

    @field_validator("METADATA_FILTER_ALLOWED_KEYS")
    @classmethod
    def validate_metadata_filter_keys(cls, value: List[str]) -> List[str]:
        """Normalize and deduplicate allowed metadata keys."""
        normalized: list[str] = []
        for key in value:
            key = (key or "").strip()
            if not key:
                continue
            if len(key) > 64:
                key = key[:64]
            if key not in normalized:
                normalized.append(key)
        return normalized

    @field_validator("MODEL_PRICING")
    @classmethod
    def validate_model_pricing(cls, value: Dict[str, Dict[str, float]]) -> Dict[str, Dict[str, float]]:
        if "default" not in value:
            raise ValueError("MODEL_PRICING must include a 'default' entry")
        for name, rates in value.items():
            if not isinstance(rates, dict):
                raise ValueError("MODEL_PRICING entries must be mappings")
            for key in ("input_price", "output_price"):
                if float(rates.get(key, 0)) <= 0:
                    raise ValueError(f"MODEL_PRICING[{name}].{key} must be > 0")
        return value

    @model_validator(mode="after")
    def apply_upload_profile(self) -> "Settings":
        """Derive ALLOWED_UPLOAD_MIMES when using a managed profile."""
        if self.UPLOAD_PROFILE == "safe":
            self.ALLOWED_UPLOAD_MIMES = list(SAFE_DEFAULT_UPLOAD_MIMES)
        elif self.UPLOAD_PROFILE == "office":
            self.ALLOWED_UPLOAD_MIMES = list(OFFICE_UPLOAD_MIMES)
        elif self.UPLOAD_PROFILE == "all-supported":
            self.ALLOWED_UPLOAD_MIMES = list(ALL_SUPPORTED_UPLOAD_MIMES)

        lowered = {mime.lower() for mime in self.ALLOWED_UPLOAD_MIMES}
        unknown = lowered - GEMINI_SUPPORTED_MIMES
        if unknown:
            raise ValueError(f"ALLOWED_UPLOAD_MIMES contains MIME types not supported by Gemini: {sorted(unknown)}")
        self.ALLOWED_UPLOAD_MIMES = sorted(lowered)
        return self

    # ----- Cross-field / production invariants -----------------------------------

    @model_validator(mode="after")
    def validate_production_safety(self) -> "Settings":
        """Enforce strong invariants when running in production."""
        if self.ENVIRONMENT != "production":
            if self.PRICE_CHECK_STRICT:
                self._validate_pricing()
            return self

        # No dev login in production
        if self.ALLOW_DEV_LOGIN:
            raise ValueError("ALLOW_DEV_LOGIN must be false in production")

        # No SQLite in production
        if self.DATABASE_URL.startswith("sqlite:"):
            raise ValueError(
                "SQLite (DATABASE_URL starting with 'sqlite:') is not allowed in production; use PostgreSQL instead."
            )

        # No default/weak DB password in production
        url = make_url(self.DATABASE_URL)
        pwd = url.password or ""
        if pwd in DEFAULT_DB_PASSWORDS:
            raise ValueError(
                "Default/blank database password is not allowed in production. Set a strong password in DATABASE_URL."
            )

        # No default JWT secret in production
        if self.JWT_SECRET == DEV_DEFAULT_JWT_SECRET:
            raise ValueError("Default JWT_SECRET is not allowed in production")

        # Require Redis when configured to
        if self.REQUIRE_REDIS_IN_PRODUCTION and not self.REDIS_URL:
            raise ValueError("REDIS_URL is required in production when REQUIRE_REDIS_IN_PRODUCTION=true")

        # CSRF protection must not be disabled in production
        if not self.REQUIRE_CSRF_HEADER:
            raise ValueError("REQUIRE_CSRF_HEADER must be true in production")

        self._validate_pricing()
        return self

    def _validate_pricing(self) -> None:
        """Ensure token pricing is non-zero when enforcement is required."""
        default_rates = (self.MODEL_PRICING or {}).get("default", {})
        input_price = float(default_rates.get("input_price", self.PRICE_PER_MTOK_INPUT))
        output_price = float(default_rates.get("output_price", self.PRICE_PER_MTOK_OUTPUT))
        index_price = float(default_rates.get("index_price", self.PRICE_PER_MTOK_INDEX))
        if input_price <= 0 or output_price <= 0 or index_price <= 0:
            raise ValueError(
                "MODEL_PRICING.default (or PRICE_PER_MTOK_*) input/output/index prices must be > 0 when "
                "PRICE_CHECK_STRICT=true or ENVIRONMENT=production"
            )


settings = Settings()
