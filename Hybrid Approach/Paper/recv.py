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

# Global socket that all threads will share
global_socket = None
socket_lock = threading.Lock()

def create_shared_socket():
    """Create a single shared socket for all threads"""
    global global_socket
    if global_socket is None:
        global_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        global_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            global_socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 0)
        except Exception:
            pass
        global_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        global_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 256 * 1024)
        global_socket.bind(("", PORT))
        global_socket.settimeout(0.1)  # Shorter timeout for better responsiveness
    return global_socket

def close_shared_socket():
    """Close the shared socket"""
    global global_socket
    if global_socket:
        global_socket.close()
        global_socket = None

def receiver_function(stop_event, statistics, lock):
    """Modified receiver that shares a single socket among threads"""
    burst_count = 0
    burst_start = None
    burst_last = None
    thread_name = threading.current_thread().name
    
    sock = create_shared_socket()

    while not stop_event.is_set():
        try:
            with socket_lock:  # Only one thread can receive at a time
                if stop_event.is_set():
                    break
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
                except OSError as e:
                    if getattr(e, 'winerror', None) == 10040:
                        now = time.time()
                        if burst_count == 0:
                            burst_start = now
                        burst_last = now
                        burst_count += 1
                    else:
                        if not stop_event.is_set():
                            print(f"{thread_name}: Socket error: {e}")
                        break
        except Exception as e:
            if not stop_event.is_set():
                print(f"{thread_name}: Error: {e}")
            break
    
    # Handle final burst if any
    if burst_count > 0:
        elapsed = burst_last - burst_start if burst_last > burst_start else 1
        mb_recv = burst_count * PACKET_SIZE / (1024 * 1024)
        mbps = mb_recv * 8 / elapsed
        with lock:
            statistics.append((thread_name, burst_start, burst_last, burst_count, mb_recv, mbps))

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
    """Test a specific number of threads for TEST_DURATION seconds"""
    print(f"\n{'='*50}")
    print(f"Testing with {num_threads} threads...")
    print(f"{'='*50}")
    
    # Close any existing socket
    close_shared_socket()
    
    # Initialize shared variables
    stop_event = threading.Event()
    statistics = deque()
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

    # Start threads
    print(f"Starting {num_threads} threads...")
    for thread in threads:
        thread.start()

    print(f"Listening for {TEST_DURATION} seconds on port {PORT}...")
    
    # Wait for test duration
    time.sleep(TEST_DURATION)
    
    # Stop threads
    print("Stopping threads...")
    stop_event.set()
    for thread in threads:
        thread.join(timeout=2.0)  # Don't wait forever

    # Calculate total throughput
    total_throughput, total_packets = calculate_total_throughput(statistics)
    
    print(f"Test completed. Packets received: {total_packets}, Total throughput: {total_throughput:.2f} Mbps")
    
    # Display burst details if any
    if statistics:
        print(f"Number of bursts detected: {len(statistics)}")
        print("Recent burst details:")
        print("{:<6} {:<12} {:<12} {:<8} {:<8} {:<10}".format(
            "Thread", "Start", "End", "Packets", "MiB", "Mbps"
        ))
        # Show last few bursts
        recent_stats = list(statistics)[-min(5, len(statistics)):]
        for stat in recent_stats:
            thread_name, burst_start, burst_last, burst_count, mb_recv, mbps = stat
            start_str = time.strftime('%H:%M:%S', time.localtime(burst_start))
            end_str = time.strftime('%H:%M:%S', time.localtime(burst_last))
            print("{:<6} {:<12} {:<12} {:<8} {:<8.2f} {:<10.2f}".format(
                thread_name, start_str, end_str, burst_count, mb_recv, mbps
            ))
    else:
        print("⚠️  No data received during test period - check if broadcaster is running!")
    
    # Close socket after test
    close_shared_socket()
    
    return total_throughput, total_packets

def find_optimal_threads():
    """Find the optimal number of threads before throughput degrades"""
    print("Starting automatic thread optimization test...")
    print(f"Will test thread counts in increments of {THREAD_INCREMENT}")
    print(f"Looking for degradation threshold of {DEGRADATION_THRESHOLD*100}%")
    print("⚠️  Make sure your UDP broadcaster is running and sending to this port!")
    
    baseline_throughput = None
    current_threads = THREAD_INCREMENT
    optimal_threads = THREAD_INCREMENT
    test_results = []
    
    while True:
        throughput, packets = test_thread_count(current_threads)
        test_results.append((current_threads, throughput, packets))
        
        if baseline_throughput is None:
            if throughput > 0:
                baseline_throughput = throughput
                optimal_threads = current_threads
                print(f"\n✅ Baseline established: {baseline_throughput:.2f} Mbps with {current_threads} threads")
            else:
                print(f"\n⚠️  No throughput detected with {current_threads} threads - continuing...")
        else:
            # Check for degradation
            if baseline_throughput > 0:
                degradation = (baseline_throughput - throughput) / baseline_throughput
                improvement = (throughput - baseline_throughput) / baseline_throughput
                
                print(f"\nThroughput: {throughput:.2f} Mbps (Change: {improvement*100:+.1f}%)")
                
                if degradation > DEGRADATION_THRESHOLD:
                    print(f"\n🚨 DEGRADATION DETECTED!")
                    print(f"Throughput dropped by {degradation*100:.1f}% with {current_threads} threads")
                    print(f"Optimal thread count: {optimal_threads}")
                    break
                else:
                    # Update optimal if throughput improved significantly
                    if throughput > baseline_throughput:
                        baseline_throughput = throughput
                        optimal_threads = current_threads
                        print(f"🚀 New best throughput: {baseline_throughput:.2f} Mbps")
                    elif throughput >= baseline_throughput * (1 - DEGRADATION_THRESHOLD/3):
                        optimal_threads = current_threads  # Still acceptable
            else:
                print("Warning: Baseline throughput was 0, continuing...")
        
        # Increase thread count for next test
        current_threads += THREAD_INCREMENT
        
        # Safety check
        if current_threads > 50:
            print("Reached maximum test limit of 50 threads")
            break
        
        print(f"\n➡️  Next: Testing {current_threads} threads...")
        time.sleep(1)  # Brief pause between tests
    
    # Display summary
    print(f"\n{'='*60}")
    print("TEST RESULTS SUMMARY:")
    print("{:<8} {:<15} {:<10}".format("Threads", "Throughput (Mbps)", "Packets"))
    print("-" * 35)
    for threads, mbps, packets in test_results:
        marker = " ← OPTIMAL" if threads == optimal_threads else ""
        print("{:<8} {:<15.2f} {:<10}{marker}".format(threads, mbps, packets, marker=marker))
    
    print(f"\nFinal optimal thread count: {optimal_threads}")
    return optimal_threads

def main():
    print("UDP Broadcast Receiver - Auto Thread Optimization")
    print("=" * 60)
    
    try:
        optimal_threads = find_optimal_threads()
        
        print(f"\n{'='*60}")
        print(f"OPTIMIZATION COMPLETE")
        print(f"Optimal number of threads: {optimal_threads}")
        print(f"{'='*60}")
        
    except KeyboardInterrupt:
        print("\nOptimization interrupted by user.")
        close_shared_socket()
    except Exception as e:
        print(f"Error during optimization: {e}")
        close_shared_socket()
    finally:
        close_shared_socket()

if __name__ == "__main__":
    main()
