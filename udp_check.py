"""Prints the pose packets sent by the phone app, so you can test before opening opentrack.

Usage:  python udp_check.py [port]      (default 4242)
Close opentrack first, otherwise it already owns the port.
"""
import socket
import struct
import sys

port = int(sys.argv[1]) if len(sys.argv) > 1 else 4242
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind(("0.0.0.0", port))
print(f"Listening on UDP {port}... (Ctrl+C to stop)")

while True:
    data, addr = sock.recvfrom(1024)
    if len(data) < 48:
        continue
    x, y, z, yaw, pitch, roll = struct.unpack("<6d", data[:48])
    print(
        f"\rx={x:7.1f} y={y:7.1f} z={z:7.1f} cm | "
        f"yaw={yaw:7.1f} pitch={pitch:7.1f} roll={roll:7.1f}   ",
        end="",
        flush=True,
    )
