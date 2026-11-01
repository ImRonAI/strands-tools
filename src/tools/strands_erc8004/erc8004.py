"""
🤖 ERC-8004: Trustless Agents Protocol Tool
============================================
On-chain agent identity, reputation, and validation for the agentic web.

Based on: https://eips.ethereum.org/EIPS/eip-8004
Website: https://www.8004.org/
Repo: https://github.com/erc-8004/erc-8004

Uses the OFFICIAL deployed contracts and ABIs from the erc-8004 repo.
Contracts are UUPS upgradeable proxies deployed as per-chain singletons.

Three registries:
  1. Identity Registry  - ERC-721 agent handles with metadata
  2. Reputation Registry - Feedback signals (on-chain + off-chain)
  3. Validation Registry - Third-party verification (zkML, TEE, re-execution)
"""

import json
import time
import base64
import hashlib
import tempfile
import os
import urllib.request
from pathlib import Path
from strands import tool

# ─── Data directory ───
DATA_DIR = Path(
    os.environ.get(
        "ERC8004_DATA_DIR",
        str(Path(tempfile.gettempdir()) / "strands_erc8004"),
    )
)
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Wallets directory (shared with blockchain.py)
WALLETS_DIR = DATA_DIR / "wallets"
WALLETS_DIR.mkdir(parents=True, exist_ok=True)

# Local deployment overrides (for local/hardhat chains)
STATE_FILE = DATA_DIR / "deployments.json"

# ═══════════════════════════════════════════════════════
# OFFICIAL DEPLOYED CONTRACT ADDRESSES
# From: https://github.com/erc-8004/erc-8004/blob/main/README.md
# ═══════════════════════════════════════════════════════

# Mainnet addresses (same across all mainnets via CREATE2 vanity deploy)
MAINNET_IDENTITY = "0x8004A169FB4a3325136EB29fA0ceB6D2e539a432"
MAINNET_REPUTATION = "0x8004BAa17C55a88189AE136b182e5fdA19dE9b63"

# Testnet addresses (same across all testnets)
TESTNET_IDENTITY = "0x8004A818BFB912233c491871b3d84c89A494BD9e"
TESTNET_REPUTATION = "0x8004B663056A597Dffe9eCcC1965A193B7388713"

# Chain → (identity_address, reputation_address, is_testnet)
DEPLOYED_REGISTRIES = {
    # ── Mainnets ──
    "ethereum": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "base": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "polygon": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "arbitrum": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "celo": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "gnosis": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "scroll": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "taiko": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "monad": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "bsc": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    "optimism": (MAINNET_IDENTITY, MAINNET_REPUTATION, False),
    # ── Testnets ──
    "sepolia": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "base_sepolia": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "amoy": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "arbitrum_sepolia": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "celo_testnet": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "scroll_testnet": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "monad_testnet": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
    "bsc_testnet": (TESTNET_IDENTITY, TESTNET_REPUTATION, True),
}

# Chain → RPC URL
CHAIN_RPCS = {
    # Mainnets
    "ethereum": "https://ethereum-rpc.publicnode.com",
    "base": "https://base-rpc.publicnode.com",
    "polygon": "https://polygon-bor-rpc.publicnode.com",
    "arbitrum": "https://arbitrum-one-rpc.publicnode.com",
    "celo": "https://celo-rpc.publicnode.com",
    "gnosis": "https://gnosis-rpc.publicnode.com",
    "scroll": "https://scroll-rpc.publicnode.com",
    "taiko": "https://rpc.mainnet.taiko.xyz",
    "bsc": "https://bsc-rpc.publicnode.com",
    "optimism": "https://optimism-rpc.publicnode.com",
    # Testnets
    "sepolia": "https://ethereum-sepolia-rpc.publicnode.com",
    "base_sepolia": "https://base-sepolia-rpc.publicnode.com",
    "amoy": "https://rpc-amoy.polygon.technology",
    "arbitrum_sepolia": "https://arbitrum-sepolia-rpc.publicnode.com",
    "bsc_testnet": "https://bsc-testnet-rpc.publicnode.com",
}

# ═══════════════════════════════════════════════════════
# OFFICIAL ABIs (loaded from repo or embedded minimal)
# ═══════════════════════════════════════════════════════

_ABI_DIR = Path(__file__).parent.parent / "erc-8004" / "abis"
_abi_cache = {}


def _load_abi(name: str) -> list:
    """Load official ABI from the cloned erc-8004 repo, or use embedded minimal ABI."""
    if name in _abi_cache:
        return _abi_cache[name]

    # Try loading from cloned repo
    abi_file = _ABI_DIR / f"{name}.json"
    if abi_file.exists():
        with open(abi_file) as f:
            abi = json.load(f)
        _abi_cache[name] = abi
        return abi

    # Also check relative to DATA_DIR (if user cloned elsewhere)
    alt_abi = DATA_DIR / "abis" / f"{name}.json"
    if alt_abi.exists():
        with open(alt_abi) as f:
            abi = json.load(f)
        _abi_cache[name] = abi
        return abi

    # Fallback: embedded minimal ABIs for the functions we actually call
    # These are extracted from the official ABIs
    if name == "IdentityRegistry":
        abi = _MINIMAL_IDENTITY_ABI
    elif name == "ReputationRegistry":
        abi = _MINIMAL_REPUTATION_ABI
    elif name == "ValidationRegistry":
        abi = _MINIMAL_VALIDATION_ABI
    else:
        raise ValueError(f"Unknown ABI: {name}")

    _abi_cache[name] = abi
    return abi


