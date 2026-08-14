from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

from apps.api.config import Settings, get_settings
from apps.api.database import SessionLocal, get_db
from apps.api.models import (
    AuthLoginAttempt,
    User,
    UserCredential,
    UserSession,
    Workspace,
    WorkspaceMember,
    WorkspaceOnboarding,
)
from apps.api.onboarding import slugify

SESSION_TOKEN_BYTES = 32
PASSWORD_VERSION = "pbkdf2-sha256-v1"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
WORKSPACE_PATH_PATTERN = re.compile(r"^/api/v1/workspaces/([^/]+)(?:/|$)")
PUBLIC_AUTH_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_PATTERN.fullmatch(normalized):
        raise ValueError("Enter a valid email address")
    return normalized


def validate_password(value: str) -> str:
    if len(value) < 10:
        raise ValueError("Password must be at least 10 characters")
    if len(value) > 128:
        raise ValueError("Password must be at most 128 characters")
    if not any(character.isalpha() for character in value):
        raise ValueError("Password must include a letter")
    if not any(character.isdigit() for character in value):
        raise ValueError("Password must include a number")
    return value


def hash_password(password: str, *, iterations: int) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return "$".join(
        (
            "pbkdf2_sha256",
            str(iterations),
            base64.urlsafe_b64encode(salt).decode().rstrip("="),
            base64.urlsafe_b64encode(digest).decode().rstrip("="),
        )
    )


def _decode_base64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt_text, digest_text = encoded.split("$", maxsplit=3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iteration_text)
        salt = _decode_base64(salt_text)
        expected = _decode_base64(digest_text)
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return hmac.compare_digest(actual, expected)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthRegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=10, max_length=128)
    workspace_name: str = Field(min_length=2, max_length=160)
    timezone: str = Field(default="UTC", min_length=2, max_length=80)

    @field_validator("email")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        return validate_password(value)


class AuthLoginRequest(BaseModel):
    email: str = Field(min_length=5, max_length=320)
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def normalize_email_field(cls, value: str) -> str:
        return normalize_email(value)


class AuthPasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=10, max_length=128)

    @field_validator("new_password")
    @classmethod
    def validate_password_field(cls, value: str) -> str:
        return validate_password(value)


class AuthUserResponse(BaseModel):
    id: str
    name: str
    email: str
    is_platform_admin: bool


class AuthWorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    role: str
    onboarding_status: str


class AuthSessionResponse(BaseModel):
    user: AuthUserResponse
    workspace: AuthWorkspaceResponse
    workspaces: list[AuthWorkspaceResponse]
    onboarding_url: str


class AuthMessageResponse(BaseModel):
    detail: str


class InvalidCredentialsError(Exception):
    pass


class LoginRateLimitedError(Exception):
    pass


