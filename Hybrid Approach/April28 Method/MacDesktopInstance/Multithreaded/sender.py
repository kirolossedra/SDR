# sender_throughput.py
import socket
import time

# Configuration
BROADCAST_IP = '192.168.0.255'   # KM-TEST adapter broadcast
PORT = 5005
PACKET_SIZE = 1024               # bytes per packet
duration = 5.0                   # seconds to send
send_delay = 0.0005              # 0.5ms pause to prevent buffer overflow

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 1048576)  # 1 MB send buffer

end_time = time.time() + duration
count = 0

while time.time() < end_time:
    try:
        sock.sendto(b'A' * PACKET_SIZE, (BROADCAST_IP, PORT))
        count += 1
    except OSError as e:
        print(f"Send failed: {e}")
        time.sleep(0.01)  # recover before next try
        continue
    time.sleep(send_delay)

elapsed = duration
mb_sent = count * PACKET_SIZE / (1024 * 1024)
mbps = mb_sent * 8 / elapsed
print(f"Sent {count} packets ({mb_sent:.2f} MiB) in {elapsed:.2f}s — throughput: {mbps:.2f} Mbps")