# Minimal ABIs — only the functions we call (fallback if repo not cloned)
_MINIMAL_IDENTITY_ABI = [
    {
        "inputs": [],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "agentURI", "type": "string"}],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "string", "name": "agentURI", "type": "string"},
            {
                "components": [
                    {"internalType": "string", "name": "metadataKey", "type": "string"},
                    {"internalType": "bytes", "name": "metadataValue", "type": "bytes"},
                ],
                "internalType": "struct IdentityRegistryUpgradeable.MetadataEntry[]",
                "name": "metadata",
                "type": "tuple[]",
            },
        ],
        "name": "register",
        "outputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getAgentWallet",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "metadataKey", "type": "string"},
        ],
        "name": "getMetadata",
        "outputs": [{"internalType": "bytes", "name": "", "type": "bytes"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "metadataKey", "type": "string"},
            {"internalType": "bytes", "name": "metadataValue", "type": "bytes"},
        ],
        "name": "setMetadata",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "newURI", "type": "string"},
        ],
        "name": "setAgentURI",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "newWallet", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "setAgentWallet",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "unsetAgentWallet",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "address", "name": "owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "name",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "symbol",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getVersion",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "pure",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "uint256",
                "name": "agentId",
                "type": "uint256",
            },
            {
                "indexed": False,
                "internalType": "string",
                "name": "agentURI",
                "type": "string",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "owner",
                "type": "address",
            },
        ],
        "name": "Registered",
        "type": "event",
    },
]

_MINIMAL_REPUTATION_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "int128", "name": "value", "type": "int128"},
            {"internalType": "uint8", "name": "valueDecimals", "type": "uint8"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "string", "name": "endpoint", "type": "string"},
            {"internalType": "string", "name": "feedbackURI", "type": "string"},
            {"internalType": "bytes32", "name": "feedbackHash", "type": "bytes32"},
        ],
        "name": "giveFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
        ],
        "name": "revokeFeedback",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
        ],
        "name": "readFeedback",
        "outputs": [
            {"internalType": "int128", "name": "value", "type": "int128"},
            {"internalType": "uint8", "name": "valueDecimals", "type": "uint8"},
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "bool", "name": "isRevoked", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {
                "internalType": "address[]",
                "name": "clientAddresses",
                "type": "address[]",
            },
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
        ],
        "name": "getSummary",
        "outputs": [
            {"internalType": "uint64", "name": "count", "type": "uint64"},
            {"internalType": "int128", "name": "summaryValue", "type": "int128"},
            {"internalType": "uint8", "name": "summaryValueDecimals", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {
                "internalType": "address[]",
                "name": "clientAddresses",
                "type": "address[]",
            },
            {"internalType": "string", "name": "tag1", "type": "string"},
            {"internalType": "string", "name": "tag2", "type": "string"},
            {"internalType": "bool", "name": "includeRevoked", "type": "bool"},
        ],
        "name": "readAllFeedback",
        "outputs": [
            {"internalType": "address[]", "name": "clients", "type": "address[]"},
            {"internalType": "uint64[]", "name": "feedbackIndexes", "type": "uint64[]"},
            {"internalType": "int128[]", "name": "values", "type": "int128[]"},
            {"internalType": "uint8[]", "name": "valueDecimals", "type": "uint8[]"},
            {"internalType": "string[]", "name": "tag1s", "type": "string[]"},
            {"internalType": "string[]", "name": "tag2s", "type": "string[]"},
            {"internalType": "bool[]", "name": "revokedStatuses", "type": "bool[]"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getClients",
        "outputs": [{"internalType": "address[]", "name": "", "type": "address[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
        ],
        "name": "getLastIndex",
        "outputs": [{"internalType": "uint64", "name": "", "type": "uint64"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "address", "name": "clientAddress", "type": "address"},
            {"internalType": "uint64", "name": "feedbackIndex", "type": "uint64"},
            {"internalType": "string", "name": "responseURI", "type": "string"},
            {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
        ],
        "name": "appendResponse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getIdentityRegistry",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getVersion",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "pure",
        "type": "function",
    },
]

_MINIMAL_VALIDATION_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"},
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "string", "name": "requestURI", "type": "string"},
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"},
        ],
        "name": "validationRequest",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"},
            {"internalType": "uint8", "name": "response", "type": "uint8"},
            {"internalType": "string", "name": "responseURI", "type": "string"},
            {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
            {"internalType": "string", "name": "tag", "type": "string"},
        ],
        "name": "validationResponse",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "requestHash", "type": "bytes32"}
        ],
        "name": "getValidationStatus",
        "outputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"},
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {"internalType": "uint8", "name": "response", "type": "uint8"},
            {"internalType": "bytes32", "name": "responseHash", "type": "bytes32"},
            {"internalType": "string", "name": "tag", "type": "string"},
            {"internalType": "uint256", "name": "lastUpdate", "type": "uint256"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "agentId", "type": "uint256"},
            {
                "internalType": "address[]",
                "name": "validatorAddresses",
                "type": "address[]",
            },
            {"internalType": "string", "name": "tag", "type": "string"},
        ],
        "name": "getSummary",
        "outputs": [
            {"internalType": "uint64", "name": "count", "type": "uint64"},
            {"internalType": "uint8", "name": "avgResponse", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "agentId", "type": "uint256"}],
        "name": "getAgentValidations",
        "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "validatorAddress", "type": "address"}
        ],
        "name": "getValidatorRequests",
        "outputs": [{"internalType": "bytes32[]", "name": "", "type": "bytes32[]"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getIdentityRegistry",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getVersion",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "pure",
        "type": "function",
    },
]


# ═══════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════


def _load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def _save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _get_web3(chain="local", rpc_url=None):
    from web3 import Web3

    if rpc_url:
        return Web3(Web3.HTTPProvider(rpc_url))
    url = CHAIN_RPCS.get(chain, "http://127.0.0.1:8545")
    return Web3(Web3.HTTPProvider(url))


