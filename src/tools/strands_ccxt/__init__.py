"""Strands CCXT

Universal CCXT tool for Strands Agents.
Supports REST API, WebSocket streaming (ccxt.pro), and multi-exchange operations.

Usage:
    from strands_ccxt import use_ccxt
"""

from .use_ccxt import use_ccxt

__all__ = ["use_ccxt"]
