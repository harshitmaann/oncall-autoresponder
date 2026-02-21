
import os

def _csv_env(name: str, default: str = "") -> set[str]:
    val = os.getenv(name, default).strip()
    if not val:
        return set()
    return {x.strip() for x in val.split(",") if x.strip()}

ALLOWED_NAMESPACES = _csv_env("ALLOWED_NAMESPACES", "default")
ALLOWED_ACTIONS = _csv_env("ALLOWED_ACTIONS", "rollout_restart")

def assert_allowed(action: str, namespace: str) -> None:
    if action not in ALLOWED_ACTIONS:
        raise PermissionError(f"Action not allowed: {action}")
    if namespace not in ALLOWED_NAMESPACES:
        raise PermissionError(f"Namespace not allowed: {namespace}")
