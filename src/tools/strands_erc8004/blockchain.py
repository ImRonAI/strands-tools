"""
🔗 Blockchain Dev Tool for Strands Agents (ERC-8004)
Create wallets, deploy contracts, send transactions, invoke functions.
Supports any EVM chain (Ethereum, Polygon, Arbitrum, Base, local Hardhat).
"""

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Dict
from strands import tool

# Lazy imports to avoid startup cost
_web3_mod = None
_solcx_mod = None
_eth_account_mod = None


def _get_web3():
    global _web3_mod
    if _web3_mod is None:
        from web3 import Web3

        _web3_mod = Web3
    return _web3_mod


def _get_solcx():
    global _solcx_mod
    if _solcx_mod is None:
        import solcx

        _solcx_mod = solcx
    return _solcx_mod


def _get_eth_account():
    global _eth_account_mod
    if _eth_account_mod is None:
        from eth_account import Account

        _eth_account_mod = Account
    return _eth_account_mod


# ─── Default RPC endpoints ───
CHAINS = {
    "local": "http://127.0.0.1:8545",
    "hardhat": "http://127.0.0.1:8545",
    "polygon": "https://polygon-rpc.com",
    "mumbai": "https://rpc-mumbai.maticvigil.com",
    "amoy": "https://rpc-amoy.polygon.technology",
    "ethereum": "https://eth.llamarpc.com",
    "sepolia": "https://rpc.sepolia.org",
    "arbitrum": "https://arb1.arbitrum.io/rpc",
    "base": "https://mainnet.base.org",
    "optimism": "https://mainnet.optimism.io",
}

# ─── Base data directory — shares with erc8004 if ERC8004_DATA_DIR is set ───
_DATA_DIR = Path(
    os.environ.get(
        "ERC8004_DATA_DIR", str(Path(tempfile.gettempdir()) / "strands_erc8004")
    )
)

# ─── Keystore directory ───
KEYSTORE_DIR = _DATA_DIR / "wallets"
KEYSTORE_DIR.mkdir(parents=True, exist_ok=True)

# ─── Compiled contracts cache ───
COMPILE_CACHE = _DATA_DIR / "contracts"
COMPILE_CACHE.mkdir(parents=True, exist_ok=True)


def _connect(chain: str = "local", rpc_url: str = None):
    """Get a Web3 connection."""
    Web3 = _get_web3()
    url = rpc_url or os.getenv("BLOCKCHAIN_RPC_URL") or CHAINS.get(chain, chain)
    # If it looks like a URL, use it directly
    if url.startswith("http") or url.startswith("ws"):
        w3 = Web3(
            Web3.HTTPProvider(url)
            if url.startswith("http")
            else Web3.WebsocketProvider(url)
        )
    else:
        w3 = Web3(Web3.HTTPProvider(CHAINS.get(url, url)))
    return w3


def _get_private_key(private_key: str = None, wallet_name: str = None) -> str:
    """Resolve private key from arg, wallet file, or env."""
    if private_key:
        return private_key
    if wallet_name:
        wallet_file = KEYSTORE_DIR / f"{wallet_name}.json"
        if wallet_file.exists():
            data = json.loads(wallet_file.read_text())
            return data["private_key"]
    # Fallback to env
    pk = os.getenv("BLOCKCHAIN_PRIVATE_KEY") or os.getenv("PRIVATE_KEY")
    if pk:
        return pk
    raise ValueError(
        "No private key provided. Use private_key=, wallet_name=, or set BLOCKCHAIN_PRIVATE_KEY env var"
    )


def _format_wei(w3, wei_value) -> str:
    """Format wei to human-readable."""
    eth = w3.from_wei(wei_value, "ether")
    return f"{eth} ETH/MATIC ({wei_value} wei)"


# ═══════════════════════════════════════════
#  WALLET ACTIONS
# ═══════════════════════════════════════════


