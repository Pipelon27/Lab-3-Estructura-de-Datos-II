"""
network/server.py  —  TCP game server (Aiden / host)
=====================================================
Runs a threaded TCP server on ``DEFAULT_PORT`` (5555).
Aiden's game instance acts as the authoritative host;
Lena connects as a client.

The server:
* accepts one client connection
* receives Lena's position/input updates
* broadcasts the combined game state back
"""

from __future__ import annotations

import socket
import threading
from settings import DEFAULT_HOST, DEFAULT_PORT, BUFFER_SIZE
from network.protocol import (
    encode_message, recv_message, MessageType,
)
from network.discovery import RoomBroadcaster


class GameServer:
    """Threaded TCP server for co-op mode.

    Usage
    -----
    >>> server = GameServer()
    >>> server.start()          # non-blocking; spawns listener thread
    >>> server.send_player_update(data)
    >>> remote = server.get_remote_data()
    >>> server.stop()
    """

    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, room_code: str | None = None):
        self.host = host
        self.port = port
        self.room_code = room_code

        self._sock:    socket.socket | None = None
        self._client:  socket.socket | None = None
        self._running  = False
        self._lock     = threading.Lock()

        self._broadcaster: RoomBroadcaster | None = None
        if self.room_code:
            self._broadcaster = RoomBroadcaster(self.room_code, tcp_port=self.port)

        # Generate a seed for randomness sync
        import random
        self.seed = random.randint(0, 1000000)

        # Latest data received from the client (Lena)
        self._remote_data: dict | None = None

        # Asynchronous background sending fields
        import queue
        self._send_lock = threading.Lock()
        self._to_send_pos: dict | None = None
        self._send_queue = queue.Queue()
        self._send_event = threading.Event()

    # ── lifecycle ─────────────────────────────────────────────

    def start(self):
        """Bind the server socket and start the accept thread."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self.host, self.port))
        self._sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self._sock.listen(1)
        self._sock.settimeout(1.0)       # so we can check _running
        self._running = True

        if self._broadcaster:
            self._broadcaster.start()

        # Reset sending buffers
        with self._send_lock:
            self._to_send_pos = None
        while not self._send_queue.empty():
            try:
                self._send_queue.get_nowait()
            except Exception:
                break
        self._send_event.clear()

        # Start background threads
        t = threading.Thread(target=self._accept_loop, daemon=True)
        t.start()
        
        t_send = threading.Thread(target=self._send_loop, daemon=True)
        t_send.start()
        print(f"[Server] Listening on {self.host}:{self.port}")

    def stop(self):
        """Shutdown server and close sockets."""
        self._running = False
        self._send_event.set()
        if self._broadcaster:
            self._broadcaster.stop()
        try:
            if self._client:
                self._client.close()
            if self._sock:
                self._sock.close()
        except OSError:
            pass
        print("[Server] Stopped.")

    # ── threads ───────────────────────────────────────────────

    def _accept_loop(self):
        """Wait for one client to connect, then start recv loop."""
        while self._running:
            try:
                client, addr = self._sock.accept()
                print(f"[Server] Client connected: {addr}")
                client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

                # Send handshake with seed
                client.sendall(
                    encode_message(MessageType.HANDSHAKE, {"status": "ok", "seed": self.seed, "room_code": self.room_code})
                )
                client.settimeout(1.5)
                join_msg = recv_message(client)
                if join_msg and join_msg.get("data", {}).get("_probe"):
                    client.close()
                    continue
                if not join_msg or not join_msg.get("data", {}).get("_join"):
                    client.close()
                    continue
                client.settimeout(None)

                with self._lock:
                    self._client = client
                
                # Stop broadcasting once a real game client joins.
                if self._broadcaster:
                    self._broadcaster.stop()
                    self._broadcaster = None

                self._recv_loop()
            except socket.timeout:
                continue
            except OSError:
                break

    def _recv_loop(self):
        """Continuously receive messages from the connected client."""
        while self._running and self._client:
            msg = recv_message(self._client)
            if msg is None:
                print("[Server] Client disconnected.")
                with self._lock:
                    self._client = None
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

            client = None
            with self._lock:
                client = self._client

            if not client:
                # Clear buffers since there is no connected client
                with self._send_lock:
                    self._to_send_pos = None
                while not self._send_queue.empty():
                    try:
                        self._send_queue.get_nowait()
                    except queue.Empty:
                        break
                self._send_event.clear()
                continue

            # 1. Process queued events first (guaranteed delivery)
            while not self._send_queue.empty():
                try:
                    msg_type, msg_data = self._send_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    client.sendall(encode_message(msg_type, msg_data))
                except OSError:
                    with self._lock:
                        self._client = None
                    break

            # 2. Process latest position update
            pos_data = None
            with self._send_lock:
                if self._to_send_pos is not None:
                    pos_data = self._to_send_pos
                    self._to_send_pos = None
                    self._send_event.clear()

            if pos_data is not None and client:
                try:
                    client.sendall(encode_message(MessageType.POSITION, pos_data))
                except OSError:
                    with self._lock:
                        self._client = None

    # ── public API ────────────────────────────────────────────

    def send_player_update(self, data: dict):
        """Send the host's (Aiden) state to the client."""
        with self._lock:
            client_active = self._client is not None
        if client_active:
            with self._send_lock:
                self._to_send_pos = data
                self._send_event.set()

    def send_event(self, event_data: dict):
        """Send a game event to the client."""
        with self._lock:
            client_active = self._client is not None
        if client_active:
            self._send_queue.put((MessageType.EVENT, event_data))
            self._send_event.set()

    def get_remote_data(self) -> dict | None:
        """Return the latest data received from Lena (client)."""
        with self._lock:
            data = self._remote_data
            self._remote_data = None
            return data

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._client is not None
