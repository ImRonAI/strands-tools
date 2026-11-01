"""
strands-erc8004 — ERC-8004 Trustless Agents Protocol tools for Strands Agents

On-chain agent identity, reputation, and validation on any EVM chain.
Based on: https://eips.ethereum.org/EIPS/eip-8004

Four tools:
  - blockchain: Low-level EVM operations (wallets, contracts, transactions)
  - erc8004: High-level ERC-8004 protocol (identity, reputation, validation)
  - ipfs: Upload, fetch, pin content on IPFS (Pinata, web3.storage, local node)
  - x402: HTTP 402 internet-native payments (pay for / charge for API access)

Usage:
    from strands import Agent
    from strands_erc8004 import blockchain, erc8004, ipfs, x402

    agent = Agent(tools=[blockchain, erc8004, ipfs, x402])
    agent("Upload my agent registration to IPFS and register on Sepolia")
    agent("Pay for weather data at https://api.example.com/weather using wallet my-agent")
"""

from .blockchain import blockchain
from .erc8004 import erc8004
from .ipfs import ipfs
from .x402 import x402

__version__ = "0.2.0"
__all__ = ["blockchain", "erc8004", "ipfs", "x402"]