@dataclass(frozen=True)
class AuthenticatedSession:
    user: User
    session: UserSession
    workspace_roles: dict[str, str]


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def register(self, payload: AuthRegisterRequest) -> tuple[User, Workspace, str]:
        existing = self._session.scalar(select(User.id).where(User.email == payload.email))
        if existing is not None:
            raise ValueError("An account with this email already exists")
        now = datetime.now(tz=UTC)
        user = User(
            id=str(uuid4()),
            email=payload.email,
            name=payload.name.strip(),
            is_platform_admin=False,
            created_at=now,
        )
        workspace = Workspace(
            id=str(uuid4()),
            name=payload.workspace_name.strip(),
            slug=self._unique_slug(payload.workspace_name),
            plan="private_beta",
            timezone=payload.timezone,
            created_at=now,
        )
        self._session.add_all((user, workspace))
        self._session.flush()
        self._session.add(
            UserCredential(
                user_id=user.id,
                password_hash=hash_password(
                    payload.password,
                    iterations=self._settings.auth_password_iterations,
                ),
                password_version=PASSWORD_VERSION,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        self._session.add(WorkspaceMember(workspace_id=workspace.id, user_id=user.id, role="owner"))
        self._session.add(
            WorkspaceOnboarding(
                workspace_id=workspace.id,
                status="in_progress",
                current_step=1,
                completed_steps_json=[],
                completed_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        token = self.create_session(user.id)
        self._session.commit()
        return user, workspace, token

    def authenticate(self, email: str, password: str, client_ip: str) -> tuple[User, str]:
        key = self._attempt_key(email, client_ip)
        self._raise_if_blocked(key)
        user = self._session.scalar(select(User).where(User.email == email))
        credential = self._session.get(UserCredential, user.id) if user else None
        encoded = credential.password_hash if credential else self._dummy_password_hash()
        valid = verify_password(password, encoded)
        if user is None or credential is None or not valid:
            self._record_failure(key)
            self._session.commit()
            raise InvalidCredentialsError
        self._session.execute(delete(AuthLoginAttempt).where(AuthLoginAttempt.key_hash == key))
        token = self.create_session(user.id)
        self._session.commit()
        return user, token

    def resolve_session(self, token: str | None) -> AuthenticatedSession | None:
        if not token:
            return None
        now = datetime.now(tz=UTC)
        row = self._session.scalar(
            select(UserSession).where(
                UserSession.token_hash == token_hash(token),
                UserSession.revoked_at.is_(None),
            )
        )
        if row is None or _aware(row.expires_at) <= now:
            return None
        user = self._session.get(User, row.user_id)
        if user is None:
            return None
        memberships = list(
            self._session.scalars(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id))
        )
        if _aware(row.last_seen_at) < now - timedelta(hours=1):
            row.last_seen_at = now
            self._session.commit()
        return AuthenticatedSession(
            user=user,
            session=row,
            workspace_roles={item.workspace_id: item.role for item in memberships},
        )

    def revoke_session(self, token: str | None) -> None:
        if not token:
            return
        row = self._session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash(token))
        )
        if row is not None and row.revoked_at is None:
            row.revoked_at = datetime.now(tz=UTC)
            self._session.commit()

    def change_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str,
    ) -> str:
        credential = self._session.get(UserCredential, user_id)
        if credential is None or not verify_password(current_password, credential.password_hash):
            raise InvalidCredentialsError
        now = datetime.now(tz=UTC)
        credential.password_hash = hash_password(
            new_password,
            iterations=self._settings.auth_password_iterations,
        )
        credential.password_version = PASSWORD_VERSION
        credential.password_changed_at = now
        credential.updated_at = now
        self._session.execute(delete(UserSession).where(UserSession.user_id == user_id))
        token = self.create_session(user_id)
        self._session.commit()
        return token

    def create_session(self, user_id: str) -> str:
        now = datetime.now(tz=UTC)
        self._session.execute(
            delete(UserSession).where(
                UserSession.user_id == user_id,
                UserSession.expires_at <= now,
            )
        )
        token = secrets.token_urlsafe(SESSION_TOKEN_BYTES)
        self._session.add(
            UserSession(
                id=str(uuid4()),
                user_id=user_id,
                token_hash=token_hash(token),
                expires_at=now + timedelta(days=self._settings.auth_session_days),
                last_seen_at=now,
                revoked_at=None,
                created_at=now,
            )
        )
        return token

    def _unique_slug(self, workspace_name: str) -> str:
        base = slugify(workspace_name)
        candidate = base
        suffix = 2
        while self._session.scalar(select(Workspace.id).where(Workspace.slug == candidate)):
            candidate = f"{base}-{suffix}"
            suffix += 1
        return candidate

    def _attempt_key(self, email: str, client_ip: str) -> str:
        pepper = self._settings.auth_pepper.get_secret_value()
        material = f"{pepper}:{email}:{client_ip}".encode()
        return hashlib.sha256(material).hexdigest()

    def _raise_if_blocked(self, key: str) -> None:
        row = self._session.get(AuthLoginAttempt, key)
        if row and row.blocked_until and _aware(row.blocked_until) > datetime.now(tz=UTC):
            raise LoginRateLimitedError

    def _record_failure(self, key: str) -> None:
        now = datetime.now(tz=UTC)
        row = self._session.get(AuthLoginAttempt, key)
        window = timedelta(minutes=self._settings.auth_login_window_minutes)
        if row is None or _aware(row.window_started_at) <= now - window:
            row = AuthLoginAttempt(
                key_hash=key,
                failure_count=1,
                window_started_at=now,
                blocked_until=None,
                updated_at=now,
            )
            self._session.merge(row)
            return
        row.failure_count += 1
        row.updated_at = now
        if row.failure_count >= self._settings.auth_login_max_failures:
            row.blocked_until = now + timedelta(minutes=self._settings.auth_login_block_minutes)

    def _dummy_password_hash(self) -> str:
        salt = b"earlysignal-auth"
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            b"not-the-password",
            salt,
            self._settings.auth_password_iterations,
        )
        return "$".join(
            (
                "pbkdf2_sha256",
                str(self._settings.auth_password_iterations),
                base64.urlsafe_b64encode(salt).decode().rstrip("="),
                base64.urlsafe_b64encode(digest).decode().rstrip("="),
            )
        )


def _workspace_responses(session: Session, user_id: str) -> list[AuthWorkspaceResponse]:
    memberships = session.execute(
        select(WorkspaceMember, Workspace)
        .join(Workspace, Workspace.id == WorkspaceMember.workspace_id)
        .where(WorkspaceMember.user_id == user_id)
        .order_by(Workspace.created_at)
    ).all()
    result: list[AuthWorkspaceResponse] = []
    for membership, workspace in memberships:
        onboarding = session.get(WorkspaceOnboarding, workspace.id)
        result.append(
            AuthWorkspaceResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                role=membership.role,
                onboarding_status=onboarding.status if onboarding else "in_progress",
            )
        )
    return result


