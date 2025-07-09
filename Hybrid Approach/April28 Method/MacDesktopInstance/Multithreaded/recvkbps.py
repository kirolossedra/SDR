import socket
import time
import threading
from collections import deque
from tqdm import tqdm

# Configuration
PORT = 5005
BUFFER_SIZE = 65535        # Socket buffer size (not assumed packet size)
IDLE_TIMEOUT = 1.0         # Seconds of silence → burst ends

def receiver_function(stop_event, statistics, lock):
    # Set up UDP socket for broadcast
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 0)
    except Exception:
        pass
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
    sock.bind(("", PORT))
    sock.settimeout(IDLE_TIMEOUT)

    burst_count = 0
    burst_start = None
    burst_last = None
    total_bytes = 0
    thread_name = threading.current_thread().name

    print(f"{thread_name}: Listening for broadcasts on port {PORT}...")

    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(BUFFER_SIZE)
            now = time.time()
            packet_size = len(data)

            if burst_count == 0:
                burst_start = now
                total_bytes = 0  # Reset byte counter for new burst

            burst_last = now
            burst_count += 1
            total_bytes += packet_size

            print(f"{thread_name}: Received packet of {packet_size} bytes from {addr}")
            
        except socket.timeout:
            if burst_count > 0:
                elapsed = burst_last - burst_start
                kB_recv = total_bytes / 1024                # kilobytes
                kilobits = (total_bytes * 8) / 1024         # kilobits
                kbps = kilobits / elapsed if elapsed > 0 else 0

                with lock:
                    statistics.append((thread_name, burst_start, burst_last, burst_count, kB_recv, kbps))

                print(f"{thread_name}: Burst ended. Packets: {burst_count}, kB: {kB_recv:.2f}, kbps: {kbps:.2f}")

                # Reset burst tracking
                burst_count = 0
                burst_start = None
                burst_last = None
                total_bytes = 0

            if stop_event.is_set():
                break
            print(f"{thread_name}: Waiting for data...")
            
        except OSError as e:
            print(f"{thread_name}: Socket error: {e}")
            if stop_event.is_set():
                break
                
    sock.close()
    print(f"{thread_name}: Stopped.")

def main():
    N = int(input("Enter the number of threads: "))
    
    stop_event = threading.Event()
    statistics = deque()
    lock = threading.Lock()
    threads = []

    for i in range(N):
        thread = threading.Thread(
            target=receiver_function,
            args=(stop_event, statistics, lock),
            name=f"Thread-{i+1}"
        )
        threads.append(thread)

    for thread in tqdm(threads, desc="Starting threads"):
        thread.start()

    print(f"Listening for broadcasts on port {PORT} with {N} threads. Press Ctrl+C to stop...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user, stopping threads...")
        stop_event.set()
        for thread in threads:
            thread.join()

    print("\nSummary of Burst Throughputs:")
    print("{:<10} {:<20} {:<20} {:<10} {:<10} {:<10}".format(
        "Thread", "Start Time", "End Time", "Packets", "kB", "kbps"
    ))
    for stat in sorted(statistics, key=lambda x: x[1]):
        thread_name, burst_start, burst_last, burst_count, kB_recv, kbps = stat
        start_str = time.strftime('%H:%M:%S', time.localtime(burst_start))
        end_str = time.strftime('%H:%M:%S', time.localtime(burst_last))
        print("{:<10} {:<20} {:<20} {:<10} {:<10.2f} {:<10.2f}".format(
            thread_name, start_str, end_str, burst_count, kB_recv, kbps
        ))

if __name__ == "__main__":
    main()