def _wallet_create(name: str = None) -> Dict:
    """Create a new wallet."""
    Account = _get_eth_account()
    acct = Account.create()

    wallet_data = {
        "address": acct.address,
        "private_key": acct.key.hex(),
    }

    # Save to keystore
    wallet_name = name or f"wallet-{acct.address[:8].lower()}"
    wallet_file = KEYSTORE_DIR / f"{wallet_name}.json"
    wallet_file.write_text(json.dumps(wallet_data, indent=2))
    wallet_file.chmod(0o600)

    return {
        "status": "success",
        "content": [
            {
                "text": f"🔐 Wallet created!\n"
                f"   Name: {wallet_name}\n"
                f"   Address: {acct.address}\n"
                f"   Private Key: {acct.key.hex()}\n"
                f"   Saved to: {wallet_file}\n\n"
                f"⚠️ SAVE YOUR PRIVATE KEY SECURELY!"
            }
        ],
    }


def _wallet_import(private_key: str, name: str = None) -> Dict:
    """Import wallet from private key."""
    if not private_key:
        return {
            "status": "error",
            "content": [{"text": "private_key= required for wallet_import"}],
        }
    Account = _get_eth_account()
    if not private_key.startswith("0x"):
        private_key = "0x" + private_key
    try:
        acct = Account.from_key(private_key)
    except Exception as e:
        return {"status": "error", "content": [{"text": f"Invalid private key: {e}"}]}

    wallet_name = name or f"wallet-{acct.address[:8].lower()}"
    wallet_file = KEYSTORE_DIR / f"{wallet_name}.json"
    wallet_data = {
        "address": acct.address,
        "private_key": private_key,
    }
    wallet_file.write_text(json.dumps(wallet_data, indent=2))
    wallet_file.chmod(0o600)

    return {
        "status": "success",
        "content": [
            {
                "text": f"🔐 Wallet imported!\n   Name: {wallet_name}\n   Address: {acct.address}\n   Saved to: {wallet_file}"
            }
        ],
    }


def _wallet_list() -> Dict:
    """List all saved wallets."""
    wallets = []
    for f in KEYSTORE_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            wallets.append(f"  • {f.stem}: {data['address']}")
        except Exception:
            wallets.append(f"  • {f.stem}: (corrupt)")

    if not wallets:
        return {
            "status": "success",
            "content": [
                {"text": "No wallets found. Use action='wallet_create' to create one."}
            ],
        }

    return {
        "status": "success",
        "content": [
            {"text": f"🔐 Saved wallets ({KEYSTORE_DIR}):\n" + "\n".join(wallets)}
        ],
    }


# ═══════════════════════════════════════════
#  CHAIN INFO & BALANCE
# ═══════════════════════════════════════════


def _chain_info(chain: str = "local", rpc_url: str = None) -> Dict:
    """Get chain info."""
    w3 = _connect(chain, rpc_url)

    if not w3.is_connected():
        return {
            "status": "error",
            "content": [{"text": f"❌ Cannot connect to {chain}"}],
        }

    chain_id = w3.eth.chain_id
    block = w3.eth.block_number
    gas_price = w3.eth.gas_price

    return {
        "status": "success",
        "content": [
            {
                "text": f"⛓️ Chain Info:\n"
                f"   Chain ID: {chain_id}\n"
                f"   Block: {block}\n"
                f"   Gas Price: {_format_wei(w3, gas_price)}\n"
                f"   Connected: ✅"
            }
        ],
    }


