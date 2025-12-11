"""
Test factories.

Rules:
- NEVER create own sessions
- NEVER call commit() - use flush() only
- Accept db session as first parameter
"""

from decimal import Decimal
from sqlalchemy.orm import Session

from app.models import User, Store, Budget, Document, DocumentStatus, ChatSession, ChatHistory
from app.auth import hash_password


class UserFactory:
    """User factory."""

    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        email: str | None = None,
        password: str = "TestPass123!",
        is_admin: bool = False,
        is_active: bool = True,
        hashed_password: str | None = None,
    ) -> User:
        cls._counter += 1
        email = email or f"test-user-{cls._counter}@example.com"

        user = User(
            email=email.lower(),
            hashed_password=hashed_password if hashed_password is not None else hash_password(password),
            is_admin=is_admin,
            is_active=is_active,
            email_verified=True,
        )
        db.add(user)
        db.flush()
        db.refresh(user)
        return user

    @classmethod
    def create_admin(cls, db: Session, **kwargs) -> User:
        kwargs.setdefault("is_admin", True)
        return cls.create(db, **kwargs)

    @classmethod
    def create_dev_user(cls, db: Session, email: str | None = None) -> User:
        """User for dev-token login (empty password hash)."""
        return cls.create(db, email=email, hashed_password="")


class StoreFactory:
    """Store factory."""

    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        user: User | None = None,
        user_id: int | None = None,
        display_name: str | None = None,
        fs_name: str | None = None,
    ) -> Store:
        cls._counter += 1

        if user is not None:
            user_id = user.id
        elif user_id is None:
            user = UserFactory.create(db)
            user_id = user.id

        display_name = display_name or f"Test Store {cls._counter}"
        fs_name = fs_name or f"stores/test-{cls._counter}"

        store = Store(
            user_id=user_id,
            display_name=display_name,
            fs_name=fs_name,
        )
        db.add(store)
        db.flush()
        db.refresh(store)
        return store


class BudgetFactory:
    """Budget factory."""

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        user: User | None = None,
        user_id: int | None = None,
        monthly_limit_usd: float = 10.0,
    ) -> Budget:
        if user is not None:
            user_id = user.id
        elif user_id is None:
            user = UserFactory.create(db)
            user_id = user.id

        budget = Budget(
            user_id=user_id,
            monthly_limit_usd=Decimal(str(monthly_limit_usd)),
        )
        db.add(budget)
        db.flush()
        db.refresh(budget)
        return budget


class DocumentFactory:
    """Document factory."""

    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        store: Store | None = None,
        store_id: int | None = None,
        filename: str | None = None,
        status: DocumentStatus = DocumentStatus.PENDING,
        size_bytes: int = 1024,
    ) -> Document:
        cls._counter += 1

        if store is not None:
            store_id = store.id
        elif store_id is None:
            store = StoreFactory.create(db)
            store_id = store.id

        filename = filename or f"test-doc-{cls._counter}.pdf"

        doc = Document(
            store_id=store_id,
            filename=filename,
            display_name=filename,
            size_bytes=size_bytes,
            status=status,
        )
        db.add(doc)
        db.flush()
        db.refresh(doc)
        return doc


class ChatSessionFactory:
    """Chat session factory."""

    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        user: User | None = None,
        user_id: int | None = None,
        store: Store | None = None,
        store_id: int | None = None,
        session_id: str | None = None,
        title: str | None = None,
    ) -> ChatSession:
        cls._counter += 1

        if user is not None:
            user_id = user.id
        elif user_id is None:
            user = UserFactory.create(db)
            user_id = user.id

        if store is not None:
            store_id = store.id

        session_id = session_id or f"test-session-{cls._counter}"
        title = title or f"Test Chat {cls._counter}"

        chat_session = ChatSession(
            id=session_id,
            user_id=user_id,
            store_id=store_id,
            title=title,
        )
        db.add(chat_session)
        db.flush()
        db.refresh(chat_session)
        return chat_session


class ChatHistoryFactory:
    """Chat history message factory."""

    _counter = 0

    @classmethod
    def create(
        cls,
        db: Session,
        *,
        user: User | None = None,
        user_id: int | None = None,
        store_id: int | None = None,
        session_id: str,
        role: str = "user",
        content: str | None = None,
    ) -> ChatHistory:
        cls._counter += 1

        if user is not None:
            user_id = user.id
        elif user_id is None:
            user = UserFactory.create(db)
            user_id = user.id

        content = content or f"Test message {cls._counter}"

        msg = ChatHistory(
            user_id=user_id,
            store_id=store_id,
            session_id=session_id,
            role=role,
            content=content,
        )
        db.add(msg)
        db.flush()
        db.refresh(msg)
        return msg
