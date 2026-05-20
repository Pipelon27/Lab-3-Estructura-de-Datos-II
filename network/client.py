"""
network/client.py  —  TCP game client (Lena / guest)
=====================================================
Connects to the host (Aiden's game instance) on ``DEFAULT_PORT``.
Sends Lena's input / position updates and receives the game state.
"""

from __future__ import annotations

import socket
import threading
from settings import DEFAULT_HOST, DEFAULT_PORT
from network.protocol import (
    encode_message, recv_message, MessageType,
)


class GameClient:
    """Threaded TCP client for co-op guest (Lena).

    Usage
    -----
    >>> client = GameClient()
    >>> client.connect()             # blocking connect + starts recv thread
    >>> client.send_player_update(data)
    >>> remote = client.get_remote_data()
    >>> client.disconnect()
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port

        self._sock:     socket.socket | None = None
        self._running   = False
        self._lock      = threading.Lock()
        self._remote_data: dict | None = None
        self._connected = False
        self.seed       = 0

        # Asynchronous background sending fields
        import queue
        self._send_lock = threading.Lock()
        self._to_send_pos: dict | None = None
        self._send_queue = queue.Queue()
        self._send_event = threading.Event()

    # ── lifecycle ─────────────────────────────────────────────

    def connect(self, timeout: float = 5.0):
        """Connect to the host server and start the receive thread.

        Raises ``ConnectionError`` if the server is unreachable.
        """
        # Resolve '0.0.0.0' to '127.0.0.1' on Windows client side
        if self.host == "0.0.0.0":
            self.host = "127.0.0.1"

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(timeout)
        try:
            self._sock.connect((self.host, self.port))
            self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except (socket.timeout, ConnectionRefusedError, OSError) as exc:
            raise ConnectionError(
                f"Cannot reach server at {self.host}:{self.port}"
            ) from exc

        self._running  = True
        self._connected = True

        # Wait for handshake
        hs = recv_message(self._sock)
        if hs and hs.get("type") == MessageType.HANDSHAKE.value:
            data = hs.get("data", {})
            self.seed = data.get("seed", 0)
            print(f"[Client] Connected to {self.host}:{self.port} (seed: {self.seed})")
        else:
            print("[Client] Warning: no handshake received")

        # The connect timeout is only for the initial join. Gameplay receives must
        # block, otherwise a slow host load is mistaken for a lost connection.
        self._sock.settimeout(None)

        # Reset sending buffers
        with self._send_lock:
            self._to_send_pos = None
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except Exception:
                break
        self._send_event.clear()

        # Send initial join event directly
        self._sock.sendall(
            encode_message(MessageType.EVENT, {"_join": True})
        )

        # Start background threads
        t_recv = threading.Thread(target=self._recv_loop, daemon=True)
        t_recv.start()
        t_send = threading.Thread(target=self._send_loop, daemon=True)
        t_send.start()

    def disconnect(self):
        """Gracefully disconnect."""
        self._running = False
        self._send_event.set()
        try:
            if self._sock:
                self._sock.sendall(
                    encode_message(MessageType.DISCONNECT, {})
                )
                self._sock.close()
        except OSError:
            pass
        self._connected = False
        print("[Client] Disconnected.")

    # Alias for game.py compatibility
    stop = disconnect

    # ── recv thread ───────────────────────────────────────────

    def _recv_loop(self):
        while self._running and self._sock:
            msg = recv_message(self._sock)
            if msg is None:
                print("[Client] Lost connection to server.")
                self._connected = False
                break
            with self._lock:
                self._remote_data = msg.get("data", {})

    # ── send thread ───────────────────────────────────────────

    def _send_loop(self):
        import queue
        while self._running:
            self._send_event.wait(timeout=0.1)
            if not self._running:
                break

            # 1. Process queued events first (guaranteed delivery)
            while not self._send_queue.empty():
                try:
                    msg_type, msg_data = self._send_queue.get_nowait()
                except queue.Empty:
                    break
                if self._sock and self._connected:
                    try:
                        self._sock.sendall(encode_message(msg_type, msg_data))
                    except OSError:
                        self._connected = False
                        return

            # 2. Process latest position update
            pos_data = None
            with self._send_lock:
                if self._to_send_pos is not None:
                    pos_data = self._to_send_pos
                    self._to_send_pos = None
                    self._send_event.clear()

            if pos_data is not None and self._sock and self._connected:
                try:
                    self._sock.sendall(encode_message(MessageType.POSITION, pos_data))
                except OSError:
                    self._connected = False
                    return

    # ── public API ────────────────────────────────────────────

    def send_player_update(self, data: dict):
        """Send Lena's state to the host."""
        if not self._connected:
            return
        with self._send_lock:
            self._to_send_pos = data
            self._send_event.set()

    def send_event(self, event_data: dict):
        """Notify the host about a local event."""
        if not self._connected:
            return
        self._send_queue.put((MessageType.EVENT, event_data))
        self._send_event.set()

    def get_remote_data(self) -> dict | None:
        """Return the latest state received from the host (Aiden)."""
        with self._lock:
            data = self._remote_data
            self._remote_data = None
            return data

    @property
    def is_connected(self) -> bool:
        return self._connected
