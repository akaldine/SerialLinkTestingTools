#!/usr/bin/env python3
"""
Tianze T900 Data Rate Test Tool (PyQt5 Version)
Tests end-to-end data rate, packet corruption, and latency between two T900 radios.
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QGroupBox,
                             QGridLayout, QSplitter, QMessageBox, QCheckBox, QFrame)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QTimer, QMutex
from PyQt5.QtGui import QFont, QColor
import serial
import serial.tools.list_ports
import threading
import time
import struct
import hashlib
from collections import deque
from typing import Optional, Tuple, List
from datetime import datetime


class T900DataRateTestQt(QMainWindow):
    log_signal = pyqtSignal(str)
    def __init__(self):
        super().__init__()
        self.setWindowTitle("T900 Data Rate Test Tool")
        self.setGeometry(100, 100, 1200, 800)
        
        self.sender_connection: Optional[serial.Serial] = None
        self.num_receivers = 3
        self.receiver_connections: List[Optional[serial.Serial]] = [None] * self.num_receivers
        
        self.test_running = False
        self.test_end_time = None
        self.target_packets = None
        self.receiver_grace_period_end = None
        self.grace_period_data_received = False
        self.packet_count_wait_end = None
        self.test_thread: Optional[threading.Thread] = None
        self.receiver_threads: List[Optional[threading.Thread]] = [None] * self.num_receivers
        self.monitor_thread: Optional[threading.Thread] = None
        
        # RSSI values (current readings)
        self.rssi_current = {
            'sender': {'S123': None, 'S124': None},
            'receivers': [{'S123': None, 'S124': None} for _ in range(self.num_receivers)]
        }
        
        # Test statistics
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
            'data_rate_total_bps': None,
            'data_rate_total_kbps': None,
            'data_rate_valid_bps': None,
            'data_rate_valid_kbps': None,
            'elapsed_time': None,
            'send_rate_bps': None,
            'send_rate_kbps': None,
            # Bidirectional stats
            'bytes_sent_2': 0,
            'bytes_received_2': 0,
            'bytes_received_valid_2': 0,
            'bytes_received_total_2': 0,
            'packets_sent_2': 0,
            'packets_received_2': 0,
            'packets_corrupt_2': 0,
            'latency_samples_2': deque(maxlen=1000),
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
        
        # Per-receiver statistics (for multi-receiver display)
        self.receiver_stats: List[dict] = []
        for _ in range(self.num_receivers):
            self.receiver_stats.append({
                'bytes_received_total': 0,
                'bytes_received_valid': 0,
                'packets_received': 0,
                'packets_corrupt': 0,
                'latency_samples': deque(maxlen=1000),
                'valid_rate_bps': None,
                'valid_rate_kbps': None,
                'packet_loss': None,
                'avg_latency': None,
            })
        
        self.packet_header_size = 44  # 4 + 8 + 32
        
        self.stats_mutex = QMutex()
        
        # Receiver UI element tracking
        self.receiver_port_combos: List[QComboBox] = []
        self.receiver_baud_combos: List[QComboBox] = []
        self.receiver_connect_btns: List[QPushButton] = []
        self.receiver_status_labels: List[QLabel] = []
        
        # Update timer for real-time statistics
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_statistics)
        self.update_timer.start(100)  # Update every 100ms
        
        self._create_widgets()
        self.log_signal.connect(self._append_log)
        self._refresh_ports()
        
    def _create_widgets(self):
        """Create the main GUI widgets"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QHBoxLayout(central_widget)
        
        # Splitter for config (left) and results (right)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        
        # Left pane: Configuration
        config_widget = QWidget()
        self._create_config_pane(config_widget)
        splitter.addWidget(config_widget)
        
        # Right pane: Results
        results_widget = QWidget()
        self._create_results_pane(results_widget)
        splitter.addWidget(results_widget)
        
        # Set splitter proportions
        splitter.setSizes([400, 800])
        
    def _create_config_pane(self, parent):
        """Create configuration panel"""
        layout = QVBoxLayout(parent)
        
        # Connection settings
        conn_group = QGroupBox("Connection Settings")
        conn_layout = QVBoxLayout(conn_group)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        conn_layout.addWidget(refresh_btn)
        
        # Sender and receiver side by side
        conn_hbox = QHBoxLayout()
        
        # Sender frame
        sender_group = QGroupBox("Sender")
        sender_layout = QGridLayout(sender_group)
        
        sender_layout.addWidget(QLabel("Port:"), 0, 0)
        self.sender_port_combo = QComboBox()
        sender_layout.addWidget(self.sender_port_combo, 0, 1)
        
        sender_layout.addWidget(QLabel("Baud Rate:"), 1, 0)
        self.sender_baud_combo = QComboBox()
        self.sender_baud_combo.addItems(["4800", "7200", "9600", "14400", "19200", "28800", 
                                        "38400", "57600", "115200", "230400", "460800", "921600"])
        self.sender_baud_combo.setCurrentText("230400")
        sender_layout.addWidget(self.sender_baud_combo, 1, 1)
        
        self.sender_connect_btn = QPushButton("Connect")
        self.sender_connect_btn.clicked.connect(self._connect_sender)
        sender_layout.addWidget(self.sender_connect_btn, 2, 0, 1, 2)
        
        self.sender_status_label = QLabel("Disconnected")
        self.sender_status_label.setStyleSheet("color: red;")
        sender_layout.addWidget(self.sender_status_label, 3, 0, 1, 2)
        
        # Receivers frame (multiple)
        receivers_group = QGroupBox("Receivers")
        receivers_layout = QHBoxLayout(receivers_group)
        
        self.receiver_port_combos.clear()
        self.receiver_baud_combos.clear()
        self.receiver_connect_btns.clear()
        self.receiver_status_labels.clear()
        
        for idx in range(self.num_receivers):
            group = QGroupBox(f"Receiver {idx + 1}")
            grid = QGridLayout(group)
            
            grid.addWidget(QLabel("Port:"), 0, 0)
            port_combo = QComboBox()
            self.receiver_port_combos.append(port_combo)
            grid.addWidget(port_combo, 0, 1)
            
            grid.addWidget(QLabel("Baud Rate:"), 1, 0)
            baud_combo = QComboBox()
            baud_combo.addItems(["4800", "7200", "9600", "14400", "19200", "28800", 
                                 "38400", "57600", "115200", "230400", "460800", "921600"])
            baud_combo.setCurrentText("230400")
            self.receiver_baud_combos.append(baud_combo)
            grid.addWidget(baud_combo, 1, 1)
            
            connect_btn = QPushButton("Connect")
            connect_btn.clicked.connect(lambda _, i=idx: self._connect_receiver(i))
            self.receiver_connect_btns.append(connect_btn)
            grid.addWidget(connect_btn, 2, 0, 1, 2)
            
            status_label = QLabel("Disconnected")
            status_label.setStyleSheet("color: red;")
            self.receiver_status_labels.append(status_label)
            grid.addWidget(status_label, 3, 0, 1, 2)
            
            receivers_layout.addWidget(group)
        
        conn_hbox.addWidget(sender_group)
        conn_hbox.addWidget(receivers_group)
        conn_layout.addLayout(conn_hbox)
        
        layout.addWidget(conn_group)
        
        # Test parameters
        test_group = QGroupBox("Test Parameters")
        test_layout = QVBoxLayout(test_group)
        
        # Input mode selection
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Input Mode:"))
        self.input_mode_combo = QComboBox()
        self.input_mode_combo.addItems(["Manual", "Speed-Based", "Packet-Count"])
        self.input_mode_combo.currentTextChanged.connect(self._on_input_mode_changed)
        mode_layout.addWidget(self.input_mode_combo)
        mode_layout.addStretch()
        test_layout.addLayout(mode_layout)
        
        # Manual mode parameters
        self.manual_params_widget = QWidget()
        manual_layout = QGridLayout(self.manual_params_widget)
        
        manual_layout.addWidget(QLabel("Total Packet Size (bytes):"), 0, 0)
        self.write_size_edit = QLineEdit("145")
        self.write_size_edit.editingFinished.connect(self._validate_packet_size)
        manual_layout.addWidget(self.write_size_edit, 0, 1)
        manual_layout.addWidget(QLabel("(Total on-wire packet size, min: 45)"), 0, 2)
        
        manual_layout.addWidget(QLabel("Payload size (bytes):"), 1, 0)
        self.total_packet_size_label = QLabel("101")
        self.total_packet_size_label.setFont(QFont("Arial", 9, QFont.Bold))
        manual_layout.addWidget(self.total_packet_size_label, 1, 1)
        
        manual_layout.addWidget(QLabel("Write Frequency (s):"), 2, 0)
        self.write_freq_edit = QLineEdit("0.1")
        self.write_freq_edit.textChanged.connect(self._update_manual_data_rate)
        manual_layout.addWidget(self.write_freq_edit, 2, 1)
        manual_layout.addWidget(QLabel("(Time between packets)"), 2, 2)
        
        manual_layout.addWidget(QLabel("Expected Data Rate (kbps):"), 3, 0)
        self.expected_data_rate_label = QLabel("11.60")
        self.expected_data_rate_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.expected_data_rate_label.setStyleSheet("color: blue;")
        manual_layout.addWidget(self.expected_data_rate_label, 3, 1)
        
        manual_layout.addWidget(QLabel("Test Length (s):"), 4, 0)
        self.test_length_edit = QLineEdit("10")
        manual_layout.addWidget(self.test_length_edit, 4, 1)
        
        self.write_size_edit.textChanged.connect(self._update_total_packet_size)
        
        # Speed-based mode parameters
        self.speed_params_widget = QWidget()
        speed_layout = QGridLayout(self.speed_params_widget)
        
        speed_layout.addWidget(QLabel("Test Duration (s):"), 0, 0)
        self.duration_edit = QLineEdit("10")
        speed_layout.addWidget(self.duration_edit, 0, 1)
        
        speed_layout.addWidget(QLabel("Buffer Size (bytes):"), 1, 0)
        self.buffer_size_edit = QLineEdit("145")
        self.buffer_size_edit.editingFinished.connect(self._validate_packet_size_speed)
        speed_layout.addWidget(self.buffer_size_edit, 1, 1)
        speed_layout.addWidget(QLabel("(Total packet size including 44-byte header)"), 1, 2)
        
        speed_layout.addWidget(QLabel("Payload size (bytes):"), 2, 0)
        self.payload_size_speed_label = QLabel("101")
        self.payload_size_speed_label.setFont(QFont("Arial", 9, QFont.Bold))
        speed_layout.addWidget(self.payload_size_speed_label, 2, 1)
        
        speed_layout.addWidget(QLabel("Desired Speed (kbps):"), 3, 0)
        self.desired_speed_edit = QLineEdit("10")
        speed_layout.addWidget(self.desired_speed_edit, 3, 1)
        
        speed_layout.addWidget(QLabel("Calculated Write Frequency (s):"), 4, 0)
        self.calc_write_freq_label = QLabel("0.116")
        self.calc_write_freq_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.calc_write_freq_label.setStyleSheet("color: blue;")
        speed_layout.addWidget(self.calc_write_freq_label, 4, 1)
        
        self.buffer_size_edit.textChanged.connect(self._update_speed_based_calculations)
        self.desired_speed_edit.textChanged.connect(self._update_speed_based_calculations)
        
        # Packet-count mode parameters
        self.packet_count_params_widget = QWidget()
        packet_count_layout = QGridLayout(self.packet_count_params_widget)
        
        packet_count_layout.addWidget(QLabel("Total Packet Size (bytes):"), 0, 0)
        self.packet_count_size_edit = QLineEdit("145")
        self.packet_count_size_edit.editingFinished.connect(self._validate_packet_size_count)
        packet_count_layout.addWidget(self.packet_count_size_edit, 0, 1)
        packet_count_layout.addWidget(QLabel("(Total on-wire packet size, min: 45)"), 0, 2)
        
        packet_count_layout.addWidget(QLabel("Payload size (bytes):"), 1, 0)
        self.packet_count_payload_label = QLabel("101")
        self.packet_count_payload_label.setFont(QFont("Arial", 9, QFont.Bold))
        packet_count_layout.addWidget(self.packet_count_payload_label, 1, 1)
        
        packet_count_layout.addWidget(QLabel("Write Frequency (s):"), 2, 0)
        self.packet_count_freq_edit = QLineEdit("0.1")
        self.packet_count_freq_edit.textChanged.connect(self._update_packet_count_calculations)
        packet_count_layout.addWidget(self.packet_count_freq_edit, 2, 1)
        packet_count_layout.addWidget(QLabel("(Time between packets)"), 2, 2)
        
        packet_count_layout.addWidget(QLabel("Expected Data Rate (kbps):"), 3, 0)
        self.packet_count_data_rate_label = QLabel("11.60")
        self.packet_count_data_rate_label.setFont(QFont("Arial", 9, QFont.Bold))
        self.packet_count_data_rate_label.setStyleSheet("color: blue;")
        packet_count_layout.addWidget(self.packet_count_data_rate_label, 3, 1)
        
        packet_count_layout.addWidget(QLabel("Number of Packets:"), 4, 0)
        self.num_packets_edit = QLineEdit("100")
        packet_count_layout.addWidget(self.num_packets_edit, 4, 1)
        
        self.packet_count_size_edit.textChanged.connect(self._update_packet_count_calculations)
        
        # Add mode parameter widgets to test layout
        test_layout.addWidget(self.manual_params_widget)
        test_layout.addWidget(self.speed_params_widget)
        test_layout.addWidget(self.packet_count_params_widget)
        self.speed_params_widget.hide()
        self.packet_count_params_widget.hide()
        
        # Direction
        direction_layout = QHBoxLayout()
        direction_layout.addWidget(QLabel("Direction:"))
        self.direction_combo = QComboBox()
        self.direction_combo.addItems(["Bidirectional", "Sender → Receiver", "Receiver → Sender"])
        direction_layout.addWidget(self.direction_combo)
        direction_layout.addWidget(QLabel("(Communication direction)"))
        direction_layout.addStretch()
        test_layout.addLayout(direction_layout)
        
        # RSSI reading button (independent of tests)
        rssi_layout = QHBoxLayout()
        rssi_read_btn = QPushButton("Read RSSI")
        rssi_read_btn.clicked.connect(self._read_rssi)
        rssi_layout.addWidget(rssi_read_btn)
        rssi_layout.addStretch()
        test_layout.addLayout(rssi_layout)
        
        # Test control buttons
        control_group = QGroupBox("Test Controls")
        control_layout = QHBoxLayout(control_group)
        
        self.start_btn = QPushButton("Start Test")
        self.start_btn.clicked.connect(self._start_test)
        self.start_btn.setEnabled(False)
        control_layout.addWidget(self.start_btn)
        
        self.stop_btn = QPushButton("Stop Test")
        self.stop_btn.clicked.connect(self._stop_test)
        self.stop_btn.setEnabled(False)
        control_layout.addWidget(self.stop_btn)
        
        self.clear_btn = QPushButton("Clear Results")
        self.clear_btn.clicked.connect(self._clear_results)
        control_layout.addWidget(self.clear_btn)
        
        control_layout.addStretch()
        
        test_layout.addWidget(control_group)
        
        layout.addWidget(test_group)
        layout.addStretch()
        
        # Initial calculations
        self._update_speed_based_calculations()
        self._update_manual_data_rate()
        self._update_packet_count_calculations()
        
    def _create_results_pane(self, parent):
        """Create results display panel"""
        layout = QVBoxLayout(parent)
        
        # Real-time statistics (sender + multiple receivers)
        stats_group = QGroupBox("Real-Time Statistics")
        stats_layout = QHBoxLayout(stats_group)
        self.stats_labels = {}
        
        sender_group = QGroupBox("Sender")
        sender_metrics = [
            ("Send Rate", "sender_send_rate"),
            ("Packets Sent", "sender_packets_sent"),
            ("Bytes Sent", "sender_bytes_sent"),
            ("Test Duration", "sender_test_duration"),
        ]
        sender_layout = QGridLayout(sender_group)
        for row, (label, key) in enumerate(sender_metrics):
            sender_layout.addWidget(QLabel(f"{label}:"), row, 0)
            value_label = QLabel("N/A")
            value_label.setFont(QFont("Arial", 9, QFont.Bold))
            sender_layout.addWidget(value_label, row, 1)
            self.stats_labels[key] = value_label
        stats_layout.addWidget(sender_group)
        
        for idx in range(self.num_receivers):
            receiver_group = QGroupBox(f"Receiver {idx + 1}")
            receiver_layout = QGridLayout(receiver_group)
            receiver_metrics = [
                ("Valid Rate", f"receiver_{idx}_valid_rate"),
                ("Packet Loss", f"receiver_{idx}_packet_loss"),
                ("Avg Latency", f"receiver_{idx}_avg_latency"),
                ("Packets Received", f"receiver_{idx}_packets_received"),
            ]
            for row, (label, key) in enumerate(receiver_metrics):
                receiver_layout.addWidget(QLabel(f"{label}:"), row, 0)
                value_label = QLabel("N/A")
                value_label.setFont(QFont("Arial", 9, QFont.Bold))
                receiver_layout.addWidget(value_label, row, 1)
                self.stats_labels[key] = value_label
            stats_layout.addWidget(receiver_group)
        
        layout.addWidget(stats_group)
        
        # Test log
        log_group = QGroupBox("Test Log")
        log_layout = QVBoxLayout(log_group)
        
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        
        layout.addWidget(log_group)
        
    def _refresh_ports(self):
        """Refresh available serial ports"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.sender_port_combo.clear()
        self.sender_port_combo.addItems(ports)
        
        for combo in self.receiver_port_combos:
            combo.clear()
            combo.addItems(ports)
        
        if ports:
            self.sender_port_combo.setCurrentIndex(0)
            for idx, combo in enumerate(self.receiver_port_combos):
                default_index = min(idx + 1, len(ports) - 1)
                combo.setCurrentIndex(default_index)
    
    def _connect_sender(self):
        """Connect to sender port"""
        try:
            if (self.sender_connection is not None and 
                hasattr(self.sender_connection, 'is_open') and 
                self.sender_connection.is_open):
                try:
                    self.sender_connection.close()
                except Exception:
                    pass
                self.sender_connection = None
                if hasattr(self, 'sender_connect_btn') and self.sender_connect_btn is not None:
                    self.sender_connect_btn.setText("Connect")
                if hasattr(self, 'sender_status_label') and self.sender_status_label is not None:
                    self.sender_status_label.setText("Disconnected")
                    self.sender_status_label.setStyleSheet("color: red;")
                self._log("Sender disconnected")
                self._update_button_states()
                return
            
            port = self.sender_port_combo.currentText()
            baud = int(self.sender_baud_combo.currentText())
            
            if not port:
                QMessageBox.critical(self, "Error", "Please select a sender port")
                return
            
            self.sender_connection = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            if hasattr(self, 'sender_connect_btn') and self.sender_connect_btn is not None:
                self.sender_connect_btn.setText("Disconnect")
            if hasattr(self, 'sender_status_label') and self.sender_status_label is not None:
                self.sender_status_label.setText(f"Connected @ {baud} baud")
                self.sender_status_label.setStyleSheet("color: green;")
            self._log(f"Sender connected to {port} at {baud} baud")
            self._update_button_states()
            
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect sender: {str(e)}")
            self._log(f"Sender connection failed: {str(e)}")
    
    def _connect_receiver(self, index: int):
        """Connect/disconnect a receiver port"""
        try:
            current_conn = self.receiver_connections[index]
            connect_btn = self.receiver_connect_btns[index]
            status_label = self.receiver_status_labels[index]
            port_combo = self.receiver_port_combos[index]
            baud_combo = self.receiver_baud_combos[index]
            
            if current_conn is not None and hasattr(current_conn, 'is_open') and current_conn.is_open:
                try:
                    current_conn.close()
                except Exception:
                    pass
                self.receiver_connections[index] = None
                connect_btn.setText("Connect")
                status_label.setText("Disconnected")
                status_label.setStyleSheet("color: red;")
                self._log(f"Receiver {index + 1} disconnected")
                self._update_button_states()
                return
            
            port = port_combo.currentText()
            baud = int(baud_combo.currentText())
            
            if not port:
                QMessageBox.critical(self, "Error", f"Please select a port for Receiver {index + 1}")
                return
            
            new_conn = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            self.receiver_connections[index] = new_conn
            connect_btn.setText("Disconnect")
            status_label.setText(f"Connected @ {baud} baud")
            status_label.setStyleSheet("color: green;")
            self._log(f"Receiver {index + 1} connected to {port} at {baud} baud")
            self._update_button_states()
            
        except Exception as e:
            QMessageBox.critical(self, "Connection Error", f"Failed to connect Receiver {index + 1}: {str(e)}")
            self._log(f"Receiver {index + 1} connection failed: {str(e)}")
    
    def _update_button_states(self):
        """Update button states based on connection status"""
        sender_connected = (self.sender_connection is not None and 
                           hasattr(self.sender_connection, 'is_open') and 
                           self.sender_connection.is_open)
        receivers_connected = True
        for conn in self.receiver_connections:
            if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
                receivers_connected = False
                break
        all_connected = sender_connected and receivers_connected
        
        if hasattr(self, 'start_btn') and self.start_btn is not None:
            if not self.test_running:
                self.start_btn.setEnabled(all_connected)
            else:
                self.start_btn.setEnabled(False)
    
    def _log(self, message: str):
        """Log message with timestamp (thread-safe)"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] {message}"
        
        if QThread.currentThread() == self.thread():
            self._append_log(formatted)
        else:
            self.log_signal.emit(formatted)

    def _append_log(self, formatted_message: str):
        """Append log text (UI thread only)"""
        if not hasattr(self, 'log_text') or self.log_text is None:
            return
        self.log_text.append(formatted_message)
    
    def _update_total_packet_size(self):
        """Update the payload size label when total size changes"""
        try:
            total = int(self.write_size_edit.text())
            if total < 0:
                return
            payload = max(total - self.packet_header_size, 0)
            self.total_packet_size_label.setText(str(payload))
            self._update_manual_data_rate()
        except ValueError:
            pass
    
    def _update_manual_data_rate(self):
        """Update expected data rate calculation for manual mode"""
        try:
            total_size = int(self.write_size_edit.text())
            write_freq = float(self.write_freq_edit.text())
            
            if write_freq > 0:
                data_rate_bps = (total_size * 8) / write_freq
                data_rate_kbps = data_rate_bps / 1000
                
                if data_rate_kbps >= 100:
                    self.expected_data_rate_label.setText(f"{data_rate_kbps:.2f}")
                elif data_rate_kbps >= 10:
                    self.expected_data_rate_label.setText(f"{data_rate_kbps:.3f}")
                else:
                    self.expected_data_rate_label.setText(f"{data_rate_kbps:.4f}")
            else:
                self.expected_data_rate_label.setText("N/A")
        except (ValueError, ZeroDivisionError):
            self.expected_data_rate_label.setText("N/A")
    
    def _on_input_mode_changed(self, text):
        """Handle input mode change"""
        if text == "Manual":
            self.manual_params_widget.show()
            self.speed_params_widget.hide()
            self.packet_count_params_widget.hide()
        elif text == "Speed-Based":
            self.manual_params_widget.hide()
            self.speed_params_widget.show()
            self.packet_count_params_widget.hide()
            self._update_speed_based_calculations()
        else:  # Packet-Count
            self.manual_params_widget.hide()
            self.speed_params_widget.hide()
            self.packet_count_params_widget.show()
            self._update_packet_count_calculations()
    
    def _update_packet_count_calculations(self):
        """Update packet-count mode calculations"""
        try:
            total_size = int(self.packet_count_size_edit.text())
            payload = max(total_size - self.packet_header_size, 0)
            self.packet_count_payload_label.setText(str(payload))
            
            write_freq = float(self.packet_count_freq_edit.text())
            if write_freq > 0:
                data_rate_bps = (total_size * 8) / write_freq
                data_rate_kbps = data_rate_bps / 1000
                
                if data_rate_kbps >= 100:
                    self.packet_count_data_rate_label.setText(f"{data_rate_kbps:.2f}")
                elif data_rate_kbps >= 10:
                    self.packet_count_data_rate_label.setText(f"{data_rate_kbps:.3f}")
                else:
                    self.packet_count_data_rate_label.setText(f"{data_rate_kbps:.4f}")
            else:
                self.packet_count_data_rate_label.setText("N/A")
        except (ValueError, ZeroDivisionError):
            self.packet_count_data_rate_label.setText("N/A")
    
    def _validate_packet_size_count(self):
        """Validate packet size for packet-count mode"""
        try:
            total = int(self.packet_count_size_edit.text())
            min_size = self.packet_header_size + 1
            if total < min_size:
                QMessageBox.critical(self, "Invalid Packet Size", 
                                   f"Total packet size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                self.packet_count_size_edit.setText(str(min_size))
                self._update_packet_count_calculations()
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Packet size must be a valid integer")
            self.packet_count_size_edit.setText("145")
            self._update_packet_count_calculations()
    
    def _update_speed_based_calculations(self):
        """Update speed-based mode calculations"""
        try:
            buffer_size = int(self.buffer_size_edit.text())
            payload = max(buffer_size - self.packet_header_size, 0)
            self.payload_size_speed_label.setText(str(payload))
            
            speed_kbps = float(self.desired_speed_edit.text())
            if speed_kbps > 0:
                bytes_per_second = (speed_kbps * 1000) / 8
                write_freq = buffer_size / bytes_per_second
                
                if write_freq >= 1.0:
                    self.calc_write_freq_label.setText(f"{write_freq:.2f}")
                elif write_freq >= 0.1:
                    self.calc_write_freq_label.setText(f"{write_freq:.4f}")
                else:
                    self.calc_write_freq_label.setText(f"{write_freq:.6f}")
            else:
                self.calc_write_freq_label.setText("N/A")
        except (ValueError, ZeroDivisionError):
            self.calc_write_freq_label.setText("N/A")
    
    def _validate_packet_size_speed(self):
        """Validate packet size for speed-based mode"""
        try:
            total = int(self.buffer_size_edit.text())
            min_size = self.packet_header_size + 1
            if total < min_size:
                QMessageBox.critical(self, "Invalid Packet Size", 
                                   f"Buffer size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                self.buffer_size_edit.setText(str(min_size))
                self._update_speed_based_calculations()
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Buffer size must be a valid integer")
            self.buffer_size_edit.setText("145")
            self._update_speed_based_calculations()
    
    def _validate_packet_size(self):
        """Validate packet size and show error if too small"""
        try:
            total = int(self.write_size_edit.text())
            min_size = self.packet_header_size + 1
            if total < min_size:
                QMessageBox.critical(self, "Invalid Packet Size", 
                                   f"Total packet size must be at least {min_size} bytes\n"
                                   f"(44-byte header + 1-byte minimum payload)")
                self.write_size_edit.setText(str(min_size))
                self._update_total_packet_size()
        except ValueError:
            QMessageBox.critical(self, "Invalid Input", "Packet size must be a valid integer")
            self.write_size_edit.setText("145")
            self._update_total_packet_size()
    
    def _clear_serial_buffers(self):
        """Clear all serial port input/output buffers"""
        try:
            if (self.sender_connection is not None and 
                hasattr(self.sender_connection, 'is_open') and 
                self.sender_connection.is_open):
                if self.sender_connection.in_waiting > 0:
                    self.sender_connection.read(self.sender_connection.in_waiting)
                self.sender_connection.reset_input_buffer()
                self.sender_connection.reset_output_buffer()
                self.sender_connection.flush()
            
            for conn in self.receiver_connections:
                if conn is not None and hasattr(conn, 'is_open') and conn.is_open:
                    if conn.in_waiting > 0:
                        conn.read(conn.in_waiting)
                    conn.reset_input_buffer()
                    conn.reset_output_buffer()
                    conn.flush()
        except Exception as e:
            self._log(f"Warning: Error clearing buffers: {str(e)}")
    
    def _enter_at_mode(self, conn: serial.Serial) -> bool:
        """Enter AT command mode from data mode"""
        try:
            self._log("Entering AT mode...")
            
            # Clear any pending data
            if conn.in_waiting > 0:
                pending = conn.read(conn.in_waiting)
                self._log(f"Cleared {len(pending)} bytes of pending data")
            
            # Step 1: Idle for 1 second
            time.sleep(1.0)
            
            # Step 2: Send "+++"
            conn.write("+++".encode())
            conn.flush()
            
            # Step 3: Idle for another 1 second
            time.sleep(1.0)
            
            # Step 4: Read response
            response = ""
            start_time = time.time()
            while time.time() - start_time < 2.0:
                if conn.in_waiting > 0:
                    chunk = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                    response += chunk
                    if 'OK' in response.upper() or 'AT' in response.upper():
                        break
                time.sleep(0.05)
            
            # Read any remaining
            if conn.in_waiting > 0:
                remaining = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                response += remaining
            
            success = 'OK' in response.upper() or 'AT' in response.upper()
            if success:
                self._log("Successfully entered AT mode")
            else:
                self._log(f"Warning: AT mode response unclear: {repr(response)}")
            
            return success
        except Exception as e:
            self._log(f"Error entering AT mode: {str(e)}")
            return False
    
    def _exit_at_mode(self, conn: serial.Serial) -> bool:
        """Exit AT command mode using ATA"""
        try:
            self._log("Exiting AT mode...")
            conn.write("ATA\r\n".encode())
            conn.flush()
            time.sleep(0.2)
            
            response = ""
            if conn.in_waiting > 0:
                response = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
            
            success = "OK" in response.upper()
            if success:
                self._log("Successfully exited AT mode")
            else:
                self._log(f"Warning: Exit response unclear: {repr(response)}")
            
            return success
        except Exception as e:
            self._log(f"Error exiting AT mode: {str(e)}")
            return False
    
    def _read_register(self, conn: serial.Serial, register: str) -> Optional[str]:
        """Read a register value using AT command"""
        try:
            reg_num = register[1:]  # Remove 'S' prefix
            cmd = f"ATS{reg_num}?\r\n"
            conn.write(cmd.encode())
            conn.flush()
            
            time.sleep(0.3)
            
            response = ""
            start_time = time.time()
            while time.time() - start_time < 1.0:
                if conn.in_waiting > 0:
                    chunk = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                    response += chunk
                    if '\r\n' in response or '\n' in response:
                        break
                time.sleep(0.05)
            
            # Read any remaining
            if conn.in_waiting > 0:
                remaining = conn.read(conn.in_waiting).decode('utf-8', errors='ignore')
                response += remaining
            
            response = response.strip()
            
            # Extract value (format is usually "ATS123=value\r\n" or just "value\r\n")
            lines = response.split('\r\n')
            for line in lines:
                if '=' in line:
                    value = line.split('=')[-1].strip()
                    if value.isdigit() or (value.startswith('-') and value[1:].isdigit()):
                        return value
                elif line.strip().isdigit() or (line.strip().startswith('-') and line.strip()[1:].isdigit()):
                    return line.strip()
            
            return None
        except Exception as e:
            self._log(f"Error reading register {register}: {str(e)}")
            return None
    
    def _read_rssi_from_device(self, device_name: str, conn: serial.Serial) -> dict:
        """Read RSSI values (S123 and S124) from a device"""
        rssi = {'S123': None, 'S124': None}
        
        if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
            self._log(f"{device_name}: Not connected")
            return rssi
        
        self._log(f"Reading RSSI from {device_name}...")
        
        # Enter AT mode
        if not self._enter_at_mode(conn):
            self._log(f"{device_name}: Failed to enter AT mode")
            return rssi
        
        # Small delay to ensure AT mode is ready
        time.sleep(0.2)
        
        # Read S123 (RSSI From Master)
        s123_value = self._read_register(conn, "S123")
        if s123_value:
            try:
                rssi['S123'] = int(s123_value)
                self._log(f"{device_name} S123 (RSSI From Master): {rssi['S123']} dBm")
            except ValueError:
                self._log(f"{device_name} S123: Failed to parse value '{s123_value}'")
        else:
            self._log(f"{device_name} S123: No value returned")
        
        # Small delay between register reads
        time.sleep(0.2)
        
        # Read S124 (RSSI From Slave)
        s124_value = self._read_register(conn, "S124")
        if s124_value:
            try:
                rssi['S124'] = int(s124_value)
                self._log(f"{device_name} S124 (RSSI From Slave): {rssi['S124']} dBm")
            except ValueError:
                self._log(f"{device_name} S124: Failed to parse value '{s124_value}'")
        else:
            self._log(f"{device_name} S124: No value returned")
        
        # Exit AT mode
        self._exit_at_mode(conn)
        
        return rssi
    
    def _read_rssi(self):
        """Read RSSI values from sender and all receivers"""
        if (self.sender_connection is None or 
            not hasattr(self.sender_connection, 'is_open') or 
            not self.sender_connection.is_open):
            QMessageBox.warning(self, "Warning", "Sender not connected")
            return
        
        disconnected = [idx for idx, conn in enumerate(self.receiver_connections)
                        if conn is None or not hasattr(conn, 'is_open') or not conn.is_open]
        if disconnected:
            QMessageBox.warning(self, "Warning", f"Receivers {', '.join(str(i+1) for i in disconnected)} are not connected")
            return
        
        self._log("=== Reading RSSI ===")
        sender_rssi = self._read_rssi_from_device("Sender", self.sender_connection)
        self.rssi_current['sender'] = sender_rssi
        self._log(f"Sender RSSI -> S123: {sender_rssi['S123']} dBm, S124: {sender_rssi['S124']} dBm")
        
        for idx, conn in enumerate(self.receiver_connections):
            rssi = self._read_rssi_from_device(f"Receiver {idx + 1}", conn)
            self.rssi_current['receivers'][idx] = rssi
            self._log(f"Receiver {idx + 1} RSSI -> S123: {rssi['S123']} dBm, S124: {rssi['S124']} dBm")
            time.sleep(0.2)
        
        self._log("RSSI capture complete.")
    
    def _start_test(self):
        """Start the data rate test"""
        if self.test_running:
            return
        
        # Get parameters based on input mode
        mode = self.input_mode_combo.currentText()
        if mode == "Manual":
            try:
                total_size = int(self.write_size_edit.text())
                write_freq = float(self.write_freq_edit.text())
                test_length = float(self.test_length_edit.text())
                target_packets = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        elif mode == "Speed-Based":
            try:
                test_length = float(self.duration_edit.text())
                total_size = int(self.buffer_size_edit.text())
                write_freq = float(self.calc_write_freq_label.text())
                target_packets = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        else:  # Packet-Count
            try:
                total_size = int(self.packet_count_size_edit.text())
                write_freq = float(self.packet_count_freq_edit.text())
                target_packets = int(self.num_packets_edit.text())
                test_length = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        
        # Validate packet size
        if total_size < self.packet_header_size + 1:
            QMessageBox.critical(self, "Invalid Packet Size", 
                               f"Total packet size must be at least {self.packet_header_size + 1} bytes")
            return
        
        # Clear buffers
        self._clear_serial_buffers()
        
        # Reset statistics
        self.stats_mutex.lock()
        for key in ['bytes_sent', 'bytes_received', 'bytes_received_valid', 'bytes_received_total',
                    'packets_sent', 'packets_received', 'packets_corrupt',
                    'bytes_sent_2', 'bytes_received_2', 'bytes_received_valid_2', 'bytes_received_total_2',
                    'packets_sent_2', 'packets_received_2', 'packets_corrupt_2']:
            if key in self.stats:
                self.stats[key] = 0
        if 'latency_samples' in self.stats:
            self.stats['latency_samples'].clear()
        if 'latency_samples_2' in self.stats:
            self.stats['latency_samples_2'].clear()
        
        for rstat in self.receiver_stats:
            rstat['bytes_received_total'] = 0
            rstat['bytes_received_valid'] = 0
            rstat['packets_received'] = 0
            rstat['packets_corrupt'] = 0
            rstat['valid_rate_bps'] = None
            rstat['valid_rate_kbps'] = None
            rstat['packet_loss'] = None
            rstat['avg_latency'] = None
            rstat['latency_samples'].clear()
        
        self.stats['start_time'] = time.time()
        self.stats['end_time'] = None
        self.stats['elapsed_time'] = None
        self.stats_mutex.unlock()
        
        self.test_running = True
        self.target_packets = target_packets
        self.test_end_time = time.time() + test_length if test_length else None
        self.receiver_threads = [None] * self.num_receivers
        
        direction = self.direction_combo.currentText()
        if direction != "Sender → Receiver":
            QMessageBox.warning(self, "Unsupported Direction",
                                "Multi-receiver mode currently supports only 'Sender → Receiver'.")
            return
        
        missing_receivers = [idx for idx, conn in enumerate(self.receiver_connections)
                             if conn is None or not hasattr(conn, 'is_open') or not conn.is_open]
        if missing_receivers:
            QMessageBox.critical(self, "Error",
                                 f"Please connect all receivers before starting the test "
                                 f"(missing: {', '.join(str(i+1) for i in missing_receivers)})")
            return
        
        # Log test start
        mode_str = mode.lower().replace("-", " ")
        self._log(f"Starting test: {mode_str} mode")
        self._log(f"Total packet size: {total_size} bytes")
        if mode == "Speed-Based":
            self._log(f"Desired speed: {float(self.desired_speed_edit.text())} kbps")
            self._log(f"Calculated write frequency: {write_freq} s")
        self._log(f"Test started - timer started")
        if test_length:
            self._log(f"Test will auto-stop after {test_length} seconds")
        elif target_packets:
            self._log(f"Test will stop after {target_packets} packets sent")
        
        # Start receiver threads
        for idx, conn in enumerate(self.receiver_connections):
            self._log(f"Starting receiver {idx + 1}")
            thread = threading.Thread(
                target=self._receiver_thread,
                args=(conn, idx, total_size, test_length, target_packets),
                daemon=True
            )
            self.receiver_threads[idx] = thread
            thread.start()
        
        # Start sender thread
        self._log(f"Starting sender: total {total_size} bytes (payload {total_size - self.packet_header_size}) "
                  f"every {write_freq}s for {test_length if test_length else 'N/A'}s")
        self.test_thread = threading.Thread(target=self._sender_thread,
                                            args=(self.sender_connection, '', total_size, write_freq, test_length, target_packets),
                                            daemon=True)
        self.test_thread.start()
        
        # Start monitor thread for auto-stop
        if test_length or target_packets:
            self.monitor_thread = threading.Thread(target=self._monitor_test_end, daemon=True)
            self.monitor_thread.start()
        
        # Update button states
        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
    
    def _sender_thread(self, conn: serial.Serial, stats_key: str = '', total_size: int = None, 
                      write_freq: float = None, test_length: float = None, target_packets: int = None):
        """Sender thread - sends packets at specified frequency"""
        if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
            return
        
        self._clear_serial_buffers()
        
        sequence = 0
        payload_size = total_size - self.packet_header_size
        payload = b'X' * payload_size
        
        start_time = time.time()
        next_packet_time = start_time
        
        while self.test_running:
            current_time = time.time()
            
            # Check if test should end
            if test_length and (current_time - start_time) >= test_length:
                break
            if target_packets and sequence >= target_packets:
                break
            
            # Wait until it's time to send the next packet
            if current_time < next_packet_time:
                time.sleep(next_packet_time - current_time)
            
            # Create and send packet
            packet = self._create_packet(sequence, payload)
            try:
                conn.write(packet)
                conn.flush()
                
                self.stats_mutex.lock()
                self.stats[f'bytes_sent{stats_key}'] += len(packet)
                self.stats[f'packets_sent{stats_key}'] += 1
                self.stats_mutex.unlock()
                
                sequence += 1
                
                # Calculate next packet time (interval between packet starts)
                next_packet_time = next_packet_time + write_freq
                
            except Exception as e:
                self._log(f"Error sending packet: {str(e)}")
                break
    
    def _receiver_thread(self, conn: serial.Serial, receiver_index: int, expected_packet_size: int = None,
                        test_length: float = None, target_packets: int = None):
        """Receiver thread - receives and validates packets for a specific receiver"""
        if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
            return
        
        self._clear_serial_buffers()
        
        buffer = b''
        latency_store = self.receiver_stats[receiver_index]['latency_samples']
        
        while self.test_running or (self.packet_count_wait_end and time.time() < self.packet_count_wait_end):
            try:
                if conn.in_waiting > 0:
                    data = conn.read(conn.in_waiting)
                    buffer += data
                    
                    # Process complete packets
                    while len(buffer) >= expected_packet_size:
                        packet = buffer[:expected_packet_size]
                        buffer = buffer[expected_packet_size:]
                        
                        valid = self._validate_packet(packet, '', latency_store)
                        self.stats_mutex.lock()
                        rstat = self.receiver_stats[receiver_index]
                        if valid:
                            rstat['packets_received'] += 1
                            rstat['bytes_received_valid'] += len(packet)
                            self.stats['bytes_received_valid'] += len(packet)
                            self.stats['packets_received'] += 1
                        else:
                            rstat['packets_corrupt'] += 1
                            self.stats['packets_corrupt'] += 1
                        
                        rstat['bytes_received_total'] += len(packet)
                        self.stats['bytes_received_total'] += len(packet)
                        self.stats['bytes_received'] += len(packet)
                        self._recalculate_receiver_totals()
                        self.stats_mutex.unlock()
                
                time.sleep(0.001)  # Small sleep to prevent CPU spinning
                
            except Exception as e:
                self._log(f"Receiver {receiver_index + 1} error: {str(e)}")
                break
    
    def _monitor_test_end(self):
        """Monitor thread to auto-stop test"""
        try:
            use_packet_count = (self.target_packets is not None and self.target_packets > 0)
            
            while self.test_running:
                if use_packet_count:
                    # Check if target packets have been sent
                    self.stats_mutex.lock()
                    sent = self.stats['packets_sent']
                    self.stats_mutex.unlock()
                    if sent >= self.target_packets:
                        self._log(f"Target of {self.target_packets} packets sent - waiting for reception (max 1s)...")
                        # Capture end_time NOW (when target packets are sent)
                        self.stats['end_time'] = time.time()
                        self.test_running = False
                        
                        # Wait up to 1 second for packets to be received
                        self.packet_count_wait_end = time.time() + 1.0
                        wait_start = time.time()
                        wait_timeout = 1.0
                        while time.time() - wait_start < wait_timeout:
                            self.stats_mutex.lock()
                            total_received = self.stats.get('packets_received', 0)
                            self.stats_mutex.unlock()
                            
                            if total_received >= self.target_packets:
                                self._log(f"All {self.target_packets} packets received")
                                break
                            time.sleep(0.05)  # Check every 50ms
                        
                        # Now actually stop the test
                        self._log("Auto-stopping after packet-count wait...")
                        QTimer.singleShot(0, self._stop_test)
                        break
                elif self.test_end_time:
                    # Check time-based stopping
                    if time.time() >= self.test_end_time:
                        self._log("Test period ended - auto-stopping...")
                        self.test_running = False
                        # Wait 500ms for reception if data received
                        time.sleep(0.5)
                        self.stats_mutex.lock()
                        if self.stats['packets_received'] > 0:
                            self.receiver_grace_period_end = time.time() + 0.5
                        self.stats_mutex.unlock()
                        QTimer.singleShot(0, self._stop_test)
                        break
                time.sleep(0.1)  # Check every 100ms
        except Exception as e:
            self._log(f"Monitor thread error: {str(e)}")
            self.test_running = False
            QTimer.singleShot(0, self._stop_test)
    
    def _stop_test(self):
        """Stop the test and calculate final statistics"""
        if not self.test_running and self.stats['end_time'] is not None:
            # Already stopped
            return
        
        self.test_running = False
        
        # Wait for threads to finish
        if self.test_thread:
            self.test_thread.join(timeout=2.0)
        for idx, thread in enumerate(self.receiver_threads):
            if thread:
                thread.join(timeout=2.0)
                self.receiver_threads[idx] = None
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)
        
        # Calculate final statistics
        self.stats_mutex.lock()
        self._recalculate_receiver_totals()
        if self.stats['start_time']:
            if self.target_packets and self.stats['end_time']:
                # For packet-count mode, use the end_time captured when packets were sent
                elapsed = self.stats['end_time'] - self.stats['start_time']
            else:
                elapsed = time.time() - self.stats['start_time']
            
            self.stats['elapsed_time'] = elapsed
            
            if elapsed > 0:
                # Calculate data rates
                direction = self.direction_combo.currentText()
                
                if direction == "Bidirectional":
                    # Calculate rates for both directions
                    self.stats['data_rate_total_bps_1'] = (self.stats['bytes_received_total'] * 8) / elapsed
                    self.stats['data_rate_total_kbps_1'] = self.stats['data_rate_total_bps_1'] / 1000
                    self.stats['data_rate_valid_bps_1'] = (self.stats['bytes_received_valid'] * 8) / elapsed
                    self.stats['data_rate_valid_kbps_1'] = self.stats['data_rate_valid_bps_1'] / 1000
                    
                    self.stats['data_rate_total_bps_2'] = (self.stats['bytes_received_total_2'] * 8) / elapsed
                    self.stats['data_rate_total_kbps_2'] = self.stats['data_rate_total_bps_2'] / 1000
                    self.stats['data_rate_valid_bps_2'] = (self.stats['bytes_received_valid_2'] * 8) / elapsed
                    self.stats['data_rate_valid_kbps_2'] = self.stats['data_rate_valid_bps_2'] / 1000
                    
                    # Combined rates
                    total_bytes = self.stats['bytes_received_total'] + self.stats['bytes_received_total_2']
                    valid_bytes = self.stats['bytes_received_valid'] + self.stats['bytes_received_valid_2']
                    self.stats['data_rate_total_bps_combined'] = (total_bytes * 8) / elapsed
                    self.stats['data_rate_total_kbps_combined'] = self.stats['data_rate_total_bps_combined'] / 1000
                    self.stats['data_rate_valid_bps_combined'] = (valid_bytes * 8) / elapsed
                    self.stats['data_rate_valid_kbps_combined'] = self.stats['data_rate_valid_bps_combined'] / 1000
                else:
                    # Unidirectional
                    self.stats['data_rate_total_bps'] = (self.stats['bytes_received_total'] * 8) / elapsed
                    self.stats['data_rate_total_kbps'] = self.stats['data_rate_total_bps'] / 1000
                    self.stats['data_rate_valid_bps'] = (self.stats['bytes_received_valid'] * 8) / elapsed
                    self.stats['data_rate_valid_kbps'] = self.stats['data_rate_valid_bps'] / 1000
                
                # Calculate send rate
                total_sent = self.stats['bytes_sent'] + (self.stats.get('bytes_sent_2', 0) if direction == "Bidirectional" else 0)
                self.stats['send_rate_bps'] = (total_sent * 8) / elapsed
                self.stats['send_rate_kbps'] = self.stats['send_rate_bps'] / 1000
        
        self.stats['end_time'] = time.time()
        self.stats_mutex.unlock()
        
        self._log("Test stopped")
        self._log("=" * 50)
        self._log(f"Data Rate (Total): {self.stats.get('data_rate_total_bps', 0):.2f} bps ({self.stats.get('data_rate_total_kbps', 0):.2f} kbps)")
        self._log(f"Data Rate (Valid): {self.stats.get('data_rate_valid_bps', 0):.2f} bps ({self.stats.get('data_rate_valid_kbps', 0):.2f} kbps)")
        self._log(f"Packet loss: {self._calculate_packet_loss():.2f}%")
        self._log(f"Corrupt packets: {self._calculate_corruption():.2f}%")
        
        # Update button states
        if hasattr(self, 'start_btn') and self.start_btn is not None:
            self.start_btn.setEnabled(True)
        if hasattr(self, 'stop_btn') and self.stop_btn is not None:
            self.stop_btn.setEnabled(False)
        self._update_button_states()
    
    def _create_packet(self, sequence: int, payload: bytes) -> bytes:
        """Create a packet with sequence, timestamp, hash, and payload"""
        timestamp = time.time()
        seq_bytes = struct.pack('>I', sequence)
        time_bytes = struct.pack('>d', timestamp)
        hash_bytes = hashlib.sha256(payload).digest()
        return seq_bytes + time_bytes + hash_bytes + payload
    
    def _validate_packet(self, packet: bytes, stats_key: str = '', latency_container=None) -> bool:
        """Validate packet integrity and calculate latency"""
        if len(packet) < self.packet_header_size:
            return False
        
        try:
            sequence = struct.unpack('>I', packet[0:4])[0]
            send_time = struct.unpack('>d', packet[4:12])[0]
            expected_hash = packet[12:44]
            payload = packet[44:]
            
            # Verify hash
            actual_hash = hashlib.sha256(payload).digest()
            if actual_hash != expected_hash:
                return False
            
            # Calculate latency
            receive_time = time.time()
            latency = (receive_time - send_time) * 1000  # Convert to ms
            
            if latency_container is not None:
                latency_container.append(latency)
            else:
                latency_key = 'latency_samples' + stats_key
                if latency_key in self.stats:
                    self.stats_mutex.lock()
                    self.stats[latency_key].append(latency)
                    self.stats_mutex.unlock()
            
            return True
        except Exception:
            return False
    
    def _calculate_packet_loss(self) -> float:
        """Calculate packet loss percentage"""
        sent = self.stats['packets_sent']
        received = self.stats['packets_received']
        if sent == 0:
            return 0.0
        return ((sent - received) / sent) * 100.0
    
    def _calculate_corruption(self) -> float:
        """Calculate corruption percentage"""
        received = self.stats['packets_received']
        corrupt = self.stats['packets_corrupt']
        total_received = received + corrupt
        if total_received == 0:
            return 0.0
        return (corrupt / total_received) * 100.0
    
    def _recalculate_receiver_totals(self):
        """Aggregate receiver statistics into legacy fields"""
        total_packets_received = sum(r['packets_received'] for r in self.receiver_stats)
        total_corrupt = sum(r['packets_corrupt'] for r in self.receiver_stats)
        total_bytes = sum(r['bytes_received_total'] for r in self.receiver_stats)
        total_valid_bytes = sum(r['bytes_received_valid'] for r in self.receiver_stats)
        
        self.stats['packets_received'] = total_packets_received
        self.stats['packets_corrupt'] = total_corrupt
        self.stats['bytes_received_total'] = total_bytes
        self.stats['bytes_received_valid'] = total_valid_bytes
        self.stats['bytes_received'] = total_valid_bytes
    
    def _update_statistics(self):
        """Update statistics display"""
        self.stats_mutex.lock()
        
        # Calculate current rates if test is running
        running_elapsed = None
        if self.test_running and self.stats['start_time']:
            running_elapsed = time.time() - self.stats['start_time']
            if running_elapsed > 0:
                self.stats['data_rate_total_bps'] = (self.stats['bytes_received_total'] * 8) / running_elapsed
                self.stats['data_rate_total_kbps'] = self.stats['data_rate_total_bps'] / 1000
                self.stats['data_rate_valid_bps'] = (self.stats['bytes_received_valid'] * 8) / running_elapsed
                self.stats['data_rate_valid_kbps'] = self.stats['data_rate_valid_bps'] / 1000
                self.stats['send_rate_bps'] = (self.stats['bytes_sent'] * 8) / running_elapsed
                self.stats['send_rate_kbps'] = self.stats['send_rate_bps'] / 1000
        
        elapsed_for_rates = self.stats['elapsed_time']
        if elapsed_for_rates is None and running_elapsed is not None:
            elapsed_for_rates = running_elapsed
        
        packets_sent_total = self.stats['packets_sent']
        receiver_display = []
        if elapsed_for_rates and elapsed_for_rates > 0:
            for rstat in self.receiver_stats:
                rstat['valid_rate_bps'] = (rstat['bytes_received_valid'] * 8) / elapsed_for_rates
                rstat['valid_rate_kbps'] = rstat['valid_rate_bps'] / 1000
                receiver_display.append({
                    'valid_rate_kbps': rstat['valid_rate_kbps'],
                    'packets_received': rstat['packets_received'],
                    'packet_loss': ((packets_sent_total - rstat['packets_received']) / packets_sent_total * 100.0
                                    if packets_sent_total else None),
                    'avg_latency': (sum(rstat['latency_samples']) / len(rstat['latency_samples'])
                                    if rstat['latency_samples'] else None)
                })
        else:
            for rstat in self.receiver_stats:
                receiver_display.append({
                    'valid_rate_kbps': None,
                    'packets_received': rstat['packets_received'],
                    'packet_loss': ((packets_sent_total - rstat['packets_received']) / packets_sent_total * 100.0
                                    if packets_sent_total else None),
                    'avg_latency': (sum(rstat['latency_samples']) / len(rstat['latency_samples'])
                                    if rstat['latency_samples'] else None)
                })
        
        sender_send_rate = self.stats.get('send_rate_kbps')
        packets_sent = packets_sent_total
        bytes_sent = self.stats['bytes_sent']
        elapsed_display = self.stats['elapsed_time']
        if elapsed_display is None and running_elapsed is not None:
            elapsed_display = running_elapsed
        
        self.stats_mutex.unlock()
        
        # Sender labels
        if sender_send_rate is not None:
            self.stats_labels['sender_send_rate'].setText(
                f"{self.stats['send_rate_bps']:.2f} bps ({sender_send_rate:.2f} kbps)")
        else:
            self.stats_labels['sender_send_rate'].setText("N/A")
        
        self.stats_labels['sender_packets_sent'].setText(str(packets_sent))
        self.stats_labels['sender_bytes_sent'].setText(str(bytes_sent))
        if elapsed_display is not None:
            self.stats_labels['sender_test_duration'].setText(f"{elapsed_display:.2f} s")
        else:
            self.stats_labels['sender_test_duration'].setText("N/A")
        
        # Receiver columns
        for idx, display in enumerate(receiver_display):
            rate_label = self.stats_labels.get(f"receiver_{idx}_valid_rate")
            if rate_label:
                if display['valid_rate_kbps'] is not None:
                    rate_label.setText(f"{display['valid_rate_kbps']:.2f} kbps")
                else:
                    rate_label.setText("N/A")
            
            loss_label = self.stats_labels.get(f"receiver_{idx}_packet_loss")
            if loss_label:
                loss_label.setText(f"{display['packet_loss']:.2f}%" if display['packet_loss'] is not None else "N/A")
            
            latency_label = self.stats_labels.get(f"receiver_{idx}_avg_latency")
            if latency_label:
                latency_label.setText(f"{display['avg_latency']:.2f} ms" if display['avg_latency'] is not None else "N/A")
            
            packets_label = self.stats_labels.get(f"receiver_{idx}_packets_received")
            if packets_label:
                packets_label.setText(str(display['packets_received']))
    
    def _clear_results(self):
        """Clear test results and log"""
        self.stats_mutex.lock()
        for key in ['bytes_sent', 'bytes_received', 'bytes_received_valid', 'bytes_received_total',
                    'packets_sent', 'packets_received', 'packets_corrupt',
                    'bytes_sent_2', 'bytes_received_2', 'bytes_received_valid_2', 'bytes_received_total_2',
                    'packets_sent_2', 'packets_received_2', 'packets_corrupt_2']:
            if key in self.stats:
                self.stats[key] = 0
        if 'latency_samples' in self.stats:
            self.stats['latency_samples'].clear()
        if 'latency_samples_2' in self.stats:
            self.stats['latency_samples_2'].clear()
        
        for rstat in self.receiver_stats:
            rstat['bytes_received_total'] = 0
            rstat['bytes_received_valid'] = 0
            rstat['packets_received'] = 0
            rstat['packets_corrupt'] = 0
            rstat['valid_rate_bps'] = None
            rstat['valid_rate_kbps'] = None
            rstat['packet_loss'] = None
            rstat['avg_latency'] = None
            rstat['latency_samples'].clear()
        
        self.stats['start_time'] = None
        self.stats['end_time'] = None
        self.stats['elapsed_time'] = None
        self.stats['data_rate_total_bps'] = None
        self.stats['data_rate_total_kbps'] = None
        self.stats['data_rate_valid_bps'] = None
        self.stats['data_rate_valid_kbps'] = None
        self.stats['send_rate_bps'] = None
        self.stats['send_rate_kbps'] = None
        self.stats_mutex.unlock()
        
        self.log_text.clear()
        self._update_statistics()


def main():
    app = QApplication(sys.argv)
    window = T900DataRateTestQt()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