def _balance(
    address: str, chain: str = "local", rpc_url: str = None, token_address: str = None
) -> Dict:
    """Check balance of an address."""
    w3 = _connect(chain, rpc_url)

    if not w3.is_connected():
        return {
            "status": "error",
            "content": [{"text": f"❌ Cannot connect to {chain}"}],
        }

    checksum = w3.to_checksum_address(address)

    if token_address:
        # ERC-20 balance
        erc20_abi = [
            {
                "constant": True,
                "inputs": [{"name": "_owner", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"name": "balance", "type": "uint256"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "symbol",
                "outputs": [{"name": "", "type": "string"}],
                "type": "function",
            },
            {
                "constant": True,
                "inputs": [],
                "name": "decimals",
                "outputs": [{"name": "", "type": "uint8"}],
                "type": "function",
            },
        ]
        token = w3.eth.contract(
            address=w3.to_checksum_address(token_address), abi=erc20_abi
        )
        raw_balance = token.functions.balanceOf(checksum).call()
        try:
            symbol = token.functions.symbol().call()
            decimals = token.functions.decimals().call()
            human_balance = raw_balance / (10**decimals)
            return {
                "status": "success",
                "content": [
                    {
                        "text": f"💰 {address}\n   {human_balance} {symbol} (raw: {raw_balance})"
                    }
                ],
            }
        except Exception:
            return {
                "status": "success",
                "content": [{"text": f"💰 {address}\n   Token balance: {raw_balance}"}],
            }
    else:
        # Native balance
        bal = w3.eth.get_balance(checksum)
        return {
            "status": "success",
            "content": [{"text": f"💰 {address}\n   Balance: {_format_wei(w3, bal)}"}],
        }


# ═══════════════════════════════════════════
#  TRANSACTIONS
# ═══════════════════════════════════════════


def _send(
    to: str,
    amount: str,
    chain: str = "local",
    rpc_url: str = None,
    private_key: str = None,
    wallet_name: str = None,
    unit: str = "ether",
    data: str = None,
) -> Dict:
    """Send native tokens."""
    w3 = _connect(chain, rpc_url)
    pk = _get_private_key(private_key, wallet_name)
    Account = _get_eth_account()

    acct = Account.from_key(pk)
    nonce = w3.eth.get_transaction_count(acct.address)

    tx = {
        "to": w3.to_checksum_address(to),
        "value": w3.to_wei(amount, unit),
        "gasPrice": w3.eth.gas_price,
        "nonce": nonce,
        "chainId": w3.eth.chain_id,
    }

    if data:
        tx["data"] = data

    # Estimate gas (21000 for simple transfers, more for data)
    tx["gas"] = w3.eth.estimate_gas(tx)

    signed = w3.eth.account.sign_transaction(tx, pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    return {
        "status": "success",
        "content": [
            {
                "text": f"📤 Transaction sent!\n"
                f"   From: {acct.address}\n"
                f"   To: {to}\n"
                f"   Amount: {amount} {unit}\n"
                f"   TX Hash: {tx_hash.hex()}\n"
                f"   Nonce: {nonce}"
            }
        ],
    }


def _tx_receipt(
    tx_hash: str, chain: str = "local", rpc_url: str = None, wait: bool = True
) -> Dict:
    """Get transaction receipt."""
    w3 = _connect(chain, rpc_url)

    if wait:
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    else:
        receipt = w3.eth.get_transaction_receipt(tx_hash)

    status = "✅ Success" if receipt["status"] == 1 else "❌ Failed"

    return {
        "status": "success",
        "content": [
            {
                "text": f"📋 TX Receipt:\n"
                f"   Hash: {tx_hash}\n"
                f"   Status: {status}\n"
                f"   Block: {receipt['blockNumber']}\n"
                f"   Gas Used: {receipt['gasUsed']}\n"
                f"   Contract: {receipt.get('contractAddress', 'N/A')}"
            }
        ],
    }


# ═══════════════════════════════════════════
#  COMPILE SOLIDITY
# ═══════════════════════════════════════════


def _compile(
    source_path: str = None,
    source_code: str = None,
    solc_version: str = "0.8.20",
    contract_name: str = None,
    import_remappings: dict = None,
) -> Dict:
    """Compile Solidity source code."""
    solcx = _get_solcx()

    # Install solc version if needed
    installed = [str(v) for v in solcx.get_installed_solc_versions()]
    if solc_version not in installed:
        solcx.install_solc(solc_version)

    # Read source
    if source_path:
        source_path = os.path.expanduser(source_path)
        with open(source_path, "r") as f:
            source_code = f.read()
        base_path = os.path.dirname(os.path.abspath(source_path))
    elif source_code:
        base_path = os.getcwd()
    else:
        return {
            "status": "error",
            "content": [{"text": "Provide source_path or source_code"}],
        }

    # Auto-detect contract name from source if not provided
    if not contract_name:
        matches = re.findall(r"contract\s+(\w+)", source_code)
        if matches:
            # Pick last non-interface, non-abstract contract
            contract_name = matches[-1]

    # Handle OpenZeppelin imports - check for node_modules
    allow_paths = [base_path]
    node_modules = os.path.join(base_path, "node_modules")
    if os.path.exists(node_modules):
        allow_paths.append(node_modules)

    # Also check parent dirs for node_modules
    parent = os.path.dirname(base_path)
    parent_nm = os.path.join(parent, "node_modules")
    if os.path.exists(parent_nm):
        allow_paths.append(parent_nm)

    try:
        # Try standard compile with import resolution
        compiled = solcx.compile_source(
            source_code,
            output_values=["abi", "bin", "bin-runtime"],
            solc_version=solc_version,
            base_path=base_path,
            allow_paths=allow_paths,
            import_remappings=import_remappings or {},
        )
    except Exception as e:
        error_str = str(e)
        # If import error, try with remappings
        if "not found" in error_str.lower() and "@openzeppelin" in source_code:
            # Auto-detect OpenZeppelin path
            for check_path in [base_path, parent, os.getcwd()]:
                oz_path = os.path.join(check_path, "node_modules", "@openzeppelin")
                if os.path.exists(oz_path):
                    remappings = {
                        "@openzeppelin/": os.path.join(
                            check_path, "node_modules", "@openzeppelin/"
                        )
                    }
                    try:
                        compiled = solcx.compile_source(
                            source_code,
                            output_values=["abi", "bin"],
                            solc_version=solc_version,
                            base_path=base_path,
                            allow_paths=allow_paths + [check_path],
                            import_remappings=remappings,
                        )
                        break
                    except Exception as e2:
                        error_str = str(e2)
                        continue
            else:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"❌ Compilation failed:\n{error_str}\n\nTip: Run 'npm install @openzeppelin/contracts' in the project directory."
                        }
                    ],
                }
        else:
            return {
                "status": "error",
                "content": [{"text": f"❌ Compilation failed:\n{error_str}"}],
            }

    # Extract the target contract
    results = {}
    for key, val in compiled.items():
        name = key.split(":")[-1]
        results[name] = {
            "abi": val.get("abi", []),
            "bytecode": val.get("bin", ""),
        }

    # Save to cache
    if contract_name and contract_name in results:
        cache_file = COMPILE_CACHE / f"{contract_name}.json"
        cache_file.write_text(json.dumps(results[contract_name], indent=2))

    # Summary
    contracts_info = []
    for name, data in results.items():
        fn_count = len([x for x in data["abi"] if x.get("type") == "function"])
        event_count = len([x for x in data["abi"] if x.get("type") == "event"])
        has_bytecode = len(data["bytecode"]) > 2
        contracts_info.append(
            f"  • {name}: {fn_count} functions, {event_count} events, bytecode={'✅' if has_bytecode else '❌'}"
        )

    return {
        "status": "success",
        "content": [
            {
                "text": f"✅ Compiled {len(results)} contract(s) (solc {solc_version}):\n"
                + "\n".join(contracts_info)
                + f"\n\n   Cache: {COMPILE_CACHE}"
            }
        ],
        "_compiled": results,  # Pass data for chaining
    }


