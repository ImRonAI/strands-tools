from pathlib import Path

from cryptography.fernet import Fernet
from fastmcp.client.auth import BearerAuth, OAuth
from key_value.aio.protocols import AsyncKeyValue
from key_value.aio.stores.filetree import (
    FileTreeStore,
    FileTreeV1CollectionSanitizationStrategy,
    FileTreeV1KeySanitizationStrategy,
)
from key_value.aio.wrappers.encryption import FernetEncryptionWrapper


def bearer(token: str) -> BearerAuth:
    return BearerAuth(token)


def oauth(
    *,
    mcp_url: str | None = None,
    scopes: str | list[str] | None = None,
    client_name: str = "FastMCP Client",
    token_storage: AsyncKeyValue | None = None,
    additional_client_metadata: dict[str, object] | None = None,
    callback_port: int | None = None,
    callback_host: str = "localhost",
    callback_timeout: float = 300.0,
    client_metadata_url: str | None = None,
    client_id: str | None = None,
    client_secret: str | None = None,
) -> OAuth:
    return OAuth(
        mcp_url=mcp_url,
        scopes=scopes,
        client_name=client_name,
        token_storage=token_storage,
        additional_client_metadata=additional_client_metadata,
        callback_port=callback_port,
        callback_host=callback_host,
        callback_timeout=callback_timeout,
        client_metadata_url=client_metadata_url,
        client_id=client_id,
        client_secret=client_secret,
    )


def file_token_storage(directory: str | Path, encryption_key: str | bytes) -> FernetEncryptionWrapper:
    """Encrypted on-disk OAuth token storage."""
    path = Path(directory)
    path.mkdir(parents=True, exist_ok=True)
    key = encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
    return FernetEncryptionWrapper(
        key_value=FileTreeStore(
            data_directory=path,
            key_sanitization_strategy=FileTreeV1KeySanitizationStrategy(path),
            collection_sanitization_strategy=FileTreeV1CollectionSanitizationStrategy(path),
        ),
        fernet=Fernet(key),
    )
