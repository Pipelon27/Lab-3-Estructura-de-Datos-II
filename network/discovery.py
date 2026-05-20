"""
network/discovery.py  —  UDP LAN discovery for local multiplayer
================================================================
Uses UDP broadcasts to advertise and find local game rooms via a 6-character code.
"""

import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from network.protocol import recv_message

class RoomBroadcaster:
    """Periodically broadcasts a room code over UDP on the LAN."""
    
    def __init__(self, room_code: str, tcp_port: int = 5555, udp_port: int = 5556):
        self.room_code = room_code.upper()
        self.tcp_port = tcp_port
        self.udp_port = udp_port
        self._running = False
        self._thread = None
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    def start(self):
        """Start sending broadcast beacons in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._broadcast_loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Stop sending broadcasts."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0)
        try:
            self._sock.close()
        except OSError:
            pass

    def _broadcast_loop(self):
        # Format: SMILE_ROOM:<CODE>:<TCP_PORT>
        message = f"SMILE_ROOM:{self.room_code}:{self.tcp_port}".encode('utf-8')
        while self._running:
            try:
                self._sock.sendto(message, ('<broadcast>', self.udp_port))
            except Exception as e:
                print(f"[Broadcaster] Error sending UDP broadcast: {e}")
            time.sleep(1.0)


def discover_room(target_code: str, udp_port: int = 5556, timeout: float = 5.0) -> tuple[str, int] | None:
    """
    Listen for UDP broadcasts matching the target_code.
    Returns (ip_address, tcp_port) if found, else None.
    """
    target_code = target_code.upper()
    found = _discover_room_udp(target_code, udp_port, timeout)
    if found:
        return found
    return _discover_room_tcp_scan(target_code)


def _discover_room_udp(target_code: str, udp_port: int, timeout: float) -> tuple[str, int] | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        # Bind to all interfaces to listen for broadcasts
        sock.bind(('', udp_port))
        sock.settimeout(0.5)

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("SMILE_ROOM:"):
                    parts = message.split(":")
                    if len(parts) >= 3 and parts[1] == target_code:
                        return (addr[0], int(parts[2]))
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Discovery] UDP error: {e}")
                break
    finally:
        sock.close()
    return None


def _local_ipv4_addresses() -> list[str]:
    addresses = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass

    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        probe.connect(("8.8.8.8", 80))
        ip = probe.getsockname()[0]
        if not ip.startswith("127."):
            addresses.add(ip)
    except OSError:
        pass
    finally:
        try:
            probe.close()
        except Exception:
            pass
    return sorted(addresses)


def _probe_room_host(ip: str, target_code: str, tcp_port: int, timeout: float = 0.18) -> tuple[str, int] | None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect((ip, tcp_port))
        msg = recv_message(sock)
        data = msg.get("data", {}) if msg else {}
        if data.get("room_code") == target_code:
            return (ip, tcp_port)
    except OSError:
        return None
    finally:
        try:
            sock.close()
        except OSError:
            pass
    return None


def _discover_room_tcp_scan(target_code: str, tcp_port: int = 5555) -> tuple[str, int] | None:
    """Fallback for networks that block UDP broadcast discovery."""
    candidates = []
    for local_ip in _local_ipv4_addresses():
        parts = local_ip.split(".")
        if len(parts) == 4:
            prefix = ".".join(parts[:3])
            candidates.extend(f"{prefix}.{i}" for i in range(1, 255))

    # Try localhost too; useful when testing two game instances on one PC.
    candidates.append("127.0.0.1")
    candidates = list(dict.fromkeys(candidates))
    if not candidates:
        return None

    with ThreadPoolExecutor(max_workers=64) as executor:
        futures = [executor.submit(_probe_room_host, ip, target_code, tcp_port) for ip in candidates]
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                return result
    return None
