"""
network/discovery.py  —  UDP LAN discovery for local multiplayer
================================================================
Uses UDP broadcasts to advertise and find local game rooms via a 6-character code.
"""

import socket
import threading
import time

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
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    # Bind to all interfaces to listen for broadcasts
    sock.bind(('', udp_port))
    sock.settimeout(timeout)
    
    start_time = time.time()
    
    try:
        while time.time() - start_time < timeout:
            try:
                data, addr = sock.recvfrom(1024)
                message = data.decode('utf-8')
                if message.startswith("SMILE_ROOM:"):
                    parts = message.split(":")
                    if len(parts) >= 3 and parts[1] == target_code:
                        ip_address = addr[0]
                        tcp_port = int(parts[2])
                        sock.close()
                        return (ip_address, tcp_port)
            except socket.timeout:
                continue
            except Exception as e:
                print(f"[Discovery] Error: {e}")
                break
    finally:
        sock.close()
        
    return None