# ═══════════════════════════════════════════
#  DEPLOY CONTRACT
# ═══════════════════════════════════════════


def _deploy(
    contract_name: str = None,
    abi: str = None,
    bytecode: str = None,
    constructor_args: list = None,
    chain: str = "local",
    rpc_url: str = None,
    private_key: str = None,
    wallet_name: str = None,
    source_path: str = None,
    solc_version: str = "0.8.20",
    gas_limit: int = None,
    value: str = "0",
) -> Dict:
    """Deploy a contract."""
    w3 = _connect(chain, rpc_url)
    pk = _get_private_key(private_key, wallet_name)
    Account = _get_eth_account()
    acct = Account.from_key(pk)

    # Resolve ABI and bytecode
    if abi and bytecode:
        # Direct ABI/bytecode
        if isinstance(abi, str):
            abi = json.loads(abi)
        pass
    elif contract_name:
        # Check compile cache
        cache_file = COMPILE_CACHE / f"{contract_name}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            abi = data["abi"]
            bytecode = data["bytecode"]
        elif source_path:
            # Compile first
            result = _compile(
                source_path=source_path,
                contract_name=contract_name,
                solc_version=solc_version,
            )
            if result["status"] == "error":
                return result
            compiled = result.get("_compiled", {})
            if contract_name in compiled:
                abi = compiled[contract_name]["abi"]
                bytecode = compiled[contract_name]["bytecode"]
            else:
                return {
                    "status": "error",
                    "content": [
                        {
                            "text": f"Contract '{contract_name}' not found in compiled output. Available: {list(compiled.keys())}"
                        }
                    ],
                }
        else:
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Contract '{contract_name}' not in cache. Compile first or provide source_path."
                    }
                ],
            }
    else:
        return {
            "status": "error",
            "content": [
                {
                    "text": "Provide contract_name (with cache/source_path) or abi+bytecode"
                }
            ],
        }

    # Ensure bytecode has 0x prefix
    if not bytecode.startswith("0x"):
        bytecode = "0x" + bytecode

    # Build contract
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    # Build constructor tx
    args = constructor_args or []
    constructor_tx = contract.constructor(*args).build_transaction(
        {
            "from": acct.address,
            "nonce": w3.eth.get_transaction_count(acct.address),
            "gasPrice": w3.eth.gas_price,
            "value": w3.to_wei(value, "ether") if value else 0,
        }
    )

    if gas_limit:
        constructor_tx["gas"] = gas_limit
    else:
        constructor_tx["gas"] = w3.eth.estimate_gas(constructor_tx)

    # Sign and send
    signed = w3.eth.account.sign_transaction(constructor_tx, pk)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)

    # Wait for receipt
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    contract_address = receipt["contractAddress"]

    # Save deployment info
    deploy_info = {
        "contract_name": contract_name or "unknown",
        "address": contract_address,
        "tx_hash": tx_hash.hex(),
        "chain": chain,
        "deployer": acct.address,
        "block": receipt["blockNumber"],
        "gas_used": receipt["gasUsed"],
        "abi": abi,
        "timestamp": int(time.time()),
    }
    deploy_file = COMPILE_CACHE / f"deploy-{contract_name or 'contract'}-{chain}.json"
    deploy_file.write_text(json.dumps(deploy_info, indent=2, default=str))

    status = "✅" if receipt["status"] == 1 else "❌ FAILED"

    return {
        "status": "success",
        "content": [
            {
                "text": f"{status} Contract deployed!\n"
                f"   Name: {contract_name or 'unknown'}\n"
                f"   Address: {contract_address}\n"
                f"   TX Hash: {tx_hash.hex()}\n"
                f"   Block: {receipt['blockNumber']}\n"
                f"   Gas Used: {receipt['gasUsed']}\n"
                f"   Deployer: {acct.address}\n"
                f"   Chain: {chain}\n"
                f"   Deployment saved: {deploy_file}"
            }
        ],
    }


