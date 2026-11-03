# pyright: strict
"""Authentication provider & unified credential registry for Strands Tools FastMCP Server.

Supports:
1. FastMCP OAuthProxy (`build_auth`) for multi-tenant MCP client OAuth + token introspection.
2. FastMCP StaticTokenVerifier (`STRANDS_ACCESS_TOKEN` / `OUBLIAI_ACCESS_TOKEN`) for single-tenant operator mode.
3. Unified Strands toolsuite credential management across all integrated tool suites.
"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from typing import TypedDict, TypeGuard

import httpx2
from fastmcp.server.auth import OAuthProxy
from fastmcp.server.auth.providers.introspection import IntrospectionTokenVerifier
from key_value.aio.protocols import AsyncKeyValue

INTROSPECTION_CACHE_TTL_SECONDS = 60


class CredentialSchemaEntry(TypedDict):
    title: str
    env_vars: list[str]
    auth_tools: list[str]


CREDENTIAL_SCHEMAS: dict[str, CredentialSchemaEntry] = {
    "strands_google": {
        "title": "Strands Google (Workspace, Gmail, Drive, Calendar, Sheets, Docs, YouTube)",
        "env_vars": [
            "GOOGLE_OAUTH_CREDENTIALS",
            "GOOGLE_API_KEY",
            "GOOGLE_CREDENTIALS_PATH",
            "GOOGLE_TOKEN_PATH",
        ],
        "auth_tools": ["google_auth", "use_google"],
    },
    "strands_fun_tools": {
        "title": "Strands Fun Tools (UI, Audio, Vision, Face Auth, Chess, Bluetooth, Clipboard)",
        "env_vars": [
            "BYPASS_TOOL_CONSENT",
            "STOCKFISH_PATH",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "STRANDS_FACE_JWT_SECRET",
            "STRANDS_FACE_AUTH_DIR",
        ],
        "auth_tools": ["utility", "face_recognition"],
    },
    "strands_tools": {
        "title": "Strands Agent Tools (AWS, Search, Memory, Multi-Agent, Code, Media)",
        "env_vars": [
            "AWS_PROFILE",
            "AWS_REGION",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "BYPASS_TOOL_CONSENT",
            "TAVILY_API_KEY",
            "EXA_API_KEY",
            "BRIGHTDATA_API_KEY",
            "SLACK_BOT_TOKEN",
            "MEM0_API_KEY",
        ],
        "auth_tools": ["environment", "use_aws"],
    },
    "strands_pack": {
        "title": "Strands Pack (YouTube, GitHub, Discord, Notion, Twilio, Box, Calendly, Runtime)",
        "env_vars": [
            "YOUTUBE_API_KEY",
            "GITHUB_TOKEN",
            "DISCORD_BOT_TOKEN",
            "NOTION_TOKEN",
            "TWILIO_ACCOUNT_SID",
            "TWILIO_AUTH_TOKEN",
            "BOX_CLIENT_ID",
            "BOX_CLIENT_SECRET",
            "BOX_DEVELOPER_TOKEN",
            "CALENDLY_TOKEN",
            "X_BEARER_TOKEN",
            "OPENROUTER_API_KEY",
            "OPENAI_API_KEY",
            "SUPABASE_URL",
            "SUPABASE_KEY",
            "LINKEDIN_ACCESS_TOKEN",
            "REDDIT_CLIENT_ID",
            "REDDIT_CLIENT_SECRET",
        ],
        "auth_tools": ["secrets_manager", "dotenv"],
    },
    "strands_telegram": {
        "title": "Strands Telegram & Telegram Listener",
        "env_vars": [
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_DEFAULT_CHAT_ID",
            "STRANDS_TELEGRAM_AUTO_LISTEN",
        ],
        "auth_tools": ["telegram", "telegram_listener"],
    },
    "strands_zero": {
        "title": "Strands Zero Compiler & Toolchain",
        "env_vars": ["ZERO_BIN_PATH"],
        "auth_tools": ["zero_doctor", "zero_version"],
    },
    "strands_utcp": {
        "title": "Strands Universal Tool Calling Protocol (UTCP)",
        "env_vars": ["UTCP_CONFIG_PATH"],
        "auth_tools": ["utcp", "utcp_register_manual"],
    },
    "strands_harness": {
        "title": "Strands Harness & Model Providers (Google Gemini, xAI Grok, Groq, Anthropic, OpenAI, Bedrock, LiteLLM, Ollama, Mistral, Writer, LlamaAPI)",
        "env_vars": [
            "STRANDS_DEFAULT_MODEL",
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "XAI_API_KEY",
            "XAI_BASE_URL",
            "XAI_MODEL_ID",
            "GROQ_API_KEY",
            "GROQ_BASE_URL",
            "GROQ_MODEL_ID",
            "ANTHROPIC_API_KEY",
            "ANTHROPIC_MODEL_ID",
            "OPENAI_API_KEY",
            "OPENAI_MODEL_ID",
            "AWS_BEARER_TOKEN_BEDROCK",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "AWS_REGION",
            "LITELLM_API_KEY",
            "LITELLM_BASE_URL",
            "OLLAMA_API_KEY",
            "OLLAMA_HOST",
            "MISTRAL_API_KEY",
            "MISTRAL_MODEL_ID",
            "WRITER_API_KEY",
            "LLAMA_API_KEY",
            "EXA_API_KEY",
        ],
        "auth_tools": ["create_harness", "use_skill", "graph", "swarm", "workflow", "web_search"],
    },
    "strands_docs_mcp": {
        "title": "Strands Document MCP Server",
        "env_vars": ["STRANDS_DOCS_LLMS_TXT_URL"],
        "auth_tools": ["search_docs", "fetch_doc"],
    },
    "agentskills": {
        "title": "Strands Agent Skills (Pattern #2 skill & Pattern #3 use_skill)",
        "env_vars": ["STRANDS_SKILLS_DIR"],
        "auth_tools": ["skill", "use_skill", "configure_skill_tools"],
    },
    "strands_ccxt": {
        "title": "Strands CCXT Cryptocurrency Exchange Suite",
        "env_vars": [
            "CCXT_EXCHANGE_ID",
            "CCXT_API_KEY",
            "CCXT_SECRET",
            "CCXT_PASSWORD",
            "CCXT_UID",
        ],
        "auth_tools": ["use_ccxt"],
    },
    "strands_inspect": {
        "title": "Strands Inspect & KernelSandbox",
        "env_vars": ["STRANDS_INSPECT_ALLOW_EXEC"],
        "auth_tools": ["inspect_tool"],
    },
    "strands_ecosystem": {
        "title": "Strands.my Ecosystem Tools (Cloudflare, HackerOne, Olostep, Apify, UCP, ERC8004)",
        "env_vars": [
            "CLOUDFLARE_API_TOKEN",
            "CLOUDFLARE_ACCOUNT_ID",
            "HACKERONE_API_USERNAME",
            "HACKERONE_API_TOKEN",
            "OLOSTEP_API_KEY",
            "APIFY_API_TOKEN",
            "STIGMER_API_KEY",
            "SQL_DATABASE_URL",
        ],
        "auth_tools": ["strands_auth_status", "strands_configure_credentials"],
    },
}


def get_auth_status(domain: str | None = None) -> dict[str, object]:
    """Return non-sensitive credential configuration status across all Strands domains."""
    domains: Mapping[str, CredentialSchemaEntry] = (
        {domain: CREDENTIAL_SCHEMAS[domain]}
        if domain and domain in CREDENTIAL_SCHEMAS
        else CREDENTIAL_SCHEMAS
    )
    rows: list[dict[str, object]] = []
    for key, meta in domains.items():
        env_vars = meta["env_vars"]
        configured = [var for var in env_vars if bool(os.environ.get(var))]
        missing = [var for var in env_vars if not os.environ.get(var)]
        rows.append(
            {
                "domain": key,
                "title": meta["title"],
                "configured_count": len(configured),
                "total_vars": len(env_vars),
                "configured_vars": ", ".join(configured) if configured else "none",
                "missing_vars": ", ".join(missing) if missing else "none",
                "status": "ready" if configured or not env_vars else "unconfigured",
                "auth_tools": ", ".join(meta["auth_tools"]),
            }
        )
    return {
        "rows": rows,
        "meta": {"total_domains": len(rows)},
    }


def configure_strands_credentials(
    env_var: str,
    value: str,
) -> dict[str, object]:
    """Set a credential environment variable in the current server process (without echoing secret values)."""
    allowed = {var for meta in CREDENTIAL_SCHEMAS.values() for var in meta["env_vars"]}
    if env_var not in allowed and not env_var.startswith(("STRANDS_", "GOOGLE_", "CCXT_", "TELEGRAM_", "AWS_")):
        raise ValueError(f"Unsupported credential variable {env_var!r}.")
    os.environ[env_var] = value
    return {
        "status": "configured",
        "env_var": env_var,
        "is_set": bool(os.environ.get(env_var)),
    }


def _is_str_mapping(val: object) -> TypeGuard[Mapping[str, object]]:
    return isinstance(val, Mapping)


def _is_obj_sequence(val: object) -> TypeGuard[Sequence[object]]:
    return isinstance(val, Sequence) and not isinstance(val, (str, bytes))


def build_auth(
    spec: Mapping[str, object] | None = None,
    *,
    base_url: str,
    client_id: str,
    client_secret: str,
    jwt_signing_key: str,
    allowed_client_redirect_uris: list[str],
    http_client: httpx2.AsyncClient | None = None,
    client_storage: AsyncKeyValue | None = None,
    authorization_url: str = "https://accounts.google.com/o/oauth2/v2/auth",
    token_url: str = "https://oauth2.googleapis.com/token",
    introspection_url: str = "https://oauth2.googleapis.com/tokeninfo",
    scopes: list[str] | None = None,
) -> OAuthProxy:
    """Build a FastMCP OAuthProxy for multi-tenant MCP client authentication."""
    if spec and "oauth_endpoints" in spec:
        ep = spec["oauth_endpoints"]
        if _is_str_mapping(ep):
            auth_ep = ep.get("authorization_url")
            if isinstance(auth_ep, str):
                authorization_url = auth_ep
            tok_ep = ep.get("token_url")
            if isinstance(tok_ep, str):
                token_url = tok_ep
            intro_ep = ep.get("introspection_url")
            if isinstance(intro_ep, str):
                introspection_url = intro_ep
            raw_scopes = ep.get("scopes")
            if _is_obj_sequence(raw_scopes):
                scopes = [str(s) for s in raw_scopes]

    verifier = IntrospectionTokenVerifier(
        introspection_url=introspection_url,
        client_id=client_id,
        client_secret=client_secret,
        client_auth_method="client_secret_basic",
        http_client=http_client,
        cache_ttl_seconds=INTROSPECTION_CACHE_TTL_SECONDS,
    )
    return OAuthProxy(
        upstream_authorization_endpoint=authorization_url,
        upstream_token_endpoint=token_url,
        upstream_client_id=client_id,
        upstream_client_secret=client_secret,
        token_verifier=verifier,
        base_url=base_url,
        valid_scopes=scopes or ["openid", "email", "profile"],
        allowed_client_redirect_uris=allowed_client_redirect_uris,
        jwt_signing_key=jwt_signing_key,
        require_authorization_consent=True,
        client_storage=client_storage,
    )