def _get_account(w3, wallet_name=None, private_key=None):
    if private_key:
        return w3.eth.account.from_key(private_key)
    if wallet_name:
        # Search order: CWD/wallets → DATA_DIR/wallets
        search_paths = [
            Path.cwd() / "wallets" / f"{wallet_name}.json",
            WALLETS_DIR / f"{wallet_name}.json",
        ]
        for wf in search_paths:
            if wf.exists():
                with open(wf) as f:
                    data = json.load(f)
                return w3.eth.account.from_key(data["private_key"])
        raise ValueError(
            f"Wallet '{wallet_name}' not found in {[str(p.parent) for p in search_paths]}"
        )
    # Default Anvil/Hardhat account
    return w3.eth.account.from_key(
        "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
    )


def _resolve_addresses(
    chain,
    rpc_url,
    identity_address=None,
    reputation_address=None,
    validation_address=None,
):
    """Resolve contract addresses: explicit > deployed registry > local state."""
    chain_key = chain if not rpc_url else rpc_url

    # Start with official deployed addresses
    if chain in DEPLOYED_REGISTRIES:
        deployed_id, deployed_rep, _ = DEPLOYED_REGISTRIES[chain]
        id_addr = identity_address or deployed_id
        rep_addr = reputation_address or deployed_rep
        val_addr = validation_address  # Validation not yet deployed on public chains
    else:
        # Check local state (for hardhat/local deployments)
        state = _load_state()
        local = state.get(chain_key, {})
        id_addr = identity_address or local.get("identity")
        rep_addr = reputation_address or local.get("reputation")
        val_addr = validation_address or local.get("validation")

    return id_addr, rep_addr, val_addr


def _get_contract(w3, address, abi_name):
    abi = _load_abi(abi_name)
    return w3.eth.contract(address=w3.to_checksum_address(address), abi=abi)


def _send_tx(w3, account, contract_fn, value=0):
    """Send a transaction with proper gas estimation."""
    # Estimate gas first (prevents wasted gas on reverts)
    try:
        estimated_gas = contract_fn.estimate_gas(
            {"from": account.address, "value": value}
        )
        gas_limit = int(estimated_gas * 1.2)  # 20% buffer
    except Exception as e:
        # If estimate fails, the tx would revert — raise early with useful message
        raise ValueError(f"Transaction would revert: {e}")

    tx = contract_fn.build_transaction(
        {
            "from": account.address,
            "nonce": w3.eth.get_transaction_count(account.address),
            "gas": gas_limit,
            "gasPrice": w3.eth.gas_price,
            "value": value,
        }
    )
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
    if receipt.status == 0:
        raise ValueError(f"Transaction reverted (tx: {tx_hash.hex()})")
    return receipt


def _parse_bytes32(hex_str):
    if not hex_str:
        return b"\x00" * 32
    if hex_str.startswith("0x"):
        hex_str = hex_str[2:]
    try:
        raw = bytes.fromhex(hex_str)
    except ValueError:
        return b"\x00" * 32
    if len(raw) < 32:
        raw = raw + b"\x00" * (32 - len(raw))
    return raw[:32]


def _fetch_uri(uri, timeout=10):
    """Fetch a URI (https, ipfs, data:) and return parsed JSON or raw text."""
    try:
        if uri.startswith("data:"):
            # data:application/json;base64,...
            if ";base64," in uri:
                b64 = uri.split(";base64,", 1)[1]
                return json.loads(base64.b64decode(b64).decode())
            else:
                data_part = uri.split(",", 1)[1]
                return json.loads(data_part)
        elif uri.startswith("ipfs://"):
            cid = uri.replace("ipfs://", "")
            url = f"https://ipfs.io/ipfs/{cid}"
            req = urllib.request.Request(
                url, headers={"User-Agent": "strands-erc8004/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        elif uri.startswith("http"):
            req = urllib.request.Request(
                uri, headers={"User-Agent": "strands-erc8004/1.0"}
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode())
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════
# LOCAL DEPLOYMENT (for hardhat/local only)
# Uses the original Solidity from the cloned repo
# ═══════════════════════════════════════════════════════


def _compile_and_deploy(w3, account, source_code, contract_name, constructor_args=None):
    """Compile and deploy using the original contracts from the cloned repo."""
    from solcx import compile_files, install_solc

    install_solc("0.8.20", show_progress=False)

    # Find node_modules
    cwd = Path.cwd()
    node_modules = None
    for search_dir in [cwd, cwd.parent, Path(__file__).parent.parent]:
        candidate = search_dir / "node_modules" / "@openzeppelin"
        if candidate.exists():
            node_modules = search_dir / "node_modules"
            break

    if not node_modules:
        raise ValueError(
            "OpenZeppelin contracts not found. Run: npm install @openzeppelin/contracts-upgradeable@^5.0.0 @openzeppelin/contracts@^5.0.0"
        )

    project_dir = node_modules.parent
    tmp_sol = project_dir / f"_tmp_{contract_name}.sol"
    tmp_sol.write_text(source_code)

    try:
        compiled = compile_files(
            [str(tmp_sol)],
            output_values=["abi", "bin"],
            solc_version="0.8.20",
            base_path=str(project_dir),
            include_path=str(node_modules),
            optimize=True,
            optimize_runs=200,
            via_ir=True,
        )
    finally:
        tmp_sol.unlink(missing_ok=True)

    contract_key = None
    for key in compiled:
        if key.endswith(f":{contract_name}"):
            contract_key = key
            break

    if not contract_key:
        available = [k.split(":")[-1] for k in compiled]
        raise ValueError(
            f"Contract '{contract_name}' not found. Available: {available}"
        )

    abi = compiled[contract_key]["abi"]
    bytecode = compiled[contract_key]["bin"]

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    if constructor_args:
        tx = contract.constructor(*constructor_args).build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 8_000_000,
                "gasPrice": w3.eth.gas_price,
            }
        )
    else:
        tx = contract.constructor().build_transaction(
            {
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 8_000_000,
                "gasPrice": w3.eth.gas_price,
            }
        )

    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return receipt.contractAddress, abi, receipt


