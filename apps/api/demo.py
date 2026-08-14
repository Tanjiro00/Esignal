from datetime import UTC, datetime
from uuid import UUID, uuid5

DEMO_NAMESPACE = UUID("7a61f9d6-b9dc-4fb2-8dc4-e778a63aef01")


def demo_id(kind: str, key: str | int) -> str:
    return str(uuid5(DEMO_NAMESPACE, f"{kind}:{key}"))


DEMO_USER_ID = demo_id("user", "owner")
DEMO_WORKSPACE_ID = demo_id("workspace", "atlas-labs")
DEMO_OWNED_CHANNEL_ID = demo_id("channel", 0)
DEMO_REFERENCE_AT = datetime(2026, 7, 26, 18, tzinfo=UTC)