# ═══════════════════════════════════════════
#  INVOKE CONTRACT FUNCTION
# ═══════════════════════════════════════════


def _invoke(
    contract_address: str,
    function_name: str,
    args: list = None,
    abi: str = None,
    contract_name: str = None,
    chain: str = "local",
    rpc_url: str = None,
    private_key: str = None,
    wallet_name: str = None,
    value: str = "0",
    read_only: bool = None,
) -> Dict:
    """Call a contract function (read or write)."""
    w3 = _connect(chain, rpc_url)

    # Resolve ABI
    if abi:
        if isinstance(abi, str):
            abi = json.loads(abi)
    elif contract_name:
        # Check cache
        cache_file = COMPILE_CACHE / f"{contract_name}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            abi = data["abi"]
        # Check deployment cache
        deploy_file = COMPILE_CACHE / f"deploy-{contract_name}-{chain}.json"
        if deploy_file.exists() and not contract_address:
            deploy_data = json.loads(deploy_file.read_text())
            abi = deploy_data.get("abi", abi)
            contract_address = deploy_data["address"]

    if not abi:
        return {
            "status": "error",
            "content": [
                {
                    "text": "No ABI found. Provide abi=, compile first, or use contract_name= with cache."
                }
            ],
        }

    if not contract_address:
        return {
            "status": "error",
            "content": [
                {
                    "text": "No contract_address provided and none found in deployment cache."
                }
            ],
        }

    contract = w3.eth.contract(
        address=w3.to_checksum_address(contract_address), abi=abi
    )

    # Find the function
    fn = contract.functions[function_name]
    call_args = args or []

    # Auto-detect read vs write
    if read_only is None:
        # Check ABI for mutability
        for item in abi:
            if item.get("type") == "function" and item.get("name") == function_name:
                mutability = item.get("stateMutability", "nonpayable")
                read_only = mutability in ("view", "pure")
                break
        else:
            read_only = False  # Default to write if can't determine

    if read_only:
        # Read call (free, no gas)
        result = fn(*call_args).call()

        # Format result nicely
        if isinstance(result, (list, tuple)):
            result_str = "\n".join(f"   [{i}]: {v}" for i, v in enumerate(result))
        elif isinstance(result, bytes):
            result_str = f"   {result.hex()}"
        else:
            result_str = f"   {result}"

        return {
            "status": "success",
            "content": [{"text": f"📖 {function_name}() → Read result:\n{result_str}"}],
        }
    else:
        # Write transaction (costs gas)
        pk = _get_private_key(private_key, wallet_name)
        Account = _get_eth_account()
        acct = Account.from_key(pk)

        tx = fn(*call_args).build_transaction(
            {
                "from": acct.address,
                "nonce": w3.eth.get_transaction_count(acct.address),
                "gasPrice": w3.eth.gas_price,
                "value": w3.to_wei(value, "ether") if value and value != "0" else 0,
            }
        )
        tx["gas"] = w3.eth.estimate_gas(tx)

        signed = w3.eth.account.sign_transaction(tx, pk)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

        status = "✅" if receipt["status"] == 1 else "❌ FAILED"

        # Decode events if any
        events_info = ""
        if receipt["logs"]:
            events_info = f"\n   Events: {len(receipt['logs'])} log(s) emitted"

        return {
            "status": "success",
            "content": [
                {
                    "text": f"{status} {function_name}() → Write TX:\n"
                    f"   TX Hash: {tx_hash.hex()}\n"
                    f"   Gas Used: {receipt['gasUsed']}\n"
                    f"   Block: {receipt['blockNumber']}"
                    f"{events_info}"
                }
            ],
        }


