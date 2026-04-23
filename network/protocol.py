"""
network/protocol.py  —  Message protocol for co-op multiplayer
================================================================
All messages are JSON-encoded and length-prefixed (4-byte big-endian
header).  This module provides encode/decode helpers and the
``MessageType`` enumeration.

Wire format::

    ┌──────────────┬───────────────────────────────────┐
    │  4 bytes BE  │         JSON payload              │
    │  (uint32)    │  {"type": "...", "data": {…}}     │
    └──────────────┴───────────────────────────────────┘
"""

from __future__ import annotations

import json
import struct
from enum import Enum, auto
from settings import HEADER_SIZE


class MessageType(Enum):
    """Types of network messages exchanged between host and guest."""
    HANDSHAKE   = "handshake"
    POSITION    = "position"
    EVENT       = "event"
    INVENTORY   = "inventory"
    MISSION     = "mission"
    CHAT        = "chat"
    SYNC        = "sync"           # full state sync
    DISCONNECT  = "disconnect"


# ── encoding / decoding ──────────────────────────────────────

def encode_message(msg_type: MessageType | str, data: dict) -> bytes:
    """Encode a message into length-prefixed JSON bytes.

    Parameters
    ----------
    msg_type : MessageType or plain string
    data     : arbitrary JSON-serialisable payload

    Returns
    -------
    bytes : 4-byte length header + UTF-8 JSON body
    """
    if isinstance(msg_type, MessageType):
        msg_type = msg_type.value

    payload = json.dumps({
        "type": msg_type,
        "data": data,
    }).encode("utf-8")

    header = struct.pack("!I", len(payload))   # big-endian uint32
    return header + payload


def decode_header(header_bytes: bytes) -> int:
    """Extract the payload length from a 4-byte header.

    Raises ``ValueError`` if header is malformed.
    """
    if len(header_bytes) != HEADER_SIZE:
        raise ValueError(f"Expected {HEADER_SIZE}-byte header, got {len(header_bytes)}")
    return struct.unpack("!I", header_bytes)[0]


def decode_message(payload_bytes: bytes) -> dict:
    """Decode a JSON payload into ``{"type": str, "data": dict}``.

    Returns an empty dict on decode failure (never crashes).
    """
    try:
        msg = json.loads(payload_bytes.decode("utf-8"))
        return {
            "type": msg.get("type", ""),
            "data": msg.get("data", {}),
        }
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {"type": "error", "data": {}}


def recv_message(sock) -> dict | None:
    """Blocking receive of one framed message from *sock*.

    Returns the decoded dict or ``None`` on connection loss.
    """
    try:
        header = _recv_exact(sock, HEADER_SIZE)
        if header is None:
            return None
        length  = decode_header(header)
        payload = _recv_exact(sock, length)
        if payload is None:
            return None
        return decode_message(payload)
    except Exception:
        return None


def _recv_exact(sock, n: int) -> bytes | None:
    """Read exactly *n* bytes from *sock*.  Returns ``None`` on EOF."""
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf += chunk
    return buf