def auth_session_response(session: Session, user: User) -> AuthSessionResponse:
    workspaces = _workspace_responses(session, user.id)
    if not workspaces:
        raise HTTPException(409, "Account has no workspace")
    workspace = workspaces[0]
    return AuthSessionResponse(
        user=AuthUserResponse(
            id=user.id,
            name=user.name,
            email=user.email,
            is_platform_admin=user.is_platform_admin,
        ),
        workspace=workspace,
        workspaces=workspaces,
        onboarding_url=f"/onboarding?workspace={workspace.id}",
    )


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    max_age = settings.auth_session_days * 24 * 60 * 60
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=max_age,
        expires=max_age,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )


DbSession = Annotated[Session, Depends(get_db)]
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
settings = get_settings()


@router.post(
    "/register",
    response_model=AuthSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    payload: AuthRegisterRequest,
    response: Response,
    session: DbSession,
) -> AuthSessionResponse:
    try:
        user, _workspace, token = AuthService(session, settings).register(payload)
    except ValueError as error:
        raise HTTPException(409, str(error)) from error
    set_session_cookie(response, token, settings)
    return auth_session_response(session, user)


@router.post("/login", response_model=AuthSessionResponse)
def login(
    payload: AuthLoginRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> AuthSessionResponse:
    client_ip = request.client.host if request.client else "unknown"
    try:
        user, token = AuthService(session, settings).authenticate(
            payload.email,
            payload.password,
            client_ip,
        )
    except LoginRateLimitedError as error:
        raise HTTPException(429, "Too many login attempts. Try again later.") from error
    except InvalidCredentialsError as error:
        raise HTTPException(401, "Email or password is incorrect") from error
    set_session_cookie(response, token, settings)
    return auth_session_response(session, user)


@router.get("/me", response_model=AuthSessionResponse)
def me(request: Request, session: DbSession) -> AuthSessionResponse:
    user_id = getattr(request.state, "auth_user_id", None)
    user = session.get(User, user_id) if user_id else None
    if user is None:
        raise HTTPException(401, "Authentication required")
    return auth_session_response(session, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, response: Response, session: DbSession) -> Response:
    token = request.cookies.get(settings.auth_cookie_name)
    AuthService(session, settings).revoke_session(token)
    clear_session_cookie(response, settings)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/change-password", response_model=AuthMessageResponse)
def change_password(
    payload: AuthPasswordChangeRequest,
    request: Request,
    response: Response,
    session: DbSession,
) -> AuthMessageResponse:
    user_id = getattr(request.state, "auth_user_id", None)
    if not user_id:
        raise HTTPException(401, "Authentication required")
    try:
        token = AuthService(session, settings).change_password(
            user_id,
            payload.current_password,
            payload.new_password,
        )
    except InvalidCredentialsError as error:
        raise HTTPException(401, "Current password is incorrect") from error
    set_session_cookie(response, token, settings)
    return AuthMessageResponse(detail="Password updated")


class AccountAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        super().__init__(app)
        self._settings = settings

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        path = request.url.path
        if not path.startswith("/api/v1/"):
            return await call_next(request)
        if request.method in UNSAFE_METHODS and not self._origin_allowed(request):
            return JSONResponse({"detail": "Request origin is not allowed"}, status_code=403)

        token = request.cookies.get(self._settings.auth_cookie_name)
        with SessionLocal() as session:
            authenticated = AuthService(session, self._settings).resolve_session(token)
            if authenticated is not None:
                request.state.auth_user_id = authenticated.user.id
                request.state.auth_user_email = authenticated.user.email
                request.state.auth_workspace_roles = authenticated.workspace_roles
                request.state.auth_is_platform_admin = authenticated.user.is_platform_admin

            is_public = path in PUBLIC_AUTH_PATHS or path == "/api/v1/oauth/youtube/callback"
            if self._settings.auth_required and not is_public:
                if authenticated is None:
                    return JSONResponse(
                        {"detail": "Authentication required"},
                        status_code=401,
                    )
                if path.startswith("/api/v1/admin/") and not (authenticated.user.is_platform_admin):
                    return JSONResponse(
                        {"detail": "Platform administrator access required"},
                        status_code=403,
                    )
                workspace_match = WORKSPACE_PATH_PATTERN.match(path)
                if workspace_match and (
                    workspace_match.group(1) not in authenticated.workspace_roles
                ):
                    return JSONResponse(
                        {"detail": "Workspace access denied"},
                        status_code=403,
                    )
        return await call_next(request)

    def _origin_allowed(self, request: Request) -> bool:
        origin = request.headers.get("origin")
        if not origin:
            return True
        return origin.rstrip("/") in self._settings.allowed_web_origins