# ═══════════════════════════════════════════
#  ABI INSPECT
# ═══════════════════════════════════════════


def _abi_inspect(
    contract_name: str = None, abi: str = None, abi_path: str = None
) -> Dict:
    """Inspect a contract ABI - list all functions, events, and their signatures."""
    if abi:
        if isinstance(abi, str):
            abi = json.loads(abi)
    elif abi_path:
        with open(os.path.expanduser(abi_path)) as f:
            data = json.load(f)
            abi = data.get("abi", data) if isinstance(data, dict) else data
    elif contract_name:
        cache_file = COMPILE_CACHE / f"{contract_name}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            abi = data["abi"]
        else:
            return {
                "status": "error",
                "content": [
                    {"text": f"No cached ABI for '{contract_name}'. Compile first."}
                ],
            }
    else:
        return {
            "status": "error",
            "content": [{"text": "Provide contract_name, abi, or abi_path"}],
        }

    functions_read = []
    functions_write = []
    events = []

    for item in abi:
        if item.get("type") == "function":
            name = item["name"]
            inputs = ", ".join(
                f"{i['type']} {i.get('name','')}" for i in item.get("inputs", [])
            )
            outputs = ", ".join(f"{o['type']}" for o in item.get("outputs", []))
            mutability = item.get("stateMutability", "nonpayable")
            sig = f"{name}({inputs})"
            if outputs:
                sig += f" → ({outputs})"
            if mutability in ("view", "pure"):
                functions_read.append(f"  📖 {sig}  [{mutability}]")
            else:
                payable = " 💰" if mutability == "payable" else ""
                functions_write.append(f"  ✏️  {sig}{payable}")
        elif item.get("type") == "event":
            name = item["name"]
            inputs = ", ".join(
                f"{'indexed ' if i.get('indexed') else ''}{i['type']} {i.get('name','')}"
                for i in item.get("inputs", [])
            )
            events.append(f"  📢 {name}({inputs})")

    text = f"📋 ABI Inspection ({contract_name or 'contract'}):\n"
    if functions_read:
        text += f"\n  Read Functions ({len(functions_read)}):\n" + "\n".join(
            functions_read
        )
    if functions_write:
        text += f"\n\n  Write Functions ({len(functions_write)}):\n" + "\n".join(
            functions_write
        )
    if events:
        text += f"\n\n  Events ({len(events)}):\n" + "\n".join(events)

    return {"status": "success", "content": [{"text": text}]}


