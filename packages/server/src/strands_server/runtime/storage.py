"""Persistent, encrypted storage for FastMCP `OAuthProxy` state."""

import os
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import fastmcp
from cryptography.fernet import Fernet
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.stores.memory import MemoryStore
from key_value.aio.stores.redis import RedisStore
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper

ENCRYPTION_KEY_ENV = "STRANDS_STORAGE_ENCRYPTION_KEY"
FALLBACK_ENCRYPTION_KEY_ENV = "OUBLIAI_STORAGE_ENCRYPTION_KEY"
STORAGE_URL_ENV = "STRANDS_STORAGE_URL"
FALLBACK_STORAGE_URL_ENV = "OUBLIAI_STORAGE_URL"
DEFAULT_DIRECTORY_NAME = "strands-storage"
_SCHEMES = "memory://, file://<path>, redis://..., rediss://..."


def _fernet(env: Mapping[str, str]) -> Fernet:
    key = env.get(ENCRYPTION_KEY_ENV) or env.get(FALLBACK_ENCRYPTION_KEY_ENV)
    if not key:
        raise SystemExit(
            f"Set {ENCRYPTION_KEY_ENV} to a Fernet key "
            "(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')."
        )
    try:
        return Fernet(key)
    except ValueError as error:
        raise SystemExit(f"{ENCRYPTION_KEY_ENV} is not a valid Fernet key: {error}") from error


def _filetree(directory: Path) -> FileTreeStore:
    directory.mkdir(parents=True, exist_ok=True)
    return FileTreeStore(
        data_directory=directory,
        key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(directory),
        collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(directory),
    )


def _backend(url: str | None) -> AsyncKeyValue:
    if not url:
        return _filetree(Path(fastmcp.settings.home) / DEFAULT_DIRECTORY_NAME)
    parsed = urlparse(url)
    if parsed.scheme == "memory":
        return MemoryStore()
    if parsed.scheme == "file":
        return _filetree(Path(parsed.netloc + parsed.path))
    if parsed.scheme in {"redis", "rediss"}:
        return RedisStore(url=url)
    raise SystemExit(f"{STORAGE_URL_ENV}={url!r} is not supported; use one of {_SCHEMES}")


def build_client_storage(env: Mapping[str, str] | None = None) -> FernetEncryptionWrapper:
    """Encrypted `client_storage` for `OAuthProxy`, selected from the environment."""
    source = os.environ if env is None else env
    fernet = _fernet(source)
    url = source.get(STORAGE_URL_ENV) or source.get(FALLBACK_STORAGE_URL_ENV)
    return FernetEncryptionWrapper(key_value=_backend(url), fernet=fernet)
