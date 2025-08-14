import socket
import time
import threading
from collections import deque
from tqdm import tqdm

# Configuration
PORT = 5005
PACKET_SIZE = 65535        # Big enough for any UDP datagram
IDLE_TIMEOUT = 1.0         # Seconds of silence → burst ends
TEST_DURATION = 7          # Seconds to test each thread count
THREAD_INCREMENT = 5       # Increase threads by this amount each test
DEGRADATION_THRESHOLD = 0.15  # 15% throughput degradation threshold

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
    try:
        sock.bind(("", PORT))
    except:
        pass
    sock.settimeout(IDLE_TIMEOUT)

    burst_count = 0
    burst_start = None
    burst_last = None
    thread_name = threading.current_thread().name

    while not stop_event.is_set():
        try:
            data, addr = sock.recvfrom(PACKET_SIZE)
            now = time.time()
            if burst_count == 0:
                burst_start = now
            burst_last = now
            burst_count += 1
        except socket.timeout:
            if burst_count > 0:
                elapsed = burst_last - burst_start
                mb_recv = burst_count * PACKET_SIZE / (1024 * 1024)
                mbps = mb_recv * 8 / elapsed
                with lock:
                    statistics.append((thread_name, burst_start, burst_last, burst_count, mb_recv, mbps))
                burst_count = 0
                burst_start = None
                burst_last = None
            if stop_event.is_set():
                break
        except OSError as e:
            if getattr(e, 'winerror', None) == 10040:
                now = time.time()
                if burst_count == 0:
                    burst_start = now
                burst_last = now
                burst_count += 1
            else:
                raise
    
    # Handle final burst if any
    if burst_count > 0:
        elapsed = burst_last - burst_start if burst_last > burst_start else 1
        mb_recv = burst_count * PACKET_SIZE / (1024 * 1024)
        mbps = mb_recv * 8 / elapsed
        with lock:
            statistics.append((thread_name, burst_start, burst_last, burst_count, mb_recv, mbps))
    
    sock.close()

def calculate_total_throughput(statistics):
    """Calculate total throughput from all bursts in the statistics"""
    total_mbps = 0
    total_packets = 0
    for stat in statistics:
        _, _, _, packets, _, mbps = stat
        total_mbps += mbps
        total_packets += packets
    return total_mbps, total_packets

def test_thread_count(num_threads):
    """Test a specific number of threads - completely clean test"""
    print(f"\nTesting {num_threads} threads for {TEST_DURATION} seconds...")
    
    # COMPLETELY FRESH START - new everything
    stop_event = threading.Event()
    statistics = deque()  # Fresh statistics
    lock = threading.Lock()
    threads = []

    # Create threads
    for i in range(num_threads):
        thread = threading.Thread(
            target=receiver_function,
            args=(stop_event, statistics, lock),
            name=f"T{i+1}"
        )
        threads.append(thread)

    # Start all threads
    for thread in threads:
        thread.start()

    # Let threads fully initialize and start receiving
    time.sleep(1)
    
    # CLEAR ANY STARTUP RESIDUE - reset statistics after initialization
    with lock:
        statistics.clear()  # Start measurement from clean slate
    
    print(f"Measurement started for {num_threads} threads...")
    
    # ACTUAL MEASUREMENT PERIOD - exactly TEST_DURATION seconds
    time.sleep(TEST_DURATION)
    
    # Stop threads
    stop_event.set()
    for thread in threads:
        thread.join(timeout=2.0)

    # Calculate results from this clean measurement period
    total_throughput, total_packets = calculate_total_throughput(statistics)
    
    print(f"RESULT: {num_threads} threads -> {total_throughput:.2f} Mbps ({total_packets} packets)")
    
    # Clean shutdown - let everything close properly
    time.sleep(1)
    
    return total_throughput, total_packets

def find_optimal_threads():
    """Find the optimal number of threads with fair measurements"""
    print("UDP Thread Optimization - Finding Optimal Thread Count")
    print("=" * 60)
    print(f"Testing {TEST_DURATION}s periods with {THREAD_INCREMENT} thread increments")
    print(f"Looking for >{DEGRADATION_THRESHOLD*100}% throughput degradation")
    
    baseline_throughput = None
    current_threads = THREAD_INCREMENT
    optimal_threads = THREAD_INCREMENT
    test_results = []
    
    while True:  # Keep going until degradation is found
        print(f"\n{'='*50}")
        print(f"STAGE: Testing {current_threads} threads")
        print(f"{'='*50}")
        
        # Run completely clean test
        throughput, packets = test_thread_count(current_threads)
        test_results.append((current_threads, throughput, packets))
        
        if baseline_throughput is None:
            if throughput > 0:
                baseline_throughput = throughput
                optimal_threads = current_threads
                print(f"✅ BASELINE: {baseline_throughput:.2f} Mbps with {current_threads} threads")
            else:
                print(f"⚠️  No throughput detected - check broadcaster")
        else:
            # Check for degradation
            if baseline_throughput > 0:
                degradation = (baseline_throughput - throughput) / baseline_throughput
                change_pct = ((throughput - baseline_throughput) / baseline_throughput) * 100
                
                print(f"Change vs baseline: {change_pct:+.1f}%")
                
                if degradation > DEGRADATION_THRESHOLD:
                    print(f"\n🚨 DEGRADATION DETECTED!")
                    print(f"Throughput dropped {degradation*100:.1f}% with {current_threads} threads")
                    print(f"OPTIMAL THREAD COUNT: {optimal_threads}")
                    break
                else:
                    # Update optimal if performance is still good
                    if throughput >= baseline_throughput * 0.98:  # Within 2%
                        optimal_threads = current_threads
                        if throughput > baseline_throughput:
                            baseline_throughput = throughput
                            print(f"🚀 New best: {baseline_throughput:.2f} Mbps")
        
        # Move to next thread count
        current_threads += THREAD_INCREMENT
        print(f"➡️  Next test: {current_threads} threads")
        
        # Safety check to prevent infinite loop
        if current_threads > 200:
            print("Reached safety limit of 200 threads")
            break
        
        # Clean pause between tests
        time.sleep(2)
    
    # Final summary
    print(f"\n{'='*60}")
    print("FINAL RESULTS:")
    print("{:<10} {:<15} {:<10} {:<10}".format("Threads", "Throughput", "Packets", "Status"))
    print("-" * 50)
    
    for threads, mbps, packets in test_results:
        status = "OPTIMAL" if threads == optimal_threads else ""
        print("{:<10} {:<15.2f} {:<10} {:<10}".format(threads, mbps, packets, status))
    
    return optimal_threads

def main():
    try:
        optimal_threads = find_optimal_threads()
        print(f"\n🏆 FINAL ANSWER: {optimal_threads} threads is optimal")
        
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
