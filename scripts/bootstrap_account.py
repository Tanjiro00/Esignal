from __future__ import annotations

import argparse
import os
from datetime import UTC, datetime

from sqlalchemy import select

from apps.api.auth import PASSWORD_VERSION, hash_password, normalize_email
from apps.api.config import get_settings
from apps.api.database import SessionLocal
from apps.api.models import User, UserCredential


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create or rotate a credential for an existing EarlySignal user."
    )
    parser.add_argument("--email", required=True)
    parser.add_argument("--platform-admin", action="store_true")
    args = parser.parse_args()
    password = os.environ.get("EARLYSIGNAL_BOOTSTRAP_PASSWORD")
    if not password:
        raise SystemExit("EARLYSIGNAL_BOOTSTRAP_PASSWORD is required")

    settings = get_settings()
    now = datetime.now(tz=UTC)
    with SessionLocal() as session:
        user = session.scalar(select(User).where(User.email == normalize_email(args.email)))
        if user is None:
            raise SystemExit("No existing user found for that email")
        credential = session.get(UserCredential, user.id)
        password_hash = hash_password(
            password,
            iterations=settings.auth_password_iterations,
        )
        if credential is None:
            credential = UserCredential(
                user_id=user.id,
                password_hash=password_hash,
                password_version=PASSWORD_VERSION,
                password_changed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(credential)
        else:
            credential.password_hash = password_hash
            credential.password_version = PASSWORD_VERSION
            credential.password_changed_at = now
            credential.updated_at = now
        if args.platform_admin:
            user.is_platform_admin = True
        session.commit()
        print(f"Credential updated for {user.email}")


if __name__ == "__main__":
    main()
