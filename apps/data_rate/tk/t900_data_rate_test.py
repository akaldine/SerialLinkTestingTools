#!/usr/bin/env python3
"""
Tianze T900 Data Rate Test Tool
Tests end-to-end data rate, packet corruption, and latency between two T900 radios.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import serial
import serial.tools.list_ports
import threading
import time
import struct
import hashlib
from collections import deque
from typing import Optional, Tuple
from datetime import datetime
from t900_sweep_test_gui import SweepTestGUI


class T900DataRateTest:
    def __init__(self, root):
        self.root = root
        self.root.title("T900 Data Rate Test Tool")
        self.root.geometry("1000x800")
        
        self.sender_connection: Optional[serial.Serial] = None
        self.receiver_connection: Optional[serial.Serial] = None
        
        self.test_running = False
        self.test_end_time = None  # Track when test should end
        self.target_packets = None  # Track target number of packets for packet-count mode
        self.receiver_grace_period_end = None  # Track when receiver grace period ends (500ms after test stops)
        self.grace_period_data_received = False  # Track if data was received during grace period
        self.packet_count_wait_end = None  # Track when packet-count wait period ends (1s after test stops)
        self.test_thread: Optional[threading.Thread] = None
        self.receive_thread: Optional[threading.Thread] = None
        self.sender2_thread: Optional[threading.Thread] = None  # For bidirectional mode
        self.receiver2_thread: Optional[threading.Thread] = None  # For bidirectional mode
        self.monitor_thread: Optional[threading.Thread] = None  # Monitor for auto-stop
        
        # Diagnostic window for AT commands
        self.diag_window = None
        self.diag_text = None
        
        # RSSI values
        self.rssi_before = {'sender': {'S123': None, 'S124': None}, 'receiver': {'S123': None, 'S124': None}}
        self.rssi_after = {'sender': {'S123': None, 'S124': None}, 'receiver': {'S123': None, 'S124': None}}
        
        # Test statistics
        self.stats = {
            'bytes_sent': 0,
            'bytes_received': 0,
            'bytes_received_valid': 0,  # Only valid packets
            'bytes_received_total': 0,  # All packets (valid + corrupt)
            'packets_sent': 0,
            'packets_received': 0,
            'packets_corrupt': 0,
            'latency_samples': deque(maxlen=1000),  # Keep last 1000 samples
            'start_time': None,
            'end_time': None,
            # Calculated rates (single source of truth)
            'data_rate_total_bps': None,  # Total rate in bps
            'data_rate_total_kbps': None,  # Total rate in kbps
            'data_rate_valid_bps': None,  # Valid rate in bps
            'data_rate_valid_kbps': None,  # Valid rate in kbps
            'elapsed_time': None,  # Actual test duration
            # For bidirectional mode
            'bytes_sent_2': 0,
            'bytes_received_2': 0,
            'bytes_received_valid_2': 0,
            'bytes_received_total_2': 0,
            'packets_sent_2': 0,
            'packets_received_2': 0,
            'packets_corrupt_2': 0,
            'latency_samples_2': deque(maxlen=1000),
            # Bidirectional calculated rates
            'data_rate_total_bps_1': None,
            'data_rate_total_kbps_1': None,
            'data_rate_valid_bps_1': None,
            'data_rate_valid_kbps_1': None,
            'data_rate_total_bps_2': None,
            'data_rate_total_kbps_2': None,
            'data_rate_valid_bps_2': None,
            'data_rate_valid_kbps_2': None,
            'data_rate_total_bps_combined': None,
            'data_rate_total_kbps_combined': None,
            'data_rate_valid_bps_combined': None,
            'data_rate_valid_kbps_combined': None
        }
        
        # Packet structure: [sequence(4), timestamp(8), hash(32), data(variable)]
        self.packet_header_size = 44  # 4 + 8 + 32
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create the main GUI widgets"""
        # Main container with horizontal paned window (config left, results right)
        main_paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left pane: Configuration
        left_frame = ttk.Frame(main_paned)
        main_paned.add(left_frame, weight=1)
        self._create_config_pane(left_frame)
        
        # Right pane: Results
        right_frame = ttk.Frame(main_paned)
        main_paned.add(right_frame, weight=1)
        self._create_results_pane(right_frame)
        
    def _create_config_pane(self, parent):
        """Create configuration panel"""
        # Connection settings
        conn_frame = ttk.LabelFrame(parent, text="Connection Settings", padding=10)
        conn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Refresh ports button at top of connection settings
        refresh_frame = ttk.Frame(conn_frame)
        refresh_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(refresh_frame, text="Refresh Ports", command=self._refresh_ports).pack(side=tk.RIGHT)
        
        # Container for sender and receiver side by side
        conn_side_by_side = ttk.Frame(conn_frame)
        conn_side_by_side.pack(fill=tk.X, pady=5)
        
        # Sender connection (left side)
        sender_frame = ttk.LabelFrame(conn_side_by_side, text="Sender", padding=5)
        sender_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))
        
        ttk.Label(sender_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.sender_port_var = tk.StringVar()
        sender_port_combo = ttk.Combobox(sender_frame, textvariable=self.sender_port_var, width=15)
        sender_port_combo.grid(row=0, column=1, padx=5, pady=2)
        self.sender_port_combo = sender_port_combo
        
        ttk.Label(sender_frame, text="Baud Rate:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.sender_baud_var = tk.StringVar(value="115200")
        ttk.Combobox(sender_frame, textvariable=self.sender_baud_var, 
                    values=["4800", "7200", "9600", "14400", "19200", "28800", "38400", "57600", "115200", "230400", "460800", "921600"], width=15).grid(row=1, column=1, padx=5, pady=2)
        
        self.sender_connect_button = ttk.Button(sender_frame, text="Connect", command=self._connect_sender)
        self.sender_connect_button.grid(row=2, column=0, columnspan=2, pady=5)
        
        self.sender_status_label = ttk.Label(sender_frame, text="Disconnected", foreground="red")
        self.sender_status_label.grid(row=3, column=0, columnspan=2, pady=2)
        
        # Receiver connection (right side)
        receiver_frame = ttk.LabelFrame(conn_side_by_side, text="Receiver", padding=5)
        receiver_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        
        ttk.Label(receiver_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.receiver_port_var = tk.StringVar()
        receiver_port_combo = ttk.Combobox(receiver_frame, textvariable=self.receiver_port_var, width=15)
        receiver_port_combo.grid(row=0, column=1, padx=5, pady=2)
        self.receiver_port_combo = receiver_port_combo
        
        ttk.Label(receiver_frame, text="Baud Rate:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.receiver_baud_var = tk.StringVar(value="115200")
        ttk.Combobox(receiver_frame, textvariable=self.receiver_baud_var, 
                     values=["4800", "7200", "9600", "14400", "19200", "28800", "38400", "57600", "115200", "230400", "460800", "921600"], width=15).grid(row=1, column=1, padx=5, pady=2)
        
        self.receiver_connect_button = ttk.Button(receiver_frame, text="Connect", command=self._connect_receiver)
        self.receiver_connect_button.grid(row=2, column=0, columnspan=2, pady=5)
        
        self.receiver_status_label = ttk.Label(receiver_frame, text="Disconnected", foreground="red")
        self.receiver_status_label.grid(row=3, column=0, columnspan=2, pady=2)
        
        # Test parameters
        test_frame = ttk.LabelFrame(parent, text="Test Parameters", padding=10)
        test_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Input mode selection
        mode_frame = ttk.LabelFrame(test_frame, text="Input Mode", padding=5)
        mode_frame.grid(row=0, column=0, columnspan=5, sticky=tk.EW, pady=5)
        ttk.Label(mode_frame, text="Mode:").pack(side=tk.LEFT, padx=5)
        self.input_mode_var = tk.StringVar(value="Manual")
        input_mode_combo = ttk.Combobox(mode_frame, textvariable=self.input_mode_var,
                                        values=["Manual", "Speed-Based", "Packet-Count"], width=30, state='readonly')
        input_mode_combo.pack(side=tk.LEFT, padx=5)
        input_mode_combo.bind('<<ComboboxSelected>>', self._on_input_mode_changed)
        
        # Manual mode parameters
        self.manual_params_frame = ttk.Frame(test_frame)
        self.manual_params_frame.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=5)
        
        ttk.Label(self.manual_params_frame, text="Total Packet Size (bytes):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.write_size_var = tk.StringVar(value="145")
        write_size_entry = ttk.Entry(self.manual_params_frame, textvariable=self.write_size_var, width=20)
        write_size_entry.grid(row=0, column=1, padx=5, pady=2)
        # Add validation on focus loss
        write_size_entry.bind('<FocusOut>', self._validate_packet_size)
        ttk.Label(self.manual_params_frame, text="(Total on-wire packet size, min: 45)").grid(row=0, column=2, sticky=tk.W, padx=5)

        # Display derived payload size (total - header) - below the total packet size
        ttk.Label(self.manual_params_frame, text="Payload size (bytes):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.total_packet_size_var = tk.StringVar(value=str(max(int(self.write_size_var.get()) - self.packet_header_size, 0)))
        self.total_packet_size_label = ttk.Label(self.manual_params_frame, textvariable=self.total_packet_size_var, font=("Arial", 9, "bold"))
        self.total_packet_size_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(self.manual_params_frame, text="Write Frequency (s):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.write_freq_var = tk.StringVar(value="0.1")
        write_freq_entry = ttk.Entry(self.manual_params_frame, textvariable=self.write_freq_var, width=20)
        write_freq_entry.grid(row=2, column=1, padx=5, pady=2)
        ttk.Label(self.manual_params_frame, text="(Time between packets)").grid(row=2, column=2, sticky=tk.W, padx=5)
        
        # Calculated Expected Data Rate (read-only)
        ttk.Label(self.manual_params_frame, text="Expected Data Rate (kbps):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.expected_data_rate_var = tk.StringVar(value="11.60")
        self.expected_data_rate_label = ttk.Label(self.manual_params_frame, textvariable=self.expected_data_rate_var, 
                                                   font=("Arial", 9, "bold"), foreground="blue")
        self.expected_data_rate_label.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(self.manual_params_frame, text="Test Length (s):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.test_length_var = tk.StringVar(value="10")
        test_length_entry = ttk.Entry(self.manual_params_frame, textvariable=self.test_length_var, width=20)
        test_length_entry.grid(row=4, column=1, padx=5, pady=2)
        
        # Speed-based mode parameters
        self.speed_params_frame = ttk.Frame(test_frame)
        self.speed_params_frame.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=5)
        self.speed_params_frame.grid_remove()  # Hide by default
        
        ttk.Label(self.speed_params_frame, text="Test Duration (s):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.duration_var = tk.StringVar(value="10")
        duration_entry = ttk.Entry(self.speed_params_frame, textvariable=self.duration_var, width=20)
        duration_entry.grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(self.speed_params_frame, text="Buffer Size (bytes):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.buffer_size_var = tk.StringVar(value="145")
        buffer_size_entry = ttk.Entry(self.speed_params_frame, textvariable=self.buffer_size_var, width=20)
        buffer_size_entry.grid(row=1, column=1, padx=5, pady=2)
        buffer_size_entry.bind('<FocusOut>', self._validate_packet_size_speed)
        ttk.Label(self.speed_params_frame, text="(Total packet size including 44-byte header)").grid(row=1, column=2, sticky=tk.W, padx=5)
        
        ttk.Label(self.speed_params_frame, text="Payload size (bytes):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.payload_size_speed_var = tk.StringVar(value=str(max(int(self.buffer_size_var.get()) - self.packet_header_size, 0)))
        self.payload_size_speed_label = ttk.Label(self.speed_params_frame, textvariable=self.payload_size_speed_var, font=("Arial", 9, "bold"))
        self.payload_size_speed_label.grid(row=2, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(self.speed_params_frame, text="Desired Speed (kbps):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.desired_speed_var = tk.StringVar(value="10")
        desired_speed_entry = ttk.Entry(self.speed_params_frame, textvariable=self.desired_speed_var, width=20)
        desired_speed_entry.grid(row=3, column=1, padx=5, pady=2)
        
        ttk.Label(self.speed_params_frame, text="Calculated Write Frequency (s):").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.calc_write_freq_var = tk.StringVar(value="0.116")
        self.calc_write_freq_label = ttk.Label(self.speed_params_frame, textvariable=self.calc_write_freq_var, 
                                               font=("Arial", 9, "bold"), foreground="blue")
        self.calc_write_freq_label.grid(row=4, column=1, sticky=tk.W, padx=5, pady=2)
        
        # Hook up auto-calculation for speed-based mode
        self.buffer_size_var.trace_add("write", lambda *a: self._update_speed_based_calculations())
        self.desired_speed_var.trace_add("write", lambda *a: self._update_speed_based_calculations())
        
        # Packet-count mode parameters
        self.packet_count_params_frame = ttk.Frame(test_frame)
        self.packet_count_params_frame.grid(row=1, column=0, columnspan=5, sticky=tk.EW, pady=5)
        self.packet_count_params_frame.grid_remove()  # Hide by default
        
        ttk.Label(self.packet_count_params_frame, text="Total Packet Size (bytes):").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.packet_count_size_var = tk.StringVar(value="145")
        packet_count_size_entry = ttk.Entry(self.packet_count_params_frame, textvariable=self.packet_count_size_var, width=20)
        packet_count_size_entry.grid(row=0, column=1, padx=5, pady=2)
        packet_count_size_entry.bind('<FocusOut>', self._validate_packet_size_count)
        ttk.Label(self.packet_count_params_frame, text="(Total on-wire packet size, min: 45)").grid(row=0, column=2, sticky=tk.W, padx=5)
        
        # Display derived payload size (total - header)
        ttk.Label(self.packet_count_params_frame, text="Payload size (bytes):").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.packet_count_payload_var = tk.StringVar(value=str(max(int(self.packet_count_size_var.get()) - self.packet_header_size, 0)))
        self.packet_count_payload_label = ttk.Label(self.packet_count_params_frame, textvariable=self.packet_count_payload_var, 
                                                     font=("Arial", 9, "bold"))
        self.packet_count_payload_label.grid(row=1, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(self.packet_count_params_frame, text="Write Frequency (s):").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.packet_count_freq_var = tk.StringVar(value="0.1")
        packet_count_freq_entry = ttk.Entry(self.packet_count_params_frame, textvariable=self.packet_count_freq_var, width=20)
        packet_count_freq_entry.grid(row=2, column=1, padx=5, pady=2)
        ttk.Label(self.packet_count_params_frame, text="(Time between packets)").grid(row=2, column=2, sticky=tk.W, padx=5)
        
        # Calculated Expected Data Rate (read-only)
        ttk.Label(self.packet_count_params_frame, text="Expected Data Rate (kbps):").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.packet_count_data_rate_var = tk.StringVar(value="11.60")
        self.packet_count_data_rate_label = ttk.Label(self.packet_count_params_frame, textvariable=self.packet_count_data_rate_var, 
                                                        font=("Arial", 9, "bold"), foreground="blue")
        self.packet_count_data_rate_label.grid(row=3, column=1, sticky=tk.W, padx=5, pady=2)
        
        ttk.Label(self.packet_count_params_frame, text="Number of Packets:").grid(row=4, column=0, sticky=tk.W, pady=2)
        self.num_packets_var = tk.StringVar(value="100")
        num_packets_entry = ttk.Entry(self.packet_count_params_frame, textvariable=self.num_packets_var, width=20)
        num_packets_entry.grid(row=4, column=1, padx=5, pady=2)
        
        # Hook up auto-calculation for packet-count mode
        self.packet_count_size_var.trace_add("write", lambda *a: self._update_packet_count_calculations())
        self.packet_count_freq_var.trace_add("write", lambda *a: self._update_packet_count_calculations())
        
        # Common parameters (Direction, RSSI, etc.)
        row_start = 2
        ttk.Label(test_frame, text="Direction:").grid(row=row_start, column=0, sticky=tk.W, pady=2)
        self.direction_var = tk.StringVar(value="Bidirectional")
        direction_combo = ttk.Combobox(test_frame, textvariable=self.direction_var,
                                       values=["Bidirectional", "Sender → Receiver", "Receiver → Sender"],
                                       width=20, state='readonly')
        direction_combo.grid(row=row_start, column=1, padx=5, pady=2)
        ttk.Label(test_frame, text="(Communication direction)").grid(row=row_start, column=2, sticky=tk.W, padx=5)
        
        # RSSI measurement options
        rssi_frame = ttk.Frame(test_frame)
        rssi_frame.grid(row=row_start+1, column=0, columnspan=3, pady=10, sticky=tk.W)
        self.auto_rssi_before_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rssi_frame, text="Auto-read RSSI before test", 
                       variable=self.auto_rssi_before_var).pack(side=tk.LEFT, padx=5)
        self.auto_rssi_after_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rssi_frame, text="Auto-read RSSI after test", 
                       variable=self.auto_rssi_after_var).pack(side=tk.LEFT, padx=5)
        
        rssi_manual_frame = ttk.Frame(test_frame)
        rssi_manual_frame.grid(row=row_start+2, column=0, columnspan=3, pady=5, sticky=tk.W)
        ttk.Button(rssi_manual_frame, text="Read RSSI Now (Before)", command=self._read_rssi_before).pack(side=tk.LEFT, padx=5)
        ttk.Button(rssi_manual_frame, text="Read RSSI Now (After)", command=self._read_rssi_after).pack(side=tk.LEFT, padx=5)
        
        # Test control buttons - placed prominently in Test Parameters frame
        control_frame = ttk.LabelFrame(test_frame, text="Test Controls", padding=5)
        control_frame.grid(row=row_start+3, column=0, columnspan=5, pady=10, sticky=tk.EW)
        
        # Main action buttons
        button_row1 = ttk.Frame(control_frame)
        button_row1.pack(fill=tk.X, pady=2)
        
        self.start_button = ttk.Button(button_row1, text="Start Test", command=self._start_test, state=tk.DISABLED)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_row1, text="Stop Test", command=self._stop_test, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(button_row1, text="Clear Results", command=self._clear_results)
        self.clear_button.pack(side=tk.LEFT, padx=5)
        
        self.diag_button = ttk.Button(button_row1, text="Show Diagnostic Window", command=self._show_diag_window)
        self.diag_button.pack(side=tk.LEFT, padx=5)
        
        self.sweep_button = ttk.Button(button_row1, text="Sweep Test", command=self._show_sweep_test)
        self.sweep_button.pack(side=tk.LEFT, padx=5)
        
        # Refresh ports on startup
        self._refresh_ports()

        # Hook: keep total packet size label in sync with payload entry
        try:
            self.write_size_var.trace_add("write", lambda *a: self._update_total_packet_size())
            self.write_freq_var.trace_add("write", lambda *a: self._update_manual_data_rate())
        except Exception:
            pass
        
        # Initial calculations
        self._update_speed_based_calculations()
        self._update_manual_data_rate()
        self._update_packet_count_calculations()

    def _update_total_packet_size(self, *args):
        """Update the payload size label when total size changes"""
        try:
            total = int(self.write_size_var.get())
            if total < 0:
                return
            payload = max(total - self.packet_header_size, 0)
            self.total_packet_size_var.set(str(payload))
            # Also update expected data rate
            self._update_manual_data_rate()
        except Exception:
            # Ignore until valid integer
            pass
    
    def _update_manual_data_rate(self):
        """Update expected data rate calculation for manual mode"""
        try:
            total_size = int(self.write_size_var.get())
            write_freq = float(self.write_freq_var.get())
            
            if write_freq > 0:
                # Calculate expected data rate in kbps
                # Data rate (bps) = (total_size_bytes * 8) / write_freq_seconds
                # Data rate (kbps) = data_rate_bps / 1000
                data_rate_bps = (total_size * 8) / write_freq
                data_rate_kbps = data_rate_bps / 1000
                
                # Determine precision based on value
                if data_rate_kbps >= 100:
                    # For large values, 2 decimal places
                    self.expected_data_rate_var.set(f"{data_rate_kbps:.2f}")
                elif data_rate_kbps >= 10:
                    # For medium values, 3 decimal places
                    self.expected_data_rate_var.set(f"{data_rate_kbps:.3f}")
                else:
                    # For small values, 4 decimal places
                    self.expected_data_rate_var.set(f"{data_rate_kbps:.4f}")
            else:
                self.expected_data_rate_var.set("N/A")
        except (ValueError, ZeroDivisionError):
            self.expected_data_rate_var.set("N/A")
    
    def _on_input_mode_changed(self, event=None):
        """Handle input mode change"""
        mode = self.input_mode_var.get()
        if mode == "Manual":
            self.manual_params_frame.grid()
            self.speed_params_frame.grid_remove()
            self.packet_count_params_frame.grid_remove()
        elif mode == "Speed-Based":
            self.manual_params_frame.grid_remove()
            self.speed_params_frame.grid()
            self.packet_count_params_frame.grid_remove()
            self._update_speed_based_calculations()
        else:  # Packet-Count
            self.manual_params_frame.grid_remove()
            self.speed_params_frame.grid_remove()
            self.packet_count_params_frame.grid()
            self._update_packet_count_calculations()
    
    def _update_packet_count_calculations(self):
        """Update packet-count mode calculations"""
        try:
            total_size = int(self.packet_count_size_var.get())
            payload = max(total_size - self.packet_header_size, 0)
            self.packet_count_payload_var.set(str(payload))
            
            write_freq = float(self.packet_count_freq_var.get())
            if write_freq > 0:
                # Calculate expected data rate in kbps
                data_rate_bps = (total_size * 8) / write_freq
                data_rate_kbps = data_rate_bps / 1000
                
                # Determine precision based on value
                if data_rate_kbps >= 100:
                    self.packet_count_data_rate_var.set(f"{data_rate_kbps:.2f}")
                elif data_rate_kbps >= 10:
                    self.packet_count_data_rate_var.set(f"{data_rate_kbps:.3f}")
                else:
                    self.packet_count_data_rate_var.set(f"{data_rate_kbps:.4f}")
            else:
                self.packet_count_data_rate_var.set("N/A")
        except (ValueError, ZeroDivisionError):
            self.packet_count_data_rate_var.set("N/A")
    
    def _validate_packet_size_count(self, event=None):
        """Validate packet size for packet-count mode"""
        try:
            total = int(self.packet_count_size_var.get())
            min_size = self.packet_header_size + 1
            if total < min_size:
                messagebox.showerror("Invalid Packet Size", 
                                   f"Total packet size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                # Reset to minimum
                self.packet_count_size_var.set(str(min_size))
                self._update_packet_count_calculations()
        except ValueError:
            # Invalid input, show error
            messagebox.showerror("Invalid Input", 
                               "Packet size must be a valid integer")
            # Reset to default
            self.packet_count_size_var.set("145")
            self._update_packet_count_calculations()
    
    def _update_speed_based_calculations(self):
        """Update speed-based mode calculations"""
        try:
            buffer_size = int(self.buffer_size_var.get())
            payload = max(buffer_size - self.packet_header_size, 0)
            self.payload_size_speed_var.set(str(payload))
            
            speed_kbps = float(self.desired_speed_var.get())
            if speed_kbps > 0:
                # Convert kbps to bytes per second
                # kbps = kilobits per second = 1000 bits per second
                bytes_per_second = (speed_kbps * 1000) / 8
                # Calculate write frequency: time between packets
                write_freq = buffer_size / bytes_per_second
                
                # Determine precision based on value (adaptive precision)
                if write_freq >= 1.0:
                    # For large values (>= 1s), 2 decimal places
                    self.calc_write_freq_var.set(f"{write_freq:.2f}")
                elif write_freq >= 0.1:
                    # For medium values (0.1-1s), 4 decimal places
                    self.calc_write_freq_var.set(f"{write_freq:.4f}")
                else:
                    # For small values (<0.1s), 6 decimal places for precision
                    self.calc_write_freq_var.set(f"{write_freq:.6f}")
            else:
                self.calc_write_freq_var.set("N/A")
        except (ValueError, ZeroDivisionError):
            self.calc_write_freq_var.set("N/A")
    
    def _validate_packet_size_speed(self, event=None):
        """Validate packet size for speed-based mode"""
        try:
            total = int(self.buffer_size_var.get())
            min_size = self.packet_header_size + 1
            if total < min_size:
                messagebox.showerror("Invalid Packet Size", 
                                   f"Buffer size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                # Reset to minimum
                self.buffer_size_var.set(str(min_size))
                self._update_speed_based_calculations()
        except ValueError:
            # Invalid input, show error
            messagebox.showerror("Invalid Input", 
                               "Buffer size must be a valid integer")
            # Reset to default
            self.buffer_size_var.set("145")
            self._update_speed_based_calculations()
    
    def _validate_packet_size(self, event=None):
        """Validate packet size and show error if too small"""
        try:
            total = int(self.write_size_var.get())
            min_size = self.packet_header_size + 1
            if total < min_size:
                messagebox.showerror("Invalid Packet Size", 
                                   f"Total packet size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                # Reset to minimum
                self.write_size_var.set(str(min_size))
                self._update_total_packet_size()
        except ValueError:
            # Invalid input, show error
            messagebox.showerror("Invalid Input", 
                               "Packet size must be a valid integer")
            # Reset to default
            self.write_size_var.set("145")
            self._update_total_packet_size()
        
    def _create_results_pane(self, parent):
        """Create results display panel"""
        # Container for statistics and log (stacked vertically)
        results_container = ttk.Frame(parent)
        results_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Real-time statistics (top)
        stats_frame = ttk.LabelFrame(results_container, text="Real-Time Statistics", padding=10)
        stats_frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Create grid for statistics
        self.stats_labels = {}
        
        stats = [
            ("Data Rate (Total)", "data_rate_total"),
            ("Data Rate (Valid)", "data_rate_valid"),
            ("Send Rate", "send_rate"),
            ("Packets Sent", "packets_sent"),
            ("Packets Received", "packets_received"),
            ("Packet Loss Rate", "packet_loss"),
            ("Corrupt Packet Rate", "corrupt_rate"),
            ("Average Latency", "avg_latency"),
            ("Min Latency", "min_latency"),
            ("Max Latency", "max_latency"),
            ("Test Duration", "test_duration"),
            ("Bytes Sent", "bytes_sent"),
            ("Bytes Received (Total)", "bytes_received_total"),
            ("Bytes Received (Valid)", "bytes_received_valid"),
            ("RSSI Before (Sender)", "rssi_before_sender"),
            ("RSSI After (Sender)", "rssi_after_sender"),
            ("RSSI Before (Receiver)", "rssi_before_receiver"),
            ("RSSI After (Receiver)", "rssi_after_receiver")
        ]
        
        for idx, (label, key) in enumerate(stats):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(stats_frame, text=f"{label}:").grid(row=row, column=col, sticky=tk.W, padx=5, pady=2)
            value_label = ttk.Label(stats_frame, text="N/A", font=("Arial", 9, "bold"))
            value_label.grid(row=row, column=col+1, sticky=tk.W, padx=5, pady=2)
            self.stats_labels[key] = value_label
        
        # Log output (bottom)
        log_frame = ttk.LabelFrame(results_container, text="Test Log", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.log_text = scrolledtext.ScrolledText(log_frame, height=10, width=40)
        self.log_text.pack(fill=tk.BOTH, expand=True)
        
    def _refresh_ports(self):
        """Refresh available serial ports"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.sender_port_combo['values'] = ports
        self.receiver_port_combo['values'] = ports
        if ports:
            if not self.sender_port_var.get():
                self.sender_port_var.set(ports[0])
            if not self.receiver_port_var.get() and len(ports) > 1:
                self.receiver_port_var.set(ports[1])
    
    def _connect_sender(self):
        """Connect to sender port"""
        try:
            if self.sender_connection and self.sender_connection.is_open:
                self.sender_connection.close()
                self.sender_connection = None
                self.sender_connect_button.config(text="Connect")
                self.sender_status_label.config(text="Disconnected", foreground="red")
                self._log("Sender disconnected")
                self._update_button_states()
                return
            
            port = self.sender_port_var.get()
            baud = int(self.sender_baud_var.get())
            
            if not port:
                messagebox.showerror("Error", "Please select a sender port")
                return
            
            self.sender_connection = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            self.sender_connect_button.config(text="Disconnect")
            self.sender_status_label.config(text=f"Connected @ {baud} baud", foreground="green")
            self._log(f"Sender connected to {port} at {baud} baud")
            self._update_button_states()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect sender: {str(e)}")
            self._log(f"Sender connection failed: {str(e)}")
    
    def _connect_receiver(self):
        """Connect to receiver port"""
        try:
            if self.receiver_connection and self.receiver_connection.is_open:
                self.receiver_connection.close()
                self.receiver_connection = None
                self.receiver_connect_button.config(text="Connect")
                self.receiver_status_label.config(text="Disconnected", foreground="red")
                self._log("Receiver disconnected")
                self._update_button_states()
                return
            
            port = self.receiver_port_var.get()
            baud = int(self.receiver_baud_var.get())
            
            if not port:
                messagebox.showerror("Error", "Please select a receiver port")
                return
            
            self.receiver_connection = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            self.receiver_connect_button.config(text="Disconnect")
            self.receiver_status_label.config(text=f"Connected @ {baud} baud", foreground="green")
            self._log(f"Receiver connected to {port} at {baud} baud")
            self._update_button_states()
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect receiver: {str(e)}")
            self._log(f"Receiver connection failed: {str(e)}")
    
    def _update_button_states(self):
        """Update button states based on connection status"""
        both_connected = (self.sender_connection and self.sender_connection.is_open and
                         self.receiver_connection and self.receiver_connection.is_open)
        
        if not self.test_running:
            self.start_button.config(state=tk.NORMAL if both_connected else tk.DISABLED)
        else:
            self.start_button.config(state=tk.DISABLED)
    
    def _log(self, message: str):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
    
    def _log_diag(self, message: str):
        """Log message to diagnostic window (only if window is open)"""
        if self.diag_window is not None and self.diag_window.winfo_exists() and self.diag_text:
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            self.diag_text.insert(tk.END, f"[{timestamp}] {message}\n")
            self.diag_text.see(tk.END)
    
    def _show_diag_window(self):
        """Show diagnostic window for AT commands"""
        if self.diag_window is None or not self.diag_window.winfo_exists():
            self.diag_window = tk.Toplevel(self.root)
            self.diag_window.title("AT Command Diagnostic Window")
            self.diag_window.geometry("800x600")
            
            diag_frame = ttk.Frame(self.diag_window, padding=10)
            diag_frame.pack(fill=tk.BOTH, expand=True)
            
            ttk.Label(diag_frame, text="AT Command Log (All commands sent and responses received):", 
                     font=("Arial", 10, "bold")).pack(anchor=tk.W, pady=5)
            
            self.diag_text = scrolledtext.ScrolledText(diag_frame, height=30, width=90)
            self.diag_text.pack(fill=tk.BOTH, expand=True)
            
            button_frame = ttk.Frame(diag_frame)
            button_frame.pack(fill=tk.X, pady=5)
            
            ttk.Button(button_frame, text="Clear", command=lambda: self.diag_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
            ttk.Button(button_frame, text="Close", command=self.diag_window.destroy).pack(side=tk.LEFT, padx=5)
        else:
            self.diag_window.lift()
            self.diag_window.focus()
    
    def _show_sweep_test(self):
        """Show sweep test configuration window"""
        try:
            SweepTestGUI(self.root, self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open sweep test window: {str(e)}")
    
    def _clear_serial_buffers(self):
        """Clear all serial port input/output buffers"""
        try:
            if self.sender_connection and self.sender_connection.is_open:
                # Clear input buffer
                if self.sender_connection.in_waiting > 0:
                    discarded = self.sender_connection.read(self.sender_connection.in_waiting)
                    self._log_diag(f"Sender: Cleared {len(discarded)} bytes from input buffer")
                # Reset input buffer (more thorough)
                self.sender_connection.reset_input_buffer()
                # Reset output buffer
                self.sender_connection.reset_output_buffer()
                # Flush output
                self.sender_connection.flush()
                self._log_diag("Sender: Buffers cleared and flushed")
            
            if self.receiver_connection and self.receiver_connection.is_open:
                # Clear input buffer
                if self.receiver_connection.in_waiting > 0:
                    discarded = self.receiver_connection.read(self.receiver_connection.in_waiting)
                    self._log_diag(f"Receiver: Cleared {len(discarded)} bytes from input buffer")
                # Reset input buffer (more thorough)
                self.receiver_connection.reset_input_buffer()
                # Reset output buffer
                self.receiver_connection.reset_output_buffer()
                # Flush output
                self.receiver_connection.flush()
                self._log_diag("Receiver: Buffers cleared and flushed")
        except Exception as e:
            self._log(f"Warning: Error clearing buffers: {str(e)}")
    
    def _enter_at_mode(self, conn: serial.Serial) -> bool:
        """Enter AT command mode from data mode"""
        try:
            self._log_diag("=== Entering AT Mode ===")
            
            # Clear any pending data
            if conn.in_waiting > 0:
                pending = conn.read(conn.in_waiting)
                self._log_diag(f"Cleared {len(pending)} bytes of pending data")
            
            # Step 1: Idle for 1 second
            self._log_diag("Waiting 1 second (idle period)...")
            time.sleep(1.0)
            
            # Step 2: Send "+++"
            self._log_diag("Sending: +++")
            conn.write("+++".encode())
            conn.flush()  # Ensure data is sent
            
            # Step 3: Idle for another 1 second
            self._log_diag("Waiting 1 second (idle period after +++ )...")
            time.sleep(1.0)
            
            # Step 4: Read response
            response = ""
            start_time = time.time()
            self._log_diag("Reading response...")
            while time.time() - start_time < 2.0:
                if conn.in_waiting > 0:
                    chunk = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                    response += chunk
                    self._log_diag(f"Received chunk: {repr(chunk)}")
                    if "OK" in response.upper() or "Welcome" in response:
                        break
                time.sleep(0.1)
            
            # Read any remaining data
            if conn.in_waiting > 0:
                remaining = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                response += remaining
                self._log_diag(f"Remaining data: {repr(remaining)}")
            
            self._log_diag(f"Full response: {repr(response)}")
            
            success = "OK" in response.upper() or "Welcome" in response
            if success:
                self._log_diag("✓ Successfully entered AT mode")
            else:
                self._log_diag("✗ Failed to enter AT mode - no OK/Welcome in response")
            
            return success
            
        except Exception as e:
            error_msg = f"Error entering AT mode: {str(e)}"
            self._log(f"{error_msg}")
            self._log_diag(f"ERROR: {error_msg}")
            return False
    
    def _exit_at_mode(self, conn: serial.Serial) -> bool:
        """Exit AT command mode using ATA"""
        try:
            self._log_diag("=== Exiting AT Mode ===")
            self._log_diag("Sending: ATA")
            conn.write("ATA\r\n".encode())
            conn.flush()
            time.sleep(0.2)
            
            response = ""
            if conn.in_waiting > 0:
                response = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
            
            self._log_diag(f"Response: {repr(response)}")
            
            success = "OK" in response.upper()
            if success:
                self._log_diag("✓ Successfully exited AT mode")
            else:
                self._log_diag("✗ No OK in response (may have exited anyway)")
            
            return success
        except Exception as e:
            error_msg = f"Error exiting AT mode: {str(e)}"
            self._log(f"{error_msg}")
            self._log_diag(f"ERROR: {error_msg}")
            return False
    
    def _read_register(self, conn: serial.Serial, register: str) -> Optional[str]:
        """Read a register value using AT command"""
        try:
            reg_num = register[1:]  # Remove 'S' prefix
            cmd = f"ATS{reg_num}?\r\n"
            self._log_diag(f"Reading register {register}: Sending: {repr(cmd)}")
            conn.write(cmd.encode())
            conn.flush()
            
            # Wait a bit longer for response
            time.sleep(0.3)
            
            response = ""
            # Read with timeout
            start_time = time.time()
            while time.time() - start_time < 1.0:
                if conn.in_waiting > 0:
                    chunk = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                    response += chunk
                    self._log_diag(f"Received chunk: {repr(chunk)}")
                    if '\r\n' in response or '\n' in response:
                        break
                time.sleep(0.05)
            
            # Read any remaining
            if conn.in_waiting > 0:
                remaining = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                response += remaining
                self._log_diag(f"Remaining: {repr(remaining)}")
            
            response = response.strip()
            self._log_diag(f"Full response for {register}: {repr(response)}")
            
            # Parse response - format can be:
            # 1. S123=-82 (with equals sign)
            # 2. ATS123?\r\n-82\r\nOK\r\n (value on separate line after command echo)
            lines = response.split('\n')
            
            # First try format with equals sign
            for line in lines:
                if register.upper() in line.upper() and '=' in line:
                    value = line.split('=')[1].strip()
                    value = value.rstrip('\r')
                    self._log_diag(f"Parsed value for {register} (format with =): {value}")
                    return value
            
            # Try format where value is on separate line after command echo
            # Look for lines that are just numbers (possibly negative)
            for i, line in enumerate(lines):
                line = line.strip().rstrip('\r')
                # Check if this line looks like a number (could be negative)
                if line and (line[0].isdigit() or (len(line) > 1 and line[0] == '-' and line[1].isdigit())):
                    try:
                        # Try to parse as integer to validate
                        int(line)
                        self._log_diag(f"Parsed value for {register} (format on separate line): {line}")
                        return line
                    except ValueError:
                        continue
            
            self._log_diag(f"✗ Could not parse value from response for {register}")
            return None
        except Exception as e:
            error_msg = f"Error reading register {register}: {str(e)}"
            self._log(f"{error_msg}")
            self._log_diag(f"ERROR: {error_msg}")
            return None
    
    def _read_rssi(self, device_name: str, conn: serial.Serial) -> dict:
        """Read RSSI values (S123 and S124) from a device"""
        rssi = {'S123': None, 'S124': None}
        
        if not conn or not conn.is_open:
            self._log(f"{device_name}: Not connected")
            self._log_diag(f"{device_name}: Not connected - cannot read RSSI")
            return rssi
        
        self._log(f"Reading RSSI from {device_name}...")
        self._log_diag(f"=== Reading RSSI from {device_name} ===")
        
        # Enter AT mode
        self._log_diag(f"{device_name}: Attempting to enter AT mode...")
        if not self._enter_at_mode(conn):
            error_msg = f"{device_name}: Failed to enter AT mode"
            self._log(error_msg)
            self._log_diag(f"✗ {error_msg}")
            return rssi
        
        self._log_diag(f"{device_name}: Successfully entered AT mode")
        
        # Small delay to ensure AT mode is ready
        time.sleep(0.2)
        
        # Read S123 (RSSI From Master)
        self._log_diag(f"{device_name}: Reading S123 (RSSI From Master)...")
        s123_value = self._read_register(conn, "S123")
        if s123_value:
            try:
                rssi['S123'] = int(s123_value)
                msg = f"{device_name} S123 (RSSI From Master): {rssi['S123']} dBm"
                self._log(msg)
                self._log_diag(f"✓ {msg}")
            except ValueError as e:
                error_msg = f"{device_name} S123: Failed to parse value '{s123_value}': {str(e)}"
                self._log(f"✗ {error_msg}")
                self._log_diag(f"✗ {error_msg}")
        else:
            error_msg = f"{device_name} S123: No value returned"
            self._log(f"✗ {error_msg}")
            self._log_diag(f"✗ {error_msg}")
        
        # Small delay between register reads
        time.sleep(0.2)
        
        # Read S124 (RSSI From Slave)
        self._log_diag(f"{device_name}: Reading S124 (RSSI From Slave)...")
        s124_value = self._read_register(conn, "S124")
        if s124_value:
            try:
                rssi['S124'] = int(s124_value)
                msg = f"{device_name} S124 (RSSI From Slave): {rssi['S124']} dBm"
                self._log(msg)
                self._log_diag(f"✓ {msg}")
            except ValueError as e:
                error_msg = f"{device_name} S124: Failed to parse value '{s124_value}': {str(e)}"
                self._log(f"✗ {error_msg}")
                self._log_diag(f"✗ {error_msg}")
        else:
            error_msg = f"{device_name} S124: No value returned"
            self._log(f"✗ {error_msg}")
            self._log_diag(f"✗ {error_msg}")
        
        # Exit AT mode
        self._log_diag(f"{device_name}: Exiting AT mode...")
        self._exit_at_mode(conn)
        
        self._log_diag(f"=== Finished reading RSSI from {device_name} ===")
        
        return rssi
    
    def _read_rssi_before(self):
        """Read RSSI values before test"""
        if not (self.sender_connection and self.sender_connection.is_open):
            messagebox.showwarning("Warning", "Sender not connected")
            return
        
        if not (self.receiver_connection and self.receiver_connection.is_open):
            messagebox.showwarning("Warning", "Receiver not connected")
            return
        
        self.rssi_before['sender'] = self._read_rssi("Sender", self.sender_connection)
        time.sleep(0.5)
        self.rssi_before['receiver'] = self._read_rssi("Receiver", self.receiver_connection)
        
        # Update statistics display
        self.root.after(0, self._update_statistics)
        messagebox.showinfo("Success", "RSSI values read successfully")
    
    def _read_rssi_after(self):
        """Read RSSI values after test"""
        if not (self.sender_connection and self.sender_connection.is_open):
            messagebox.showwarning("Warning", "Sender not connected")
            return
        
        if not (self.receiver_connection and self.receiver_connection.is_open):
            messagebox.showwarning("Warning", "Receiver not connected")
            return
        
        self.rssi_after['sender'] = self._read_rssi("Sender", self.sender_connection)
        time.sleep(0.5)
        self.rssi_after['receiver'] = self._read_rssi("Receiver", self.receiver_connection)
        
        # Update statistics display
        self.root.after(0, self._update_statistics)
        messagebox.showinfo("Success", "RSSI values read successfully")
    
    def _create_packet(self, sequence: int, payload: bytes) -> bytes:
        """Create a test packet with sequence, timestamp, hash, and payload"""
        # Packet structure: [sequence(4), timestamp(8), hash(32), payload(variable)]
        timestamp = time.time()
        
        # Calculate hash of payload
        payload_hash = hashlib.sha256(payload).digest()
        
        # Pack header: sequence (4 bytes) + timestamp (8 bytes) + hash (32 bytes)
        header = struct.pack('!I', sequence) + struct.pack('!d', timestamp) + payload_hash
        
        return header + payload
    
    def _parse_packet(self, data: bytes) -> Optional[Tuple[int, float, bytes, bytes]]:
        """Parse packet and return (sequence, timestamp, hash, payload)"""
        if len(data) < self.packet_header_size:
            return None
        
        try:
            sequence = struct.unpack('!I', data[0:4])[0]
            timestamp = struct.unpack('!d', data[4:12])[0]
            packet_hash = data[12:44]
            payload = data[44:]
            
            return (sequence, timestamp, packet_hash, payload)
        except:
            return None
    
    def _verify_packet(self, packet_data: Tuple[int, float, bytes, bytes]) -> bool:
        """Verify packet integrity using hash"""
        sequence, timestamp, packet_hash, payload = packet_data
        
        # Recalculate hash
        calculated_hash = hashlib.sha256(payload).digest()
        
        return packet_hash == calculated_hash
    
    def _monitor_test_end(self):
        """Monitor thread to auto-stop test when time period ends or packet count reached"""
        try:
            use_packet_count = (self.target_packets is not None and self.target_packets > 0)
            
            while self.test_running:
                if use_packet_count:
                    # Check if target packets have been sent
                    total_sent = self.stats.get('packets_sent', 0) + self.stats.get('packets_sent_2', 0)
                    if total_sent >= self.target_packets:
                        self._log(f"Target of {self.target_packets} packets sent - waiting for reception (max 1s)...")
                        # Capture end_time NOW (when target packets are sent) - this won't be extended
                        packet_count_end_time = time.time()
                        self.stats['end_time'] = packet_count_end_time
                        
                        # Stop sending but wait for reception
                        self.test_running = False
                        
                        # Wait up to 1 second for packets to be received
                        wait_start = time.time()
                        wait_timeout = 1.0
                        direction = self.direction_var.get()
                        
                        while time.time() - wait_start < wait_timeout:
                            if direction == "Bidirectional":
                                total_received = self.stats.get('packets_received', 0) + self.stats.get('packets_received_2', 0)
                            else:
                                total_received = self.stats.get('packets_received', 0)
                            
                            if total_received >= self.target_packets:
                                self._log(f"All {self.target_packets} packets received")
                                break
                            time.sleep(0.05)  # Check every 50ms
                        
                        # Now actually stop the test
                        self._log(f"Auto-stopping after packet-count wait...")
                        self.root.after(0, self._stop_test)
                        break
                elif self.test_end_time:
                    # Check time-based stopping
                    if time.time() >= self.test_end_time:
                        self._log("Test period ended - auto-stopping...")
                        self.root.after(0, self._stop_test)
                        break
                time.sleep(0.1)
        except Exception as e:
            self._log(f"Monitor thread error: {str(e)}")
    
    def _sender_thread(self, conn: serial.Serial, stats_key: str = '', total_size: int = None, write_freq: float = None, test_length: float = None, target_packets: int = None):
        """Thread for sending packets"""
        try:
            # Use provided parameters if given, otherwise read from GUI (for backward compatibility)
            if total_size is None:
                total_size = int(self.write_size_var.get())
            if write_freq is None:
                write_freq = float(self.write_freq_var.get())
            if test_length is None:
                test_length = float(self.test_length_var.get())
            
            # Clear any stale data from serial buffer at sender thread start
            if conn and conn.is_open:
                try:
                    # Reset input buffer
                    conn.reset_input_buffer()
                    # Reset and flush output buffer
                    conn.reset_output_buffer()
                    conn.flush()
                except Exception as e:
                    self._log(f"Sender{stats_key}: Warning - error clearing buffer: {str(e)}")
            
            sequence = 0
            end_time = time.time() + test_length if test_length else None
            use_packet_count = (target_packets is not None and target_packets > 0)
            
            bytes_key = f'bytes_sent{stats_key}'
            packets_key = f'packets_sent{stats_key}'
            
            payload_size = max(total_size - self.packet_header_size, 0)
            if use_packet_count:
                self._log(f"Starting sender{stats_key}: total {total_size} bytes (payload {payload_size}) every {write_freq}s for {target_packets} packets")
            else:
                self._log(f"Starting sender{stats_key}: total {total_size} bytes (payload {payload_size}) every {write_freq}s for {test_length}s")
            self._log(f"Packet header: {self.packet_header_size} bytes; Total packet size: {total_size} bytes")
            
            # Track timing to ensure accurate write frequency
            next_packet_time = time.time()
            
            while self.test_running:
                # Check stopping conditions
                if use_packet_count:
                    # Check if we've sent enough packets
                    if self.stats[packets_key] >= target_packets:
                        self._log(f"Sender{stats_key} reached target of {target_packets} packets")
                        break
                else:
                    # Check if time limit reached
                    if end_time and time.time() >= end_time:
                        break
                
                # Wait until it's time for the next packet (ensures accurate timing)
                current_time = time.time()
                sleep_time = next_packet_time - current_time
                if sleep_time > 0:
                    time.sleep(sleep_time)
                elif sleep_time < -0.001:  # Warn if we're significantly behind schedule
                    self._log(f"Sender{stats_key}: Warning - behind schedule by {-sleep_time:.3f}s")
                
                # Record packet start time
                packet_start_time = time.time()
                
                # Generate payload (random data)
                payload = bytes([(sequence + i) % 256 for i in range(payload_size)])
                
                # Create packet
                packet = self._create_packet(sequence, payload)
                
                # Send packet
                if conn and conn.is_open:
                    conn.write(packet)
                    conn.flush()  # Ensure packet is sent immediately
                    # Count full on-wire packet size (header + payload)
                    self.stats[bytes_key] += len(packet)
                    self.stats[packets_key] += 1
                    sequence += 1
                
                # Calculate next packet time (write_freq after the START of this packet)
                next_packet_time = packet_start_time + write_freq
                
            self._log(f"Sender{stats_key} finished")
            
        except Exception as e:
            self._log(f"Sender{stats_key} error: {str(e)}")
            self.test_running = False
    
    def _receiver_thread(self, conn: serial.Serial, stats_key: str = '', expected_packet_size: int = None, test_length: float = None, target_packets: int = None):
        """Thread for receiving packets"""
        try:
            # Use provided parameters if given, otherwise read from GUI (for backward compatibility)
            if expected_packet_size is None:
                expected_packet_size = int(self.write_size_var.get())
            if test_length is None:
                test_length = float(self.test_length_var.get())
            end_time = time.time() + test_length if test_length else None
            use_packet_count = (target_packets is not None and target_packets > 0)
            buffer = b''
            
            bytes_key = f'bytes_received{stats_key}'
            bytes_valid_key = f'bytes_received_valid{stats_key}'
            bytes_total_key = f'bytes_received_total{stats_key}'
            packets_key = f'packets_received{stats_key}'
            corrupt_key = f'packets_corrupt{stats_key}'
            latency_key = f'latency_samples{stats_key}'
            
            # Clear any stale data from serial buffer at receiver thread start
            if conn and conn.is_open:
                try:
                    # Read any pending data
                    if conn.in_waiting > 0:
                        discarded = conn.read(conn.in_waiting)
                        self._log(f"Receiver{stats_key}: Cleared {len(discarded)} bytes from buffer at start")
                    # Reset input buffer
                    conn.reset_input_buffer()
                    # Flush output buffer
                    conn.reset_output_buffer()
                    conn.flush()
                except Exception as e:
                    self._log(f"Receiver{stats_key}: Warning - error clearing buffer: {str(e)}")
            
            self._log(f"Starting receiver{stats_key}")
            
            # Continue during normal test, grace period (500ms), or packet-count wait (1s)
            while (self.test_running or 
                   (self.receiver_grace_period_end and time.time() < self.receiver_grace_period_end) or
                   (self.packet_count_wait_end and time.time() < self.packet_count_wait_end)):
                # Check stopping conditions (only during normal test, not grace/wait periods)
                if self.test_running:
                    if use_packet_count:
                        # Check if we've received enough packets
                        # Note: For packet-count mode, we stop when sender has sent target packets
                        # The receiver will continue until sender stops (test_running becomes False)
                        # But we can also check if we've received enough packets (in case we're ahead)
                        packets_received = self.stats[packets_key]
                        if packets_received >= target_packets:
                            # We've received enough, but let sender finish to match its count
                            break
                    else:
                        # Check if time limit reached
                        if end_time and time.time() >= end_time:
                            break
                
                if conn and conn.is_open:
                    if conn.in_waiting > 0:
                        buffer += conn.read(conn.in_waiting)
                        
                        # Try to find complete packets
                        while len(buffer) >= expected_packet_size:
                            # Parse packet
                            packet_data = self._parse_packet(buffer[:expected_packet_size])
                            
                            if packet_data:
                                sequence, send_timestamp, packet_hash, payload = packet_data
                                
                                # Calculate latency
                                receive_timestamp = time.time()
                                latency = receive_timestamp - send_timestamp
                                
                                # Verify packet
                                packet_size = len(buffer[:expected_packet_size])
                                # Always count total on-wire bytes (all packets)
                                self.stats[bytes_total_key] += packet_size
                                
                                # Track if we received data during grace period (not for packet-count wait)
                                if not self.test_running and self.receiver_grace_period_end and not self.packet_count_wait_end:
                                    self.grace_period_data_received = True
                                
                                if self._verify_packet(packet_data):
                                    self.stats[packets_key] += 1
                                    self.stats[bytes_valid_key] += packet_size  # Only valid packets (full packet)
                                    self.stats[bytes_key] += packet_size  # Backward compatibility field reflects full packet
                                    self.stats[latency_key].append(latency)
                                else:
                                    self.stats[corrupt_key] += 1
                                    self.stats[packets_key] += 1  # Still count as received
                                    # bytes_valid_key not incremented for corrupt packets
                                
                                # Remove processed packet from buffer
                                buffer = buffer[expected_packet_size:]
                            else:
                                # Invalid packet, skip one byte and try again
                                buffer = buffer[1:]
                    else:
                        time.sleep(0.001)  # Small sleep when no data
                else:
                    time.sleep(0.1)
            
            self._log(f"Receiver{stats_key} finished")
            
        except Exception as e:
            self._log(f"Receiver{stats_key} error: {str(e)}")
            self.test_running = False
    
    def _update_statistics(self):
        """Update statistics display"""
        if not self.test_running and self.stats['start_time'] is None:
            return
        
        direction = self.direction_var.get()
        
        # Use stored rates if test is stopped, otherwise calculate in real-time
        if not self.test_running and self.stats['elapsed_time'] is not None:
            # Test stopped - use stored calculated rates (single source of truth)
            if direction == "Bidirectional":
                if self.stats['data_rate_total_bps_combined'] is not None:
                    self.stats_labels['data_rate_total'].config(
                        text=f"{self.stats['data_rate_total_bps_combined']:.2f} bps ({self.stats['data_rate_total_kbps_combined']:.2f} kbps) [Bidirectional]")
                else:
                    self.stats_labels['data_rate_total'].config(text="0 bps")
                
                if self.stats['data_rate_valid_bps_combined'] is not None:
                    self.stats_labels['data_rate_valid'].config(
                        text=f"{self.stats['data_rate_valid_bps_combined']:.2f} bps ({self.stats['data_rate_valid_kbps_combined']:.2f} kbps) [Bidirectional]")
                else:
                    self.stats_labels['data_rate_valid'].config(text="0 bps")
                
                # Send rate (bidirectional)
                if self.stats['send_rate_bps_combined'] is not None:
                    self.stats_labels['send_rate'].config(
                        text=f"{self.stats['send_rate_bps_combined']:.2f} bps ({self.stats['send_rate_kbps_combined']:.2f} kbps) [Bidirectional]")
                else:
                    self.stats_labels['send_rate'].config(text="0 bps")
            else:
                if self.stats['data_rate_total_bps'] is not None:
                    self.stats_labels['data_rate_total'].config(
                        text=f"{self.stats['data_rate_total_bps']:.2f} bps ({self.stats['data_rate_total_kbps']:.2f} kbps)")
                else:
                    self.stats_labels['data_rate_total'].config(text="0 bps")
                
                if self.stats['data_rate_valid_bps'] is not None:
                    self.stats_labels['data_rate_valid'].config(
                        text=f"{self.stats['data_rate_valid_bps']:.2f} bps ({self.stats['data_rate_valid_kbps']:.2f} kbps)")
                else:
                    self.stats_labels['data_rate_valid'].config(text="0 bps")
                
                # Send rate
                if self.stats['send_rate_bps'] is not None:
                    self.stats_labels['send_rate'].config(
                        text=f"{self.stats['send_rate_bps']:.2f} bps ({self.stats['send_rate_kbps']:.2f} kbps)")
                else:
                    self.stats_labels['send_rate'].config(text="0 bps")
        else:
            # Test running - calculate in real-time
            elapsed = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
            
            if elapsed > 0:
                if direction == "Bidirectional":
                    # Total rate (includes corrupt packets)
                    total_bytes1 = self.stats['bytes_received_total']
                    total_bytes2 = self.stats['bytes_received_total_2']
                    total_bytes = total_bytes1 + total_bytes2
                    total_rate_bps = (total_bytes / elapsed) * 8
                    total_rate_kbps = total_rate_bps / 1000
                    self.stats_labels['data_rate_total'].config(
                        text=f"{total_rate_bps:.2f} bps ({total_rate_kbps:.2f} kbps) [Bidirectional]")
                    
                    # Valid rate (only valid packets)
                    valid_bytes1 = self.stats['bytes_received_valid']
                    valid_bytes2 = self.stats['bytes_received_valid_2']
                    valid_bytes = valid_bytes1 + valid_bytes2
                    valid_rate_bps = (valid_bytes / elapsed) * 8
                    valid_rate_kbps = valid_rate_bps / 1000
                    self.stats_labels['data_rate_valid'].config(
                        text=f"{valid_rate_bps:.2f} bps ({valid_rate_kbps:.2f} kbps) [Bidirectional]")
                    
                    # Send rate (bidirectional)
                    sent_bytes1 = self.stats['bytes_sent']
                    sent_bytes2 = self.stats['bytes_sent_2']
                    sent_bytes = sent_bytes1 + sent_bytes2
                    send_rate_bps = (sent_bytes / elapsed) * 8
                    send_rate_kbps = send_rate_bps / 1000
                    self.stats_labels['send_rate'].config(
                        text=f"{send_rate_bps:.2f} bps ({send_rate_kbps:.2f} kbps) [Bidirectional]")
                else:
                    # Total rate (includes corrupt packets)
                    total_bytes = self.stats['bytes_received_total']
                    total_rate_bps = (total_bytes / elapsed) * 8
                    total_rate_kbps = total_rate_bps / 1000
                    self.stats_labels['data_rate_total'].config(
                        text=f"{total_rate_bps:.2f} bps ({total_rate_kbps:.2f} kbps)")
                    
                    # Valid rate (only valid packets)
                    valid_bytes = self.stats['bytes_received_valid']
                    valid_rate_bps = (valid_bytes / elapsed) * 8
                    valid_rate_kbps = valid_rate_bps / 1000
                    self.stats_labels['data_rate_valid'].config(
                        text=f"{valid_rate_bps:.2f} bps ({valid_rate_kbps:.2f} kbps)")
                    
                    # Send rate (unidirectional)
                    sent_bytes = self.stats['bytes_sent']
                    send_rate_bps = (sent_bytes / elapsed) * 8
                    send_rate_kbps = send_rate_bps / 1000
                    self.stats_labels['send_rate'].config(
                        text=f"{send_rate_bps:.2f} bps ({send_rate_kbps:.2f} kbps)")
            else:
                self.stats_labels['data_rate_total'].config(text="0 bps")
                self.stats_labels['data_rate_valid'].config(text="0 bps")
                self.stats_labels['send_rate'].config(text="0 bps")
        
        # Use stored elapsed time if available, otherwise calculate
        elapsed = self.stats['elapsed_time'] if (not self.test_running and self.stats['elapsed_time'] is not None) else (time.time() - self.stats['start_time'] if self.stats['start_time'] else 0)
        
        # Test duration (use stored elapsed time if available)
        elapsed_display = self.stats['elapsed_time'] if (not self.test_running and self.stats['elapsed_time'] is not None) else elapsed
        self.stats_labels['test_duration'].config(text=f"{elapsed_display:.2f} s")
        
        # Packet statistics (combined for bidirectional)
        if direction == "Bidirectional":
            total_sent = self.stats['packets_sent'] + self.stats['packets_sent_2']
            total_received = self.stats['packets_received'] + self.stats['packets_received_2']
            self.stats_labels['packets_sent'].config(text=f"{total_sent} (Bidirectional)")
            self.stats_labels['packets_received'].config(text=f"{total_received} (Bidirectional)")
        else:
            self.stats_labels['packets_sent'].config(text=str(self.stats['packets_sent']))
            self.stats_labels['packets_received'].config(text=str(self.stats['packets_received']))
        
        # Packet loss rate
        if direction == "Bidirectional":
            total_sent = self.stats['packets_sent'] + self.stats['packets_sent_2']
            total_received = self.stats['packets_received'] + self.stats['packets_received_2']
            if total_sent > 0:
                loss_rate = ((total_sent - total_received) / total_sent) * 100
                self.stats_labels['packet_loss'].config(text=f"{loss_rate:.2f}% (Bidirectional)")
            else:
                self.stats_labels['packet_loss'].config(text="N/A")
        else:
            if self.stats['packets_sent'] > 0:
                loss_rate = ((self.stats['packets_sent'] - self.stats['packets_received']) / 
                            self.stats['packets_sent']) * 100
                self.stats_labels['packet_loss'].config(text=f"{loss_rate:.2f}%")
            else:
                self.stats_labels['packet_loss'].config(text="N/A")
        
        # Corrupt packet rate
        if direction == "Bidirectional":
            total_received = self.stats['packets_received'] + self.stats['packets_received_2']
            total_corrupt = self.stats['packets_corrupt'] + self.stats['packets_corrupt_2']
            if total_received > 0:
                corrupt_rate = (total_corrupt / total_received) * 100
                self.stats_labels['corrupt_rate'].config(text=f"{corrupt_rate:.2f}% (Bidirectional)")
            else:
                self.stats_labels['corrupt_rate'].config(text="N/A")
        else:
            if self.stats['packets_received'] > 0:
                corrupt_rate = (self.stats['packets_corrupt'] / self.stats['packets_received']) * 100
                self.stats_labels['corrupt_rate'].config(text=f"{corrupt_rate:.2f}%")
            else:
                self.stats_labels['corrupt_rate'].config(text="N/A")
        
        # Latency statistics (combined for bidirectional)
        if direction == "Bidirectional":
            combined_latency = list(self.stats['latency_samples']) + list(self.stats['latency_samples_2'])
            if combined_latency:
                avg_latency = sum(combined_latency) / len(combined_latency)
                min_latency = min(combined_latency)
                max_latency = max(combined_latency)
                self.stats_labels['avg_latency'].config(text=f"{avg_latency*1000:.2f} ms (Bidirectional)")
                self.stats_labels['min_latency'].config(text=f"{min_latency*1000:.2f} ms")
                self.stats_labels['max_latency'].config(text=f"{max_latency*1000:.2f} ms")
            else:
                self.stats_labels['avg_latency'].config(text="N/A")
                self.stats_labels['min_latency'].config(text="N/A")
                self.stats_labels['max_latency'].config(text="N/A")
        else:
            if self.stats['latency_samples']:
                avg_latency = sum(self.stats['latency_samples']) / len(self.stats['latency_samples'])
                min_latency = min(self.stats['latency_samples'])
                max_latency = max(self.stats['latency_samples'])
                
                self.stats_labels['avg_latency'].config(text=f"{avg_latency*1000:.2f} ms")
                self.stats_labels['min_latency'].config(text=f"{min_latency*1000:.2f} ms")
                self.stats_labels['max_latency'].config(text=f"{max_latency*1000:.2f} ms")
            else:
                self.stats_labels['avg_latency'].config(text="N/A")
                self.stats_labels['min_latency'].config(text="N/A")
                self.stats_labels['max_latency'].config(text="N/A")
        
        # Test duration
        self.stats_labels['test_duration'].config(text=f"{elapsed:.2f} s")
        
        # Bytes (combined for bidirectional)
        if direction == "Bidirectional":
            total_sent = self.stats['bytes_sent'] + self.stats['bytes_sent_2']
            total_received_total = self.stats['bytes_received_total'] + self.stats['bytes_received_total_2']
            total_received_valid = self.stats['bytes_received_valid'] + self.stats['bytes_received_valid_2']
            self.stats_labels['bytes_sent'].config(text=f"{total_sent} (Bidirectional)")
            self.stats_labels['bytes_received_total'].config(text=f"{total_received_total} (Bidirectional)")
            self.stats_labels['bytes_received_valid'].config(text=f"{total_received_valid} (Bidirectional)")
        else:
            self.stats_labels['bytes_sent'].config(text=str(self.stats['bytes_sent']))
            self.stats_labels['bytes_received_total'].config(text=str(self.stats['bytes_received_total']))
            self.stats_labels['bytes_received_valid'].config(text=str(self.stats['bytes_received_valid']))
        
        # RSSI values
        rssi_before_s = self.rssi_before['sender']
        rssi_after_s = self.rssi_after['sender']
        rssi_before_r = self.rssi_before['receiver']
        rssi_after_r = self.rssi_after['receiver']
        
        if rssi_before_s['S123'] is not None and rssi_before_s['S124'] is not None:
            self.stats_labels['rssi_before_sender'].config(
                text=f"Master: {rssi_before_s['S123']} dBm, Slave: {rssi_before_s['S124']} dBm")
        else:
            self.stats_labels['rssi_before_sender'].config(text="Not measured")
            
        if rssi_after_s['S123'] is not None and rssi_after_s['S124'] is not None:
            self.stats_labels['rssi_after_sender'].config(
                text=f"Master: {rssi_after_s['S123']} dBm, Slave: {rssi_after_s['S124']} dBm")
        else:
            self.stats_labels['rssi_after_sender'].config(text="Not measured")
            
        if rssi_before_r['S123'] is not None and rssi_before_r['S124'] is not None:
            self.stats_labels['rssi_before_receiver'].config(
                text=f"Master: {rssi_before_r['S123']} dBm, Slave: {rssi_before_r['S124']} dBm")
        else:
            self.stats_labels['rssi_before_receiver'].config(text="Not measured")
            
        if rssi_after_r['S123'] is not None and rssi_after_r['S124'] is not None:
            self.stats_labels['rssi_after_receiver'].config(
                text=f"Master: {rssi_after_r['S123']} dBm, Slave: {rssi_after_r['S124']} dBm")
        else:
            self.stats_labels['rssi_after_receiver'].config(text="Not measured")
        
        # Schedule next update
        if self.test_running:
            self.root.after(100, self._update_statistics)
    
    def _start_test(self):
        """Start the data rate test"""
        try:
            # Get parameters based on input mode
            input_mode = self.input_mode_var.get()
            speed_kbps = None  # Initialize for logging
            target_packets = None  # Initialize for packet-count mode
            
            if input_mode == "Manual":
                total_size = int(self.write_size_var.get())
                write_freq = float(self.write_freq_var.get())
                test_length = float(self.test_length_var.get())
            elif input_mode == "Speed-Based":
                total_size = int(self.buffer_size_var.get())
                test_length = float(self.duration_var.get())
                # Calculate write frequency from speed
                speed_kbps = float(self.desired_speed_var.get())
                bytes_per_second = (speed_kbps * 1000) / 8
                write_freq = total_size / bytes_per_second
            else:  # Packet-Count
                total_size = int(self.packet_count_size_var.get())
                write_freq = float(self.packet_count_freq_var.get())
                target_packets = int(self.num_packets_var.get())
                test_length = None  # No time limit for packet-count mode
            
            # Validate
            if total_size < (self.packet_header_size + 1):
                messagebox.showerror("Error", f"Total packet size must be at least {self.packet_header_size + 1} bytes")
                return
            
            if write_freq <= 0:
                messagebox.showerror("Error", "Write frequency must be greater than 0")
                return
            
            if test_length is not None and test_length <= 0:
                messagebox.showerror("Error", "Test length must be greater than 0")
                return
            
            if target_packets is not None and target_packets <= 0:
                messagebox.showerror("Error", "Number of packets must be greater than 0")
                return
            
            # Check connections
            if not (self.sender_connection and self.sender_connection.is_open):
                messagebox.showerror("Error", "Sender not connected")
                return
            
            if not (self.receiver_connection and self.receiver_connection.is_open):
                messagebox.showerror("Error", "Receiver not connected")
                return
            
            # Clear all serial port buffers before starting test
            self._clear_serial_buffers()
            
            # Reset statistics (start_time will be set when test actually starts)
            direction = self.direction_var.get()
            self.stats = {
                'bytes_sent': 0,
                'bytes_received': 0,
                'bytes_received_valid': 0,
                'bytes_received_total': 0,
                'packets_sent': 0,
                'packets_received': 0,
                'packets_corrupt': 0,
                'latency_samples': deque(maxlen=1000),
                'start_time': None,  # Will be set when test actually starts (after RSSI reading)
                'end_time': None,
                # Calculated rates (single source of truth)
                'data_rate_total_bps': None,
                'data_rate_total_kbps': None,
                'data_rate_valid_bps': None,
                'data_rate_valid_kbps': None,
                'send_rate_bps': None,
                'send_rate_kbps': None,
                'elapsed_time': None,
                # For bidirectional mode
                'bytes_sent_2': 0,
                'bytes_received_2': 0,
                'bytes_received_valid_2': 0,
                'bytes_received_total_2': 0,
                'packets_sent_2': 0,
                'packets_received_2': 0,
                'packets_corrupt_2': 0,
                'latency_samples_2': deque(maxlen=1000),
                # Bidirectional calculated rates
                'data_rate_total_bps_1': None,
                'data_rate_total_kbps_1': None,
                'data_rate_valid_bps_1': None,
                'data_rate_valid_kbps_1': None,
                'data_rate_total_bps_2': None,
                'data_rate_total_kbps_2': None,
                'data_rate_valid_bps_2': None,
                'data_rate_valid_kbps_2': None,
                'data_rate_total_bps_combined': None,
                'data_rate_total_kbps_combined': None,
                'data_rate_valid_bps_combined': None,
                'data_rate_valid_kbps_combined': None,
                # Send rate for bidirectional mode
                'send_rate_bps_1': None,
                'send_rate_kbps_1': None,
                'send_rate_bps_2': None,
                'send_rate_kbps_2': None,
                'send_rate_bps_combined': None,
                'send_rate_kbps_combined': None
            }
            
            # Read RSSI before test if enabled (before timer starts)
            if self.auto_rssi_before_var.get():
                self._log("Auto-reading RSSI before test...")
                self.rssi_before['sender'] = self._read_rssi("Sender", self.sender_connection)
                time.sleep(0.5)
                self.rssi_before['receiver'] = self._read_rssi("Receiver", self.receiver_connection)
                # Update statistics display
                self.root.after(0, self._update_statistics)
            
            # Start test - timer starts NOW (after RSSI reading, before data transfer)
            self.test_running = True
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.target_packets = target_packets  # Store for monitor thread
            
            # Note: total_size, write_freq, test_length, and target_packets are already calculated above based on input mode
            
            # Log test parameters
            if input_mode == "Manual":
                self._log(f"Starting test: Manual mode")
                self._log(f"Total packet size: {total_size} bytes")
                self._log(f"Write frequency: {write_freq} s")
                self._log(f"Test length: {test_length} s")
            elif input_mode == "Speed-Based":
                self._log(f"Starting test: Speed-based mode")
                self._log(f"Total packet size: {total_size} bytes")
                self._log(f"Desired speed: {speed_kbps} kbps")
                self._log(f"Calculated write frequency: {write_freq:.6f} s")
                self._log(f"Test length: {test_length} s")
            else:  # Packet-Count
                self._log(f"Starting test: Packet-count mode")
                self._log(f"Total packet size: {total_size} bytes")
                self._log(f"Write frequency: {write_freq} s")
                self._log(f"Number of packets: {target_packets}")
            
            # Start threads based on direction - pass calculated parameters
            if direction == "Bidirectional":
                # Both sides send and receive simultaneously
                self.test_thread = threading.Thread(target=self._sender_thread, 
                                                   args=(self.sender_connection, '', total_size, write_freq, test_length, target_packets), daemon=True)
                self.receive_thread = threading.Thread(target=self._receiver_thread, 
                                                       args=(self.receiver_connection, '', total_size, test_length, target_packets), daemon=True)
                self.sender2_thread = threading.Thread(target=self._sender_thread, 
                                                      args=(self.receiver_connection, '_2', total_size, write_freq, test_length, target_packets), daemon=True)
                self.receiver2_thread = threading.Thread(target=self._receiver_thread, 
                                                        args=(self.sender_connection, '_2', total_size, test_length, target_packets), daemon=True)
                
                self.test_thread.start()
                self.receive_thread.start()
                self.sender2_thread.start()
                self.receiver2_thread.start()
                
                self._log("Starting bidirectional test (both sides sending and receiving)")
                
            elif direction == "Sender → Receiver":
                # Only sender sends, only receiver receives
                self.test_thread = threading.Thread(target=self._sender_thread, 
                                                   args=(self.sender_connection, '', total_size, write_freq, test_length, target_packets), daemon=True)
                self.receive_thread = threading.Thread(target=self._receiver_thread, 
                                                       args=(self.receiver_connection, '', total_size, test_length, target_packets), daemon=True)
                
                self.test_thread.start()
                self.receive_thread.start()
                
                self._log("Starting unidirectional test: Sender → Receiver")
                
            elif direction == "Receiver → Sender":
                # Only receiver sends, only sender receives
                self.test_thread = threading.Thread(target=self._sender_thread, 
                                                   args=(self.receiver_connection, '', total_size, write_freq, test_length, target_packets), daemon=True)
                self.receive_thread = threading.Thread(target=self._receiver_thread, 
                                                       args=(self.sender_connection, '', total_size, test_length, target_packets), daemon=True)
                
                self.test_thread.start()
                self.receive_thread.start()
                
                self._log("Starting unidirectional test: Receiver → Sender")
            
            # Start timer NOW - after threads are started, when data actually starts flowing
            self.stats['start_time'] = time.time()
            if test_length is not None:
                self.test_end_time = self.stats['start_time'] + test_length
            else:
                self.test_end_time = None  # No time limit for packet-count mode
            
            # Start monitor thread to auto-stop test
            self.monitor_thread = threading.Thread(target=self._monitor_test_end, daemon=True)
            self.monitor_thread.start()
            
            if target_packets:
                self._log(f"Test started - timer started")
                self._log(f"Test will auto-stop after {target_packets} packets are sent")
            else:
                self._log(f"Test started - timer started")
                self._log(f"Test will auto-stop after {test_length} seconds")
            
            # Start statistics updates
            self._update_statistics()
            
            self._log("=" * 50)
            if input_mode == "Manual":
                self._log(f"Starting test: Manual mode")
                self._log(f"Total packet size: {total_size} bytes")
                self._log(f"Write frequency: {write_freq} s")
            else:
                self._log(f"Starting test: Speed-based mode")
                self._log(f"Total packet size: {total_size} bytes")
                self._log(f"Desired speed: {speed_kbps} kbps")
                self._log(f"Calculated write frequency: {write_freq:.6f} s")
            self._log("Test started - timer started")
            self._log(f"Test will auto-stop after {test_length} seconds")
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid parameter: {str(e)}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start test: {str(e)}")
            self._log(f"Test start error: {str(e)}")
    
    def _stop_test(self):
        """Stop the data rate test"""
        self.test_running = False
        self.test_end_time = None  # Reset end time
        
        # Check if this is packet-count mode
        use_packet_count = (self.target_packets is not None and self.target_packets > 0)
        
        # Stop timer NOW - before RSSI reading
        # For packet-count mode, end_time was already set in monitor thread when packets were sent
        # For other modes, we capture the time now
        if not use_packet_count:
            initial_end_time = time.time()
            self.stats['end_time'] = initial_end_time
        else:
            # For packet-count mode, end_time is already set, use it as initial
            initial_end_time = self.stats['end_time']
        
        # Wait for sender threads to finish
        if self.test_thread:
            self.test_thread.join(timeout=2)
        if self.sender2_thread:
            self.sender2_thread.join(timeout=2)
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        
        if use_packet_count:
            # For packet-count mode: wait up to 1 second for packets to be received
            # But don't extend elapsed_time (it's already set when test_running became False)
            self.packet_count_wait_end = initial_end_time + 1.0  # 1 second wait
            
            # Wait for receiver threads with 1 second wait period
            if self.receive_thread:
                self.receive_thread.join(timeout=2.0)  # Wait up to 2s (includes wait period)
            if self.receiver2_thread:
                self.receiver2_thread.join(timeout=2.0)
            
            # Keep original end_time (don't extend for packet-count mode)
            self.stats['end_time'] = initial_end_time
            self.packet_count_wait_end = None
        else:
            # For non-packet-count modes: use grace period (500ms)
            self.grace_period_data_received = False
            self.receiver_grace_period_end = initial_end_time + 0.5  # 500ms grace period
            
            # Wait for receiver threads with grace period
            if self.receive_thread:
                self.receive_thread.join(timeout=1.5)  # Wait up to 1.5s (includes grace period)
            if self.receiver2_thread:
                self.receiver2_thread.join(timeout=1.5)
            
            # Check if data was received during grace period
            if self.grace_period_data_received:
                # Extend end_time to include grace period
                self.stats['end_time'] = self.receiver_grace_period_end
                self._log("Data received during grace period - extending test duration by 500ms")
            else:
                # Keep original end_time
                self.stats['end_time'] = initial_end_time
            
            # Clear grace period flag
            self.receiver_grace_period_end = None
        
        # Clear any remaining data from buffers after test completes
        # This ensures clean state for next test
        try:
            if self.sender_connection and self.sender_connection.is_open:
                if self.sender_connection.in_waiting > 0:
                    discarded = self.sender_connection.read(self.sender_connection.in_waiting)
                    self._log_diag(f"Sender: Cleared {len(discarded)} bytes after test stop")
                self.sender_connection.reset_input_buffer()
                self.sender_connection.reset_output_buffer()
                self.sender_connection.flush()
            
            if self.receiver_connection and self.receiver_connection.is_open:
                if self.receiver_connection.in_waiting > 0:
                    discarded = self.receiver_connection.read(self.receiver_connection.in_waiting)
                    self._log_diag(f"Receiver: Cleared {len(discarded)} bytes after test stop")
                self.receiver_connection.reset_input_buffer()
                self.receiver_connection.reset_output_buffer()
                self.receiver_connection.flush()
        except Exception as e:
            self._log(f"Warning: Error clearing buffers after stop: {str(e)}")
        
        # Calculate data rates NOW (single source of truth)
        direction = self.direction_var.get()
        elapsed = self.stats['end_time'] - self.stats['start_time'] if self.stats['start_time'] else 0
        self.stats['elapsed_time'] = elapsed
        
        if elapsed > 0:
            if direction == "Bidirectional":
                # Calculate rates for direction 1
                total_bytes1 = self.stats['bytes_received_total']
                valid_bytes1 = self.stats['bytes_received_valid']
                self.stats['data_rate_total_bps_1'] = (total_bytes1 / elapsed) * 8
                self.stats['data_rate_total_kbps_1'] = self.stats['data_rate_total_bps_1'] / 1000
                self.stats['data_rate_valid_bps_1'] = (valid_bytes1 / elapsed) * 8
                self.stats['data_rate_valid_kbps_1'] = self.stats['data_rate_valid_bps_1'] / 1000
                
                # Calculate rates for direction 2
                total_bytes2 = self.stats['bytes_received_total_2']
                valid_bytes2 = self.stats['bytes_received_valid_2']
                self.stats['data_rate_total_bps_2'] = (total_bytes2 / elapsed) * 8
                self.stats['data_rate_total_kbps_2'] = self.stats['data_rate_total_bps_2'] / 1000
                self.stats['data_rate_valid_bps_2'] = (valid_bytes2 / elapsed) * 8
                self.stats['data_rate_valid_kbps_2'] = self.stats['data_rate_valid_bps_2'] / 1000
                
                # Calculate combined rates
                total_combined = total_bytes1 + total_bytes2
                valid_combined = valid_bytes1 + valid_bytes2
                self.stats['data_rate_total_bps_combined'] = (total_combined / elapsed) * 8
                self.stats['data_rate_total_kbps_combined'] = self.stats['data_rate_total_bps_combined'] / 1000
                self.stats['data_rate_valid_bps_combined'] = (valid_combined / elapsed) * 8
                self.stats['data_rate_valid_kbps_combined'] = self.stats['data_rate_valid_bps_combined'] / 1000
                
                # Calculate send rates for bidirectional
                sent_bytes1 = self.stats['bytes_sent']
                sent_bytes2 = self.stats['bytes_sent_2']
                self.stats['send_rate_bps_1'] = (sent_bytes1 / elapsed) * 8
                self.stats['send_rate_kbps_1'] = self.stats['send_rate_bps_1'] / 1000
                self.stats['send_rate_bps_2'] = (sent_bytes2 / elapsed) * 8
                self.stats['send_rate_kbps_2'] = self.stats['send_rate_bps_2'] / 1000
                sent_combined = sent_bytes1 + sent_bytes2
                self.stats['send_rate_bps_combined'] = (sent_combined / elapsed) * 8
                self.stats['send_rate_kbps_combined'] = self.stats['send_rate_bps_combined'] / 1000
            else:
                # Calculate rates for unidirectional
                total_bytes = self.stats['bytes_received_total']
                valid_bytes = self.stats['bytes_received_valid']
                self.stats['data_rate_total_bps'] = (total_bytes / elapsed) * 8
                self.stats['data_rate_total_kbps'] = self.stats['data_rate_total_bps'] / 1000
                self.stats['data_rate_valid_bps'] = (valid_bytes / elapsed) * 8
                self.stats['data_rate_valid_kbps'] = self.stats['data_rate_valid_bps'] / 1000
                
                # Calculate send rate for unidirectional
                sent_bytes = self.stats['bytes_sent']
                self.stats['send_rate_bps'] = (sent_bytes / elapsed) * 8
                self.stats['send_rate_kbps'] = self.stats['send_rate_bps'] / 1000
        
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self._update_button_states()
        
        # Read RSSI after test if enabled (after timer stopped)
        if self.auto_rssi_after_var.get():
            self._log("Auto-reading RSSI after test...")
            self.rssi_after['sender'] = self._read_rssi("Sender", self.sender_connection)
            time.sleep(0.5)
            self.rssi_after['receiver'] = self._read_rssi("Receiver", self.receiver_connection)
        
        # Final statistics update
        self.root.after(0, self._update_statistics)
        
        self._log("Test stopped")
        self._log("=" * 50)
        
        # Show summary using stored rates (single source of truth)
        if elapsed > 0:
            if direction == "Bidirectional":
                # Use stored calculated rates
                if self.stats['data_rate_total_bps_1'] is not None:
                    self._log(f"Direction 1 (Sender→Receiver):")
                    self._log(f"  Total: {self.stats['data_rate_total_bps_1']:.2f} bps ({self.stats['data_rate_total_kbps_1']:.2f} kbps)")
                    self._log(f"  Valid: {self.stats['data_rate_valid_bps_1']:.2f} bps ({self.stats['data_rate_valid_kbps_1']:.2f} kbps)")
                if self.stats['data_rate_total_bps_2'] is not None:
                    self._log(f"Direction 2 (Receiver→Sender):")
                    self._log(f"  Total: {self.stats['data_rate_total_bps_2']:.2f} bps ({self.stats['data_rate_total_kbps_2']:.2f} kbps)")
                    self._log(f"  Valid: {self.stats['data_rate_valid_bps_2']:.2f} bps ({self.stats['data_rate_valid_kbps_2']:.2f} kbps)")
                if self.stats['data_rate_total_bps_combined'] is not None:
                    self._log(f"Combined Total: {self.stats['data_rate_total_bps_combined']:.2f} bps ({self.stats['data_rate_total_kbps_combined']:.2f} kbps)")
                    self._log(f"Combined Valid: {self.stats['data_rate_valid_bps_combined']:.2f} bps ({self.stats['data_rate_valid_kbps_combined']:.2f} kbps)")
            else:
                # Use stored calculated rates
                if self.stats['data_rate_total_bps'] is not None:
                    self._log(f"Data Rate (Total): {self.stats['data_rate_total_bps']:.2f} bps ({self.stats['data_rate_total_kbps']:.2f} kbps)")
                    self._log(f"Data Rate (Valid): {self.stats['data_rate_valid_bps']:.2f} bps ({self.stats['data_rate_valid_kbps']:.2f} kbps)")
            
            if self.stats['packets_sent'] > 0:
                loss = ((self.stats['packets_sent'] - self.stats['packets_received']) / 
                       self.stats['packets_sent']) * 100
                self._log(f"Packet loss: {loss:.2f}%")
            if self.stats['packets_received'] > 0:
                corrupt = (self.stats['packets_corrupt'] / self.stats['packets_received']) * 100
                self._log(f"Corrupt packets: {corrupt:.2f}%")
            
            if direction == "Bidirectional" and self.stats['packets_sent_2'] > 0:
                loss2 = ((self.stats['packets_sent_2'] - self.stats['packets_received_2']) / 
                        self.stats['packets_sent_2']) * 100
                self._log(f"Direction 2 packet loss: {loss2:.2f}%")
            if direction == "Bidirectional" and self.stats['packets_received_2'] > 0:
                corrupt2 = (self.stats['packets_corrupt_2'] / self.stats['packets_received_2']) * 100
                self._log(f"Direction 2 corrupt packets: {corrupt2:.2f}%")
    
    def _clear_results(self):
        """Clear test results"""
        if self.test_running:
            messagebox.showwarning("Warning", "Please stop the test first")
            return
        
        self.target_packets = None
        self.test_end_time = None
        self.receiver_grace_period_end = None
        self.grace_period_data_received = False
        self.packet_count_wait_end = None
        self.stats = {
            'bytes_sent': 0,
            'bytes_received': 0,
            'bytes_received_valid': 0,
            'bytes_received_total': 0,
            'packets_sent': 0,
            'packets_received': 0,
            'packets_corrupt': 0,
            'latency_samples': deque(maxlen=1000),
            'start_time': None,
            'end_time': None,
            # Calculated rates (single source of truth)
            'data_rate_total_bps': None,
            'data_rate_total_kbps': None,
            'data_rate_valid_bps': None,
            'data_rate_valid_kbps': None,
            'send_rate_bps': None,
            'send_rate_kbps': None,
            'elapsed_time': None,
            # For bidirectional mode
            'bytes_sent_2': 0,
            'bytes_received_2': 0,
            'bytes_received_valid_2': 0,
            'bytes_received_total_2': 0,
            'packets_sent_2': 0,
            'packets_received_2': 0,
            'packets_corrupt_2': 0,
            'latency_samples_2': deque(maxlen=1000),
            # Bidirectional calculated rates
            'data_rate_total_bps_1': None,
            'data_rate_total_kbps_1': None,
            'data_rate_valid_bps_1': None,
            'data_rate_valid_kbps_1': None,
            'data_rate_total_bps_2': None,
            'data_rate_total_kbps_2': None,
            'data_rate_valid_bps_2': None,
            'data_rate_valid_kbps_2': None,
            'data_rate_total_bps_combined': None,
            'data_rate_total_kbps_combined': None,
            'data_rate_valid_bps_combined': None,
            'data_rate_valid_kbps_combined': None,
            # Send rate for bidirectional mode
            'send_rate_bps_1': None,
            'send_rate_kbps_1': None,
            'send_rate_bps_2': None,
            'send_rate_kbps_2': None,
            'send_rate_bps_combined': None,
            'send_rate_kbps_combined': None
        }
        
        self.rssi_before = {'sender': {'S123': None, 'S124': None}, 'receiver': {'S123': None, 'S124': None}}
        self.rssi_after = {'sender': {'S123': None, 'S124': None}, 'receiver': {'S123': None, 'S124': None}}
        
        for label in self.stats_labels.values():
            label.config(text="N/A")
        
        self.log_text.delete(1.0, tk.END)
        self._log("Results cleared")


def main():
    root = tk.Tk()
    app = T900DataRateTest(root)
    root.mainloop()


if __name__ == "__main__":
    main()

