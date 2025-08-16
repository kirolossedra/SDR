import socket
import time
import threading
from collections import deque
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import queue
import subprocess
import platform

class UDPReceiverGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("UDP Broadcast Receiver")
        self.root.geometry("800x600")
        
        # Configuration
        self.PACKET_SIZE = 65535
        self.IDLE_TIMEOUT = 1.0
        
        # State variables
        self.threads = []
        self.stop_event = threading.Event()
        self.statistics = deque()
        self.lock = threading.Lock()
        self.is_listening = False
        self.log_queue = queue.Queue()
        
        self.create_widgets()
        self.update_log()
        
    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configuration frame
        config_frame = ttk.LabelFrame(main_frame, text="Configuration", padding="10")
        config_frame.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # Network Configuration Frame
        network_frame = ttk.LabelFrame(config_frame, text="Network Settings", padding="5")
        network_frame.grid(row=0, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(0, 10))
        
        # DHCP/Static toggle
        self.ip_mode_var = tk.StringVar(value="DHCP")
        dhcp_radio = ttk.Radiobutton(network_frame, text="DHCP", variable=self.ip_mode_var, 
                                    value="DHCP", command=self.toggle_ip_mode)
        dhcp_radio.grid(row=0, column=0, padx=(0, 10))
        
        static_radio = ttk.Radiobutton(network_frame, text="Static IP", variable=self.ip_mode_var, 
                                      value="Static", command=self.toggle_ip_mode)
        static_radio.grid(row=0, column=1, padx=(0, 20))
        
        # Static IP configuration (initially disabled)
        ttk.Label(network_frame, text="IP:").grid(row=0, column=2, padx=(0, 2))
        self.ip_var = tk.StringVar(value="192.168.1.100")
        self.ip_entry = ttk.Entry(network_frame, textvariable=self.ip_var, width=12, state='disabled')
        self.ip_entry.grid(row=0, column=3, padx=(0, 10))
        
        ttk.Label(network_frame, text="Subnet:").grid(row=0, column=4, padx=(0, 2))
        self.subnet_var = tk.StringVar(value="255.255.255.0")
        self.subnet_entry = ttk.Entry(network_frame, textvariable=self.subnet_var, width=12, state='disabled')
        self.subnet_entry.grid(row=0, column=5, padx=(0, 10))
        
        ttk.Label(network_frame, text="Gateway:").grid(row=0, column=6, padx=(0, 2))
        self.gateway_var = tk.StringVar(value="192.168.1.1")
        self.gateway_entry = ttk.Entry(network_frame, textvariable=self.gateway_var, width=12, state='disabled')
        self.gateway_entry.grid(row=0, column=7, padx=(0, 10))
        
        # Apply network settings button
        self.apply_network_btn = ttk.Button(network_frame, text="Apply Network Settings", 
                                           command=self.apply_network_settings, state='disabled')
        self.apply_network_btn.grid(row=0, column=8, padx=(10, 0))
        
        # UDP Configuration Frame
        udp_frame = ttk.Frame(config_frame)
        udp_frame.grid(row=1, column=0, columnspan=6, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # Port input
        ttk.Label(udp_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        self.port_var = tk.StringVar(value="5005")
        port_entry = ttk.Entry(udp_frame, textvariable=self.port_var, width=10)
        port_entry.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))
        
        # Thread count input
        ttk.Label(udp_frame, text="Number of Threads:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        self.threads_var = tk.StringVar(value="4")
        threads_entry = ttk.Entry(udp_frame, textvariable=self.threads_var, width=10)
        threads_entry.grid(row=0, column=3, sticky=tk.W, padx=(0, 20))
        
        # Control buttons
        self.start_button = ttk.Button(udp_frame, text="Start Listening", command=self.start_listening)
        self.start_button.grid(row=0, column=4, padx=(0, 10))
        
        self.stop_button = ttk.Button(udp_frame, text="Stop Listening", command=self.stop_listening, state='disabled')
        self.stop_button.grid(row=0, column=5)
        
        # Status
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(main_frame, textvariable=self.status_var, font=('Arial', 10, 'bold'))
        status_label.grid(row=1, column=0, columnspan=2, pady=(0, 10))
        
        # Log frame
        log_frame = ttk.LabelFrame(main_frame, text="Activity Log", padding="10")
        log_frame.grid(row=2, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=15, width=90)
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Statistics frame
        stats_frame = ttk.LabelFrame(main_frame, text="Statistics", padding="10")
        stats_frame.grid(row=3, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Thread selector
        thread_frame = ttk.Frame(stats_frame)
        thread_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        
        ttk.Label(thread_frame, text="Select Thread:").grid(row=0, column=0, padx=(0, 5))
        self.thread_var = tk.StringVar()
        self.thread_combo = ttk.Combobox(thread_frame, textvariable=self.thread_var, width=15, state='readonly')
        self.thread_combo.grid(row=0, column=1, padx=(0, 10))
        self.thread_combo.bind('<<ComboboxSelected>>', self.update_thread_stats)
        
        ttk.Button(thread_frame, text="Show All Threads", command=self.show_all_stats).grid(row=0, column=2)
        
        # Statistics table
        self.stats_tree = ttk.Treeview(stats_frame, columns=('start', 'end', 'packets', 'mib', 'mbps'), show='tree headings', height=8)
        self.stats_tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # Configure treeview columns
        self.stats_tree.heading('#0', text='Thread')
        self.stats_tree.heading('start', text='Start Time')
        self.stats_tree.heading('end', text='End Time')
        self.stats_tree.heading('packets', text='Packets')
        self.stats_tree.heading('mib', text='MiB')
        self.stats_tree.heading('mbps', text='Mbps')
        
        self.stats_tree.column('#0', width=80)
        self.stats_tree.column('start', width=100)
        self.stats_tree.column('end', width=100)
        self.stats_tree.column('packets', width=80)
        self.stats_tree.column('mib', width=80)
        self.stats_tree.column('mbps', width=80)
        
        # Scrollbar for treeview
        stats_scrollbar = ttk.Scrollbar(stats_frame, orient=tk.VERTICAL, command=self.stats_tree.yview)
        stats_scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.stats_tree.configure(yscrollcommand=stats_scrollbar.set)
        
        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(2, weight=1)
        main_frame.rowconfigure(3, weight=1)
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        stats_frame.columnconfigure(0, weight=1)
        stats_frame.rowconfigure(1, weight=1)
        
    def log_message(self, message):
        """Thread-safe logging"""
        self.log_queue.put(f"[{time.strftime('%H:%M:%S')}] {message}")
        
    def update_log(self):
        """Update log display from queue"""
        try:
            while True:
                message = self.log_queue.get_nowait()
                self.log_text.insert(tk.END, message + "\n")
                self.log_text.see(tk.END)
        except queue.Empty:
            pass
        
        # Schedule next update
        self.root.after(100, self.update_log)
        
    def receiver_function(self, stop_event, statistics, lock, thread_name):
        """UDP receiver function (modified for GUI)"""
        try:
            port = int(self.port_var.get())
        except ValueError:
            self.log_message(f"{thread_name}: Invalid port number")
            return
            
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
            sock.bind(("", port))
            sock.settimeout(self.IDLE_TIMEOUT)
        except Exception as e:
            self.log_message(f"{thread_name}: Failed to bind to port {port}: {e}")
            return

        burst_count = 0
        burst_start = None
        burst_last = None
        total_bytes = 0

        self.log_message(f"{thread_name}: Listening for broadcasts on port {port}...")

        while not stop_event.is_set():
            try:
                data, addr = sock.recvfrom(self.PACKET_SIZE)
                now = time.time()
                packet_size = len(data)
                self.log_message(f"{thread_name}: Received packet from {addr} ({packet_size} bytes)")
                if burst_count == 0:
                    burst_start = now
                    total_bytes = 0
                burst_last = now
                burst_count += 1
                total_bytes += packet_size
            except socket.timeout:
                if burst_count > 0:
                    elapsed = burst_last - burst_start
                    mb_recv = total_bytes / (1024 * 1024)
                    mbps = mb_recv * 8 / elapsed
                    with lock:
                        statistics.append((thread_name, burst_start, burst_last, burst_count, mb_recv, mbps))
                    self.log_message(f"{thread_name}: Burst ended. Packets: {burst_count}, Bytes: {total_bytes}, MiB: {mb_recv:.2f}, Mbps: {mbps:.2f}")
                    burst_count = 0
                    burst_start = None
                    burst_last = None
                    total_bytes = 0
                if stop_event.is_set():
                    break
                self.log_message(f"{thread_name}: Waiting for data...")
            except OSError as e:
                if getattr(e, 'winerror', None) == 10040:
                    now = time.time()
                    if burst_count == 0:
                        burst_start = now
                        total_bytes = 0
                    burst_last = now
                    burst_count += 1
                    total_bytes += self.PACKET_SIZE  # Oversized packet, use max size
                    self.log_message(f"{thread_name}: Received oversized packet (>{self.PACKET_SIZE} bytes)")
                else:
                    self.log_message(f"{thread_name}: Socket error: {e}")
                    break
                    
        sock.close()
        self.log_message(f"{thread_name}: Stopped.")
        
    def start_listening(self):
        """Start UDP listening threads"""
        if self.is_listening:
            return
            
        try:
            port = int(self.port_var.get())
            num_threads = int(self.threads_var.get())
        except ValueError:
            messagebox.showerror("Error", "Please enter valid port and thread count numbers")
            return
            
        if num_threads <= 0:
            messagebox.showerror("Error", "Number of threads must be greater than 0")
            return
            
        # Clear previous data
        self.statistics.clear()
        self.stats_tree.delete(*self.stats_tree.get_children())
        self.thread_combo['values'] = []
        self.thread_var.set('')
        
        # Reset stop event
        self.stop_event = threading.Event()
        self.threads = []
        
        # Create and start threads
        for i in range(num_threads):
            thread_name = f"Thread-{i+1}"
            thread = threading.Thread(
                target=self.receiver_function,
                args=(self.stop_event, self.statistics, self.lock, thread_name),
                name=thread_name,
                daemon=True
            )
            self.threads.append(thread)
            thread.start()
            
        # Update thread selector
        thread_names = [f"Thread-{i+1}" for i in range(num_threads)]
        self.thread_combo['values'] = thread_names
        
        # Update UI state
        self.is_listening = True
        self.start_button.config(state='disabled')
        self.stop_button.config(state='normal')
        self.status_var.set(f"Listening on port {port} with {num_threads} threads")
        
        self.log_message(f"Started listening with {num_threads} threads on port {port}")
        
    def stop_listening(self):
        """Stop UDP listening threads"""
        if not self.is_listening:
            return
            
        self.log_message("Stopping all threads...")
        self.stop_event.set()
        
        # Wait for threads to finish (with timeout)
        for thread in self.threads:
            thread.join(timeout=2.0)
            
        # Update UI state
        self.is_listening = False
        self.start_button.config(state='normal')
        self.stop_button.config(state='disabled')
        self.status_var.set("Stopped")
        
        # Update statistics display
        self.show_all_stats()
        self.log_message("All threads stopped. Statistics updated.")
        
    def toggle_ip_mode(self):
        """Toggle between DHCP and Static IP mode"""
        mode = self.ip_mode_var.get()
        if mode == "Static":
            self.ip_entry.config(state='normal')
            self.subnet_entry.config(state='normal')
            self.gateway_entry.config(state='normal')
            self.apply_network_btn.config(state='normal')
        else:
            self.ip_entry.config(state='disabled')
            self.subnet_entry.config(state='disabled')
            self.gateway_entry.config(state='disabled')
            self.apply_network_btn.config(state='normal')  # Still allow applying DHCP
            
    def get_wifi_interface_name(self):
        """Get the WiFi interface name (Windows specific)"""
        try:
            result = subprocess.run(['netsh', 'wlan', 'show', 'interfaces'], 
                                  capture_output=True, text=True, check=True)
            lines = result.stdout.split('\n')
            for line in lines:
                if 'Name' in line and 'Wi-Fi' in line:
                    return line.split(':')[-1].strip()
                elif 'Name' in line and ('Wireless' in line or 'WLAN' in line):
                    return line.split(':')[-1].strip()
            # Fallback - try common names
            return "Wi-Fi"
        except:
            return "Wi-Fi"  # Default fallback
            
    def apply_network_settings(self):
        """Apply network settings (requires admin privileges)"""
        if platform.system() != 'Windows':
            messagebox.showerror("Error", "Network configuration is currently only supported on Windows")
            return
            
        mode = self.ip_mode_var.get()
        interface_name = self.get_wifi_interface_name()
        
        try:
            if mode == "DHCP":
                # Set to DHCP
                subprocess.run(['netsh', 'interface', 'ip', 'set', 'address', 
                              interface_name, 'dhcp'], check=True)
                subprocess.run(['netsh', 'interface', 'ip', 'set', 'dns', 
                              interface_name, 'dhcp'], check=True)
                self.log_message(f"Successfully set {interface_name} to DHCP")
                messagebox.showinfo("Success", f"Network interface '{interface_name}' set to DHCP")
                
            else:  # Static
                ip = self.ip_var.get().strip()
                subnet = self.subnet_var.get().strip()
                gateway = self.gateway_var.get().strip()
                
                # Validate IP addresses
                if not self.validate_ip(ip) or not self.validate_ip(subnet) or not self.validate_ip(gateway):
                    messagebox.showerror("Error", "Please enter valid IP addresses")
                    return
                
                # Set static IP
                subprocess.run(['netsh', 'interface', 'ip', 'set', 'address', 
                              interface_name, 'static', ip, subnet, gateway], check=True)
                
                # Set DNS (optional - using Google DNS as default)
                subprocess.run(['netsh', 'interface', 'ip', 'set', 'dns', 
                              interface_name, 'static', '8.8.8.8'], check=True)
                subprocess.run(['netsh', 'interface', 'ip', 'add', 'dns', 
                              interface_name, '8.8.4.4', 'index=2'], check=True)
                
                self.log_message(f"Successfully set {interface_name} to static IP: {ip}")
                messagebox.showinfo("Success", f"Network interface '{interface_name}' configured:\n"
                                               f"IP: {ip}\nSubnet: {subnet}\nGateway: {gateway}")
                
        except subprocess.CalledProcessError as e:
            error_msg = "Failed to apply network settings. This usually means:\n\n" \
                       "1. The application needs to run as Administrator\n" \
                       "2. The WiFi interface name couldn't be detected\n" \
                       "3. Invalid network parameters\n\n" \
                       f"Error: {e}"
            messagebox.showerror("Network Configuration Error", error_msg)
            self.log_message(f"Network configuration failed: {e}")
            
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error: {e}")
            self.log_message(f"Network configuration error: {e}")
            
    def validate_ip(self, ip):
        """Validate IP address format"""
        try:
            parts = ip.split('.')
            if len(parts) != 4:
                return False
            for part in parts:
                if not 0 <= int(part) <= 255:
                    return False
            return True
        except:
            return False
        
    def update_thread_stats(self, event=None):
        """Update statistics display for selected thread"""
        selected_thread = self.thread_var.get()
        if not selected_thread:
            return
            
        # Clear current display
        self.stats_tree.delete(*self.stats_tree.get_children())
        
        # Filter statistics for selected thread
        thread_stats = [stat for stat in self.statistics if stat[0] == selected_thread]
        
        # Add to treeview
        for stat in sorted(thread_stats, key=lambda x: x[1]):
            thread_name, burst_start, burst_last, burst_count, mb_recv, mbps = stat
            start_str = time.strftime('%H:%M:%S', time.localtime(burst_start))
            end_str = time.strftime('%H:%M:%S', time.localtime(burst_last))
            
            self.stats_tree.insert('', tk.END, text=thread_name,
                                 values=(start_str, end_str, burst_count, f"{mb_recv:.2f}", f"{mbps:.2f}"))
                                 
    def show_all_stats(self):
        """Show statistics for all threads"""
        # Clear current display
        self.stats_tree.delete(*self.stats_tree.get_children())
        self.thread_var.set('')
        
        # Add all statistics to treeview
        for stat in sorted(self.statistics, key=lambda x: (x[0], x[1])):
            thread_name, burst_start, burst_last, burst_count, mb_recv, mbps = stat
            start_str = time.strftime('%H:%M:%S', time.localtime(burst_start))
            end_str = time.strftime('%H:%M:%S', time.localtime(burst_last))
            
            self.stats_tree.insert('', tk.END, text=thread_name,
                                 values=(start_str, end_str, burst_count, f"{mb_recv:.2f}", f"{mbps:.2f}"))
                                 
    def on_closing(self):
        """Handle window closing"""
        if self.is_listening:
            self.stop_listening()
        self.root.destroy()

def main():
    root = tk.Tk()
    app = UDPReceiverGUI(root)
    
    # Handle window closing
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    
    # Start the GUI
    root.mainloop()

if __name__ == "__main__":
    main()