# ═══════════════════════════════════════════════════════
# MAIN TOOL
# ═══════════════════════════════════════════════════════


@tool
def erc8004(
    action: str,
    chain: str = "base",
    rpc_url: str = None,
    wallet_name: str = None,
    private_key: str = None,
    # Identity
    agent_uri: str = None,
    agent_id: int = None,
    metadata_key: str = None,
    metadata_value: str = None,
    new_uri: str = None,
    # Reputation
    value: int = None,
    value_decimals: int = 0,
    tag1: str = "",
    tag2: str = "",
    endpoint: str = "",
    feedback_uri: str = "",
    feedback_hash: str = None,
    client_address: str = None,
    feedback_index: int = None,
    client_addresses: list = None,
    include_revoked: bool = False,
    # Validation
    validator_address: str = None,
    request_uri: str = "",
    request_hash: str = None,
    response_code: int = None,
    response_uri: str = "",
    response_hash: str = None,
    tag: str = "",
    # Registration file
    agent_name: str = None,
    description: str = None,
    image_url: str = None,
    services: list = None,
    supported_trust: list = None,
    # Contract overrides (for custom deployments)
    identity_address: str = None,
    reputation_address: str = None,
    validation_address: str = None,
    # Discovery
    max_agents: int = 50,
    fetch_metadata: bool = True,
) -> dict:
    """
    🤖 ERC-8004: Trustless Agents Protocol — on-chain agent identity, reputation & validation.

    Uses OFFICIAL deployed contracts on 10+ EVM chains. No modified contracts.

    Deployed chains: ethereum, base, polygon, arbitrum, celo, gnosis, scroll, taiko, monad, bsc
    Testnets: sepolia, base_sepolia, amoy, arbitrum_sepolia, bsc_testnet

    Actions:
      Discovery (READ-ONLY, no wallet needed):
        discover_agents     - Browse all registered agents on a public chain
        get_agent           - Get agent identity by ID
        get_reputation      - Get aggregated reputation for an agent
        get_clients         - Get all clients who gave feedback
        read_feedback       - Read specific feedback entry
        read_all_feedback   - Read all feedback for an agent
        total_agents        - Get total registered agents count
        resolve_agent       - Find agents by owner address
        status              - Show deployment status for a chain

      Identity (WRITE, needs wallet):
        register_agent      - Register a new agent (mint ERC-721 identity)
        update_agent        - Update agent URI or metadata
        set_agent_wallet    - Set verified payment wallet

      Reputation (WRITE, needs wallet):
        give_feedback       - Submit feedback for an agent
        revoke_feedback     - Revoke previously given feedback

      Validation (WRITE, needs wallet):
        request_validation  - Request validation of agent's work
        submit_validation   - Submit validation result

      Utility:
        create_registration_file - Generate ERC-8004 registration JSON

      Local deployment (for hardhat/local dev only):
        deploy_all          - Deploy all three registries locally

    Examples:
        erc8004(action="discover_agents", chain="base")
        erc8004(action="discover_agents", chain="ethereum", max_agents=20)
        erc8004(action="get_agent", agent_id=0, chain="base")
        erc8004(action="get_reputation", agent_id=0, chain="base")
        erc8004(action="register_agent", agent_uri="https://example.com/agent.json", chain="sepolia", wallet_name="dev")
        erc8004(action="give_feedback", agent_id=0, value=95, tag1="starred", chain="sepolia", wallet_name="dev")
    """
    try:
        id_addr, rep_addr, val_addr = _resolve_addresses(
            chain, rpc_url, identity_address, reputation_address, validation_address
        )

        # ==========================================
        # DISCOVERY / READ-ONLY ACTIONS
        # ==========================================

        if action == "discover_agents":
            w3 = _get_web3(chain, rpc_url)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry deployed on {chain}"}],
                }

            contract = _get_contract(w3, id_addr, "IdentityRegistry")

            # Use Registered event logs for efficient discovery (no O(n) probing)
            agents = []
            try:
                # Get all Registered events — much faster than probing ownerOf
                registered_events = contract.events.Registered().get_logs(from_block=0)
                agent_ids = [e["args"]["agentId"] for e in registered_events]
                # Deduplicate and take last max_agents
                agent_ids = list(dict.fromkeys(agent_ids))[-max_agents:]
            except Exception:
                # Fallback to sequential probing if event logs fail (some RPCs limit this)
                agent_ids = []
                miss = 0
                for i in range(max_agents + 50):
                    if len(agent_ids) >= max_agents:
                        break
                    try:
                        contract.functions.ownerOf(i).call()
                        agent_ids.append(i)
                        miss = 0
                    except Exception:
                        miss += 1
                        if miss > 5:
                            break

            for aid in agent_ids:
                try:
                    owner = contract.functions.ownerOf(aid).call()
                    uri = ""
                    try:
                        uri = contract.functions.tokenURI(aid).call()
                    except Exception:
                        pass

                    wallet = None
                    try:
                        wallet = contract.functions.getAgentWallet(aid).call()
                    except Exception:
                        pass

                    agent_info = {
                        "agentId": aid,
                        "owner": owner,
                        "uri": uri,
                        "wallet": wallet,
                    }

                    # Optionally fetch registration file metadata
                    if fetch_metadata and uri:
                        reg_file = _fetch_uri(uri)
                        if reg_file and isinstance(reg_file, dict):
                            agent_info["name"] = reg_file.get("name", "")
                            agent_info["description"] = reg_file.get("description", "")[
                                :200
                            ]
                            agent_info["services"] = [
                                s.get("name", "") for s in reg_file.get("services", [])
                            ]
                            agent_info["active"] = reg_file.get("active", True)
                            agent_info["supportedTrust"] = reg_file.get(
                                "supportedTrust", []
                            )

                    agents.append(agent_info)
                except Exception:
                    continue

            if not agents:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"🤖 No agents found on {chain}\n"
                            f"   Identity Registry: {id_addr}\n"
                            f"   Chain may be new or agents not yet registered."
                        }
                    ],
                }

            # Format output
            lines = [f"🤖 Discovered {len(agents)} agent(s) on {chain}:"]
            lines.append(f"   Identity Registry: {id_addr}\n")

            for a in agents:
                lines.append(f"  ── Agent #{a['agentId']} ──")
                lines.append(f"     Owner: {a['owner']}")
                if a.get("name"):
                    lines.append(f"     Name: {a['name']}")
                if a.get("description"):
                    lines.append(f"     Desc: {a['description']}")
                if a.get("uri"):
                    lines.append(f"     URI: {a['uri'][:120]}")
                if a.get("wallet") and a["wallet"] != "0x" + "0" * 40:
                    lines.append(f"     Wallet: {a['wallet']}")
                if a.get("services"):
                    lines.append(f"     Services: {', '.join(a['services'])}")
                if a.get("supportedTrust"):
                    lines.append(f"     Trust: {', '.join(a['supportedTrust'])}")
                lines.append("")

            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        elif action == "get_agent":
            w3 = _get_web3(chain, rpc_url)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry on {chain}"}],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")

            owner = contract.functions.ownerOf(agent_id).call()
            uri = ""
            try:
                uri = contract.functions.tokenURI(agent_id).call()
            except Exception:
                pass
            wallet = None
            try:
                wallet = contract.functions.getAgentWallet(agent_id).call()
            except Exception:
                pass

            text = (
                f"🤖 Agent #{agent_id} on {chain}\n"
                f"   Owner: {owner}\n"
                f"   URI: {uri}\n"
                f"   Wallet: {wallet or 'not set'}"
            )

            # Fetch registration file
            if fetch_metadata and uri:
                reg = _fetch_uri(uri)
                if reg and isinstance(reg, dict):
                    text += f"\n\n   📄 Registration File:\n"
                    text += f"   Name: {reg.get('name', '?')}\n"
                    text += f"   Description: {reg.get('description', '?')[:300]}\n"
                    for svc in reg.get("services", []):
                        text += f"   Service: {svc.get('name', '?')} → {svc.get('endpoint', '?')[:80]}\n"
                    text += f"   Active: {reg.get('active', '?')}\n"
                    text += f"   Trust: {reg.get('supportedTrust', [])}"

            return {"status": "success", "content": [{"text": text}]}

        elif action == "total_agents":
            w3 = _get_web3(chain, rpc_url)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry on {chain}"}],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")
            # Use Registered event logs to count agents efficiently
            try:
                registered_events = contract.events.Registered().get_logs(from_block=0)
                total = len(set(e["args"]["agentId"] for e in registered_events))
            except Exception:
                # Fallback to probing
                total = 0
                miss = 0
                for i in range(10000):
                    try:
                        contract.functions.ownerOf(i).call()
                        total = i + 1
                        miss = 0
                    except Exception:
                        miss += 1
                        if miss > 5:
                            break
            return {
                "status": "success",
                "content": [{"text": f"📊 {total} registered agents on {chain}"}],
            }

        elif action == "resolve_agent":
            w3 = _get_web3(chain, rpc_url)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry on {chain}"}],
                }
            if not client_address:
                return {
                    "status": "error",
                    "content": [{"text": "resolve_agent requires 'client_address'"}],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")
            target = w3.to_checksum_address(client_address)

            # Use event logs to find agents by owner (works for any agent ID)
            found = []
            try:
                registered_events = contract.events.Registered().get_logs(from_block=0)
                candidate_ids = [
                    e["args"]["agentId"]
                    for e in registered_events
                    if e["args"].get("owner", "").lower() == target.lower()
                ]
                # Also check current ownership (transfers may have happened)
                for aid in candidate_ids:
                    try:
                        owner = contract.functions.ownerOf(aid).call()
                        if owner.lower() == target.lower():
                            uri = ""
                            try:
                                uri = contract.functions.tokenURI(aid).call()
                            except Exception:
                                pass
                            found.append(f"  #{aid} | URI: {uri[:80]}")
                    except Exception:
                        continue
            except Exception:
                # Fallback: check balanceOf first, then probe
                try:
                    balance = contract.functions.balanceOf(target).call()
                    if balance == 0:
                        return {
                            "status": "success",
                            "content": [
                                {
                                    "text": f"🔍 No agents found for {target} on {chain} (balance: 0)"
                                }
                            ],
                        }
                except Exception:
                    pass

            if found:
                return {
                    "status": "success",
                    "content": [
                        {
                            "text": f"🔍 Agents owned by {target} on {chain}:\n"
                            + "\n".join(found)
                        }
                    ],
                }
            return {
                "status": "success",
                "content": [{"text": f"🔍 No agents found for {target} on {chain}"}],
            }

        elif action == "get_reputation":
            w3 = _get_web3(chain, rpc_url)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")

            # Get clients first if not provided
            addrs = [w3.to_checksum_address(a) for a in (client_addresses or [])]
            if not addrs:
                try:
                    addrs = contract.functions.getClients(agent_id).call()
                except Exception:
                    pass

            if not addrs:
                return {
                    "status": "success",
                    "content": [
                        {"text": f"📊 Agent #{agent_id} on {chain}: No feedback yet"}
                    ],
                }

            count, avg, decimals = contract.functions.getSummary(
                agent_id, addrs, tag1, tag2
            ).call()

            # Format value with decimals
            if decimals > 0:
                display_val = avg / (10**decimals)
            else:
                display_val = avg

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"📊 Agent #{agent_id} Reputation on {chain}:\n"
                        f"   Feedback count: {count}\n"
                        f"   Average value: {display_val} (decimals: {decimals})\n"
                        f"   Clients: {len(addrs)}"
                    }
                ],
            }

        elif action == "get_clients":
            w3 = _get_web3(chain, rpc_url)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")
            clients = contract.functions.getClients(agent_id).call()
            return {
                "status": "success",
                "content": [
                    {
                        "text": (
                            f"👥 Agent #{agent_id} clients on {chain} ({len(clients)}):\n"
                            + "\n".join(f"  {c}" for c in clients)
                            if clients
                            else f"No clients yet for agent #{agent_id}"
                        )
                    }
                ],
            }

        elif action == "read_feedback":
            w3 = _get_web3(chain, rpc_url)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")
            result = contract.functions.readFeedback(
                agent_id, w3.to_checksum_address(client_address), feedback_index
            ).call()
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"📖 Feedback #{feedback_index} from {client_address[:10]}... for agent #{agent_id} on {chain}:\n"
                        f"   Value: {result[0]} (decimals: {result[1]})\n"
                        f"   Tag1: {result[2]}\n"
                        f"   Tag2: {result[3]}\n"
                        f"   Revoked: {result[4]}"
                    }
                ],
            }

        elif action == "read_all_feedback":
            w3 = _get_web3(chain, rpc_url)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")

            addrs = [w3.to_checksum_address(a) for a in (client_addresses or [])]
            result = contract.functions.readAllFeedback(
                agent_id, addrs, tag1, tag2, include_revoked
            ).call()

            clients, indexes, values, decimals, tag1s, tag2s, revoked = result
            if not clients:
                return {
                    "status": "success",
                    "content": [
                        {"text": f"No feedback for agent #{agent_id} on {chain}"}
                    ],
                }

            lines = [
                f"📋 All feedback for agent #{agent_id} on {chain} ({len(clients)} entries):"
            ]
            for i in range(len(clients)):
                dec = decimals[i]
                val = values[i] / (10**dec) if dec > 0 else values[i]
                rev = " [REVOKED]" if revoked[i] else ""
                lines.append(
                    f"  #{indexes[i]} from {clients[i][:10]}... | "
                    f"value={val} | {tag1s[i]}/{tag2s[i]}{rev}"
                )
            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        # ==========================================
        # IDENTITY WRITE ACTIONS
        # ==========================================

        elif action == "register_agent":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"No Identity Registry on {chain}. Use deploy_all for local."
                        }
                    ],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")

            uri = agent_uri or ""
            if uri:
                receipt = _send_tx(w3, account, contract.functions.register(uri))
            else:
                receipt = _send_tx(w3, account, contract.functions.register())

            # Parse agentId from Registered event
            agent_id_result = "?"
            for log in receipt.logs:
                try:
                    parsed = contract.events.Registered().process_log(log)
                    agent_id_result = parsed["args"]["agentId"]
                    break
                except Exception:
                    continue

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Agent registered on {chain}!\n"
                        f"   Agent ID: {agent_id_result}\n"
                        f"   Owner: {account.address}\n"
                        f"   URI: {uri or '(bare - set later)'}\n"
                        f"   Registry: {id_addr}\n"
                        f"   TX: {receipt.transactionHash.hex()}"
                    }
                ],
            }

        elif action == "update_agent":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry on {chain}"}],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")

            if new_uri:
                _send_tx(w3, account, contract.functions.setAgentURI(agent_id, new_uri))
                return {
                    "status": "success",
                    "content": [
                        {"text": f"✅ Agent #{agent_id} URI updated to: {new_uri}"}
                    ],
                }
            elif metadata_key and metadata_value:
                _send_tx(
                    w3,
                    account,
                    contract.functions.setMetadata(
                        agent_id, metadata_key, metadata_value.encode()
                    ),
                )
                return {
                    "status": "success",
                    "content": [
                        {"text": f"✅ Agent #{agent_id} metadata '{metadata_key}' set"}
                    ],
                }
            else:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "update_agent needs 'new_uri' or 'metadata_key'+'metadata_value'"
                        }
                    ],
                }

        elif action == "set_agent_wallet":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not id_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Identity Registry on {chain}"}],
                }
            contract = _get_contract(w3, id_addr, "IdentityRegistry")

            if not client_address:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": "set_agent_wallet requires 'client_address' (the new wallet address)"
                        }
                    ],
                }

            new_wallet = w3.to_checksum_address(client_address)

            # Build EIP-712 signature for wallet verification
            # The new wallet must sign to prove control
            deadline = int(time.time()) + 3600  # 1 hour from now

            # Get EIP-712 domain from contract
            domain = contract.functions.eip712Domain().call()
            domain_data = {
                "name": domain[1],
                "version": domain[2],
                "chainId": domain[3],
                "verifyingContract": domain[4],
            }

            # Build typed data
            message = {
                "agentId": agent_id,
                "newWallet": new_wallet,
                "deadline": deadline,
            }

            # Sign with the new wallet's key (must be provided as private_key or wallet)
            from eth_account.messages import encode_typed_data

            signable = encode_typed_data(
                domain_data=domain_data,
                message_types={
                    "SetAgentWallet": [
                        {"name": "agentId", "type": "uint256"},
                        {"name": "newWallet", "type": "address"},
                        {"name": "deadline", "type": "uint256"},
                    ]
                },
                message_data=message,
            )
            # The new wallet signs (account is the owner calling, but the sig is from new wallet)
            signed_msg = w3.eth.account.sign_message(signable, private_key=account.key)

            receipt = _send_tx(
                w3,
                account,
                contract.functions.setAgentWallet(
                    agent_id, new_wallet, deadline, signed_msg.signature
                ),
            )

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ Agent #{agent_id} wallet set to {new_wallet}\n"
                        f"   TX: {receipt.transactionHash.hex()}"
                    }
                ],
            }

        # ==========================================
        # REPUTATION WRITE ACTIONS
        # ==========================================

        elif action == "give_feedback":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")

            fb_hash = _parse_bytes32(feedback_hash)
            receipt = _send_tx(
                w3,
                account,
                contract.functions.giveFeedback(
                    agent_id,
                    value,
                    value_decimals,
                    tag1,
                    tag2,
                    endpoint,
                    feedback_uri,
                    fb_hash,
                ),
            )

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"⭐ Feedback submitted on {chain}!\n"
                        f"   Agent: #{agent_id}\n"
                        f"   Value: {value} (decimals: {value_decimals})\n"
                        f"   Tags: {tag1} / {tag2}\n"
                        f"   From: {account.address}\n"
                        f"   TX: {receipt.transactionHash.hex()}"
                    }
                ],
            }

        elif action == "revoke_feedback":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")
            _send_tx(
                w3, account, contract.functions.revokeFeedback(agent_id, feedback_index)
            )
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"🚫 Feedback #{feedback_index} for agent #{agent_id} revoked on {chain}"
                    }
                ],
            }

        elif action == "append_response":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not rep_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Reputation Registry on {chain}"}],
                }
            contract = _get_contract(w3, rep_addr, "ReputationRegistry")
            resp_hash = _parse_bytes32(response_hash)
            receipt = _send_tx(
                w3,
                account,
                contract.functions.appendResponse(
                    agent_id,
                    w3.to_checksum_address(client_address),
                    feedback_index,
                    response_uri,
                    resp_hash,
                ),
            )
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"💬 Response appended on {chain}!\n"
                        f"   Agent: #{agent_id} | Client: {client_address[:12]}... | Index: {feedback_index}\n"
                        f"   TX: {receipt.transactionHash.hex()}"
                    }
                ],
            }

        # ==========================================
        # VALIDATION ACTIONS
        # ==========================================

        elif action == "request_validation":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not val_addr:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"No Validation Registry on {chain}. May not be deployed on public chains yet."
                        }
                    ],
                }
            contract = _get_contract(w3, val_addr, "ValidationRegistry")

            if not request_hash:
                # ERC-8004 spec says keccak256 for request hashes
                req_data = f"{agent_id}:{request_uri}:{int(time.time())}".encode()
                request_hash = w3.keccak(req_data).hex()

            rh_bytes = _parse_bytes32(request_hash)
            receipt = _send_tx(
                w3,
                account,
                contract.functions.validationRequest(
                    w3.to_checksum_address(validator_address),
                    agent_id,
                    request_uri,
                    rh_bytes,
                ),
            )

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"🔍 Validation requested on {chain}!\n"
                        f"   Agent: #{agent_id}\n"
                        f"   Validator: {validator_address}\n"
                        f"   Request Hash: {request_hash}\n"
                        f"   TX: {receipt.transactionHash.hex()}"
                    }
                ],
            }

        elif action == "submit_validation":
            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)
            if not val_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Validation Registry on {chain}"}],
                }
            contract = _get_contract(w3, val_addr, "ValidationRegistry")

            rh_bytes = _parse_bytes32(request_hash)
            resp_hash = _parse_bytes32(response_hash)
            _send_tx(
                w3,
                account,
                contract.functions.validationResponse(
                    rh_bytes, response_code, response_uri, resp_hash, tag
                ),
            )

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"🔍 Validation submitted: {response_code}/100 on {chain}\n"
                        f"   Request: {request_hash}\n"
                        f"   Tag: {tag}"
                    }
                ],
            }

        elif action == "get_validation":
            w3 = _get_web3(chain, rpc_url)
            if not val_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Validation Registry on {chain}"}],
                }
            contract = _get_contract(w3, val_addr, "ValidationRegistry")
            rh_bytes = _parse_bytes32(request_hash)
            result = contract.functions.getValidationStatus(rh_bytes).call()
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"🔍 Validation Status on {chain}:\n"
                        f"   Validator: {result[0]}\n"
                        f"   Agent: #{result[1]}\n"
                        f"   Response: {result[2]}/100\n"
                        f"   Tag: {result[4]}\n"
                        f"   Last Update: {result[5]}"
                    }
                ],
            }

        elif action == "get_agent_validations":
            w3 = _get_web3(chain, rpc_url)
            if not val_addr:
                return {
                    "status": "error",
                    "content": [{"text": f"No Validation Registry on {chain}"}],
                }
            contract = _get_contract(w3, val_addr, "ValidationRegistry")
            hashes = contract.functions.getAgentValidations(agent_id).call()
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"🔍 Agent #{agent_id} validations on {chain} ({len(hashes)}):\n"
                        + "\n".join(f"  {h.hex()}" for h in hashes)
                    }
                ],
            }

        # ==========================================
        # UTILITY
        # ==========================================

        elif action == "create_registration_file":
            reg_file = {
                "type": "https://eips.ethereum.org/EIPS/eip-8004#registration-v1",
                "name": agent_name or "my-agent",
                "description": description or "An autonomous AI agent",
                "image": image_url or "",
                "services": services
                or [
                    {
                        "name": "web",
                        "endpoint": f"https://{agent_name or 'agent'}.example.com/",
                    },
                    {
                        "name": "MCP",
                        "endpoint": f"https://{agent_name or 'agent'}.example.com/mcp",
                        "version": "2025-06-18",
                    },
                ],
                "x402Support": False,
                "active": True,
                "registrations": [],
                "supportedTrust": supported_trust or ["reputation"],
            }

            json_str = json.dumps(reg_file, indent=2)
            b64 = base64.b64encode(json_str.encode()).decode()
            data_uri = f"data:application/json;base64,{b64}"

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"📄 ERC-8004 Registration File:\n\n{json_str}\n\n"
                        f"📎 Data URI (for fully on-chain):\n{data_uri[:200]}..."
                    }
                ],
            }

        elif action == "status":
            lines = [f"📋 ERC-8004 Status for '{chain}':"]

            if chain in DEPLOYED_REGISTRIES:
                d_id, d_rep, is_test = DEPLOYED_REGISTRIES[chain]
                lines.append(f"   Network: {'Testnet' if is_test else 'Mainnet'}")
                lines.append(f"   ✅ Identity: {d_id}")
                lines.append(f"   ✅ Reputation: {d_rep}")
                lines.append(f"   ⏳ Validation: Not yet deployed on public chains")

                # Try to get version
                try:
                    w3 = _get_web3(chain, rpc_url)
                    c = _get_contract(w3, d_id, "IdentityRegistry")
                    ver = c.functions.getVersion().call()
                    lines.append(f"   Version: {ver}")
                    lines.append(f"   Connected: ✅")
                except Exception as e:
                    lines.append(f"   Connected: ❌ ({e})")
            else:
                state = _load_state()
                chain_key = chain if not rpc_url else rpc_url
                local = state.get(chain_key, {})
                for reg_name in ["identity", "reputation", "validation"]:
                    addr = local.get(reg_name, "NOT DEPLOYED")
                    emoji = "✅" if addr != "NOT DEPLOYED" else "❌"
                    lines.append(f"   {emoji} {reg_name.title()}: {addr}")

            lines.append(
                f"\n   Available chains: {', '.join(sorted(DEPLOYED_REGISTRIES.keys()))}"
            )
            return {"status": "success", "content": [{"text": "\n".join(lines)}]}

        # ==========================================
        # LOCAL DEPLOYMENT (hardhat/local only)
        # ==========================================

        elif action == "deploy_all":
            if chain not in ("local", "hardhat") and not rpc_url:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"deploy_all is for local/hardhat only. On {chain}, contracts are already deployed:\n"
                            f"  Identity: {id_addr}\n  Reputation: {rep_addr}"
                        }
                    ],
                }

            w3 = _get_web3(chain, rpc_url)
            account = _get_account(w3, wallet_name, private_key)

            # Check for OZ
            if not (Path.cwd() / "node_modules" / "@openzeppelin").exists():
                import subprocess

                subprocess.run(
                    [
                        "npm",
                        "install",
                        "@openzeppelin/contracts@^5.0.0",
                        "@openzeppelin/contracts-upgradeable@^5.0.0",
                        "--save",
                        "--silent",
                    ],
                    check=True,
                )

            # Read original contract sources from cloned repo
            repo_contracts = Path(__file__).parent.parent / "erc-8004" / "contracts"
            results = []

            # 1. Identity Registry
            id_sol = (repo_contracts / "IdentityRegistryUpgradeable.sol").read_text()
            id_addr_new, id_abi, _ = _compile_and_deploy(
                w3, account, id_sol, "IdentityRegistryUpgradeable"
            )
            # Call initialize() — required for upgradeable contracts
            id_contract = w3.eth.contract(address=id_addr_new, abi=id_abi)
            try:
                _send_tx(w3, account, id_contract.functions.initialize())
            except Exception:
                pass  # May already be initialized
            results.append(f"Identity Registry: {id_addr_new}")

            # 2. Reputation Registry
            rep_sol = (repo_contracts / "ReputationRegistryUpgradeable.sol").read_text()
            rep_addr_new, rep_abi, _ = _compile_and_deploy(
                w3, account, rep_sol, "ReputationRegistryUpgradeable"
            )
            rep_contract = w3.eth.contract(address=rep_addr_new, abi=rep_abi)
            try:
                _send_tx(w3, account, rep_contract.functions.initialize(id_addr_new))
            except Exception:
                pass
            results.append(f"Reputation Registry: {rep_addr_new}")

            # 3. Validation Registry
            val_sol = (repo_contracts / "ValidationRegistryUpgradeable.sol").read_text()
            val_addr_new, val_abi, _ = _compile_and_deploy(
                w3, account, val_sol, "ValidationRegistryUpgradeable"
            )
            val_contract = w3.eth.contract(address=val_addr_new, abi=val_abi)
            try:
                _send_tx(w3, account, val_contract.functions.initialize(id_addr_new))
            except Exception:
                pass
            results.append(f"Validation Registry: {val_addr_new}")

            # Save state
            chain_key = chain if not rpc_url else rpc_url
            state = _load_state()
            state.setdefault(chain_key, {}).update(
                {
                    "identity": id_addr_new,
                    "reputation": rep_addr_new,
                    "validation": val_addr_new,
                }
            )
            _save_state(state)

            return {
                "status": "success",
                "content": [
                    {
                        "text": f"✅ ERC-8004 deployed locally (original contracts)!\n\n"
                        + "\n".join(f"   {r}" for r in results)
                        + f"\n\n   ⚠️ Note: These are implementation contracts, not proxied.\n"
                        f"   For production, use the official deployments on public chains."
                    }
                ],
            }

        else:
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Unknown action: {action}\n\n"
                        "Valid actions:\n"
                        "  Discovery: discover_agents, get_agent, get_reputation, get_clients,\n"
                        "             read_feedback, read_all_feedback, total_agents, resolve_agent, status\n"
                        "  Identity: register_agent, update_agent, set_agent_wallet\n"
                        "  Reputation: give_feedback, revoke_feedback\n"
                        "  Validation: request_validation, submit_validation, get_validation, get_agent_validations\n"
                        "  Utility: create_registration_file\n"
                        "  Local: deploy_all (hardhat/local only)"
                    }
                ],
            }

    except Exception as e:
        return {
            "status": "error",
            "content": [{"text": f"❌ ERC-8004 error: {str(e)}"}],
        }