# ═══════════════════════════════════════════
#  DEPLOYMENTS LIST
# ═══════════════════════════════════════════


def _deployments() -> Dict:
    """List all cached deployments."""
    deploys = []
    for f in sorted(COMPILE_CACHE.glob("deploy-*.json")):
        try:
            data = json.loads(f.read_text())
            deploys.append(
                f"  • {data.get('contract_name','?')} on {data.get('chain','?')}\n"
                f"    Address: {data.get('address','?')}\n"
                f"    Deployer: {data.get('deployer','?')}\n"
                f"    Block: {data.get('block','?')}"
            )
        except Exception:
            continue

    if not deploys:
        return {"status": "success", "content": [{"text": "No deployments cached."}]}

    return {
        "status": "success",
        "content": [{"text": f"📦 Cached Deployments:\n\n" + "\n\n".join(deploys)}],
    }


# ═══════════════════════════════════════════
#  MAIN TOOL ENTRY POINT
# ═══════════════════════════════════════════


@tool
def blockchain(
    action: str,
    chain: str = "local",
    rpc_url: str = None,
    address: str = None,
    to: str = None,
    amount: str = None,
    private_key: str = None,
    wallet_name: str = None,
    name: str = None,
    source_path: str = None,
    source_code: str = None,
    solc_version: str = "0.8.20",
    contract_name: str = None,
    contract_address: str = None,
    constructor_args: list = None,
    function_name: str = None,
    args: list = None,
    abi: str = None,
    abi_path: str = None,
    bytecode: str = None,
    tx_hash: str = None,
    value: str = "0",
    unit: str = "ether",
    read_only: bool = None,
    token_address: str = None,
    gas_limit: int = None,
    data: str = None,
    import_remappings: dict = None,
) -> Dict[str, Any]:
    """
    🔗 Blockchain Dev Tool — wallets, contracts, transactions on any EVM chain.

    Actions:
        Wallet:
            wallet_create   - Create a new wallet (name=optional)
            wallet_import   - Import from private_key (private_key=, name=optional)
            wallet_list     - List saved wallets

        Chain:
            chain_info      - Get chain info (chain=, rpc_url=)
            balance         - Check balance (address=, chain=, token_address=optional for ERC-20)

        Transactions:
            send            - Send native tokens (to=, amount=, chain=, private_key=/wallet_name=)
            tx_receipt      - Get transaction receipt (tx_hash=, chain=)

        Contracts:
            compile         - Compile Solidity (source_path= or source_code=, solc_version=, contract_name=)
            deploy          - Deploy contract (contract_name= with cache, or source_path=, chain=, constructor_args=)
            invoke          - Call contract function (contract_address=, function_name=, args=, read_only=auto)
            abi_inspect     - Inspect ABI functions/events (contract_name= or abi= or abi_path=)
            deployments     - List all cached deployments

    Chains (shortcuts):
        local, hardhat, polygon, mumbai, amoy, ethereum, sepolia, arbitrum, base, optimism
        Or pass any RPC URL via rpc_url=

    Examples:
        blockchain(action="wallet_create", name="dev")
        blockchain(action="balance", address="0x...", chain="polygon")
        blockchain(action="compile", source_path="contracts/Flex.sol", solc_version="0.8.4")
        blockchain(action="deploy", contract_name="Flex", chain="local", wallet_name="dev")
        blockchain(action="invoke", contract_address="0x...", function_name="name", chain="local")
        blockchain(action="invoke", contract_address="0x...", function_name="mint", args=["0x...", "myslug"], wallet_name="dev", value="0.1")
    """
    try:
        if action == "wallet_create":
            return _wallet_create(name)
        elif action == "wallet_import":
            return _wallet_import(private_key, name)
        elif action == "wallet_list":
            return _wallet_list()
        elif action == "chain_info":
            return _chain_info(chain, rpc_url)
        elif action == "balance":
            if not address:
                return {"status": "error", "content": [{"text": "address= required"}]}
            return _balance(address, chain, rpc_url, token_address)
        elif action == "send":
            if not to or not amount:
                return {
                    "status": "error",
                    "content": [{"text": "to= and amount= required"}],
                }
            return _send(
                to, amount, chain, rpc_url, private_key, wallet_name, unit, data
            )
        elif action == "tx_receipt":
            if not tx_hash:
                return {"status": "error", "content": [{"text": "tx_hash= required"}]}
            return _tx_receipt(tx_hash, chain, rpc_url)
        elif action == "compile":
            return _compile(
                source_path, source_code, solc_version, contract_name, import_remappings
            )
        elif action == "deploy":
            return _deploy(
                contract_name,
                abi,
                bytecode,
                constructor_args,
                chain,
                rpc_url,
                private_key,
                wallet_name,
                source_path,
                solc_version,
                gas_limit,
                value,
            )
        elif action == "invoke":
            return _invoke(
                contract_address,
                function_name,
                args,
                abi,
                contract_name,
                chain,
                rpc_url,
                private_key,
                wallet_name,
                value,
                read_only,
            )
        elif action == "abi_inspect":
            return _abi_inspect(contract_name, abi, abi_path)
        elif action == "deployments":
            return _deployments()
        else:
            actions = [
                "wallet_create",
                "wallet_import",
                "wallet_list",
                "chain_info",
                "balance",
                "send",
                "tx_receipt",
                "compile",
                "deploy",
                "invoke",
                "abi_inspect",
                "deployments",
            ]
            return {
                "status": "error",
                "content": [
                    {
                        "text": f"Unknown action: {action}\nValid actions: {', '.join(actions)}"
                    }
                ],
            }

    except Exception as e:
        return {
            "status": "error",
            "content": [{"text": f"❌ {action} failed: {str(e)}"}],
        }
