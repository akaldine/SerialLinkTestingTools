#!/usr/bin/env python3
"""
Tianze T900 Data Rate Test Tool (PyQt5 Version)
Tests end-to-end data rate, packet corruption, and latency between two T900 radios.
"""

import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                             QLabel, QPushButton, QComboBox, QLineEdit, QTextEdit, QGroupBox,
                             QGridLayout, QSplitter, QMessageBox)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont
from typing import Optional, List

from t900_viewmodel import T900DataRateViewModel, TestConfig
from t900_sweep_test_qt_gui import SweepTestDialog


class T900DataRateTestQt(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("T900 Data Rate Test Tool")
        self.setGeometry(100, 100, 1200, 800)
        
        # Create ViewModel
        self.viewmodel = T900DataRateViewModel(num_receivers=3)
        
        # Connect ViewModel signals
        self.viewmodel.log_message.connect(self._append_log)
        self.viewmodel.stats_changed.connect(self._on_stats_changed)
        self.viewmodel.test_state_changed.connect(self._on_test_state_changed)
        self.viewmodel.connection_changed.connect(self._on_connection_changed)
        
        self.sweep_dialog = None
        
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
        self._refresh_ports()
        self._update_button_states()
    
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
        conn_group = QGroupBox("Connections")
        conn_layout = QVBoxLayout(conn_group)
        
        # Refresh button
        refresh_btn = QPushButton("Refresh Ports")
        refresh_btn.clicked.connect(self._refresh_ports)
        conn_layout.addWidget(refresh_btn)
        
        # Combined connections layout (sender + receivers)
        connections_layout = QGridLayout()
        connections_layout.setSpacing(12)
        connections_layout.setColumnStretch(0, 1)
        connections_layout.setColumnStretch(1, 1)
        
        # Sender block
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
        
        connections_layout.addWidget(sender_group, 0, 0)
        
        # Receivers
        self.receiver_port_combos.clear()
        self.receiver_baud_combos.clear()
        self.receiver_connect_btns.clear()
        self.receiver_status_labels.clear()
        
        receiver_positions = [(0, 1), (1, 0), (1, 1)]
        for idx in range(self.viewmodel.num_receivers):
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
            
            row, col = receiver_positions[idx]
            connections_layout.addWidget(group, row, col)
        
        conn_layout.addLayout(connections_layout)
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
        
        # Direction (fixed)
        direction_layout = QHBoxLayout()
        direction_layout.addWidget(QLabel("Direction: Sender → Receiver (fixed)"))
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
        
        self.sweep_btn = QPushButton("Sweep Test")
        self.sweep_btn.clicked.connect(self._show_sweep_test)
        control_layout.addWidget(self.sweep_btn)
        
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
        
        for idx in range(self.viewmodel.num_receivers):
            receiver_group = QGroupBox(f"Receiver {idx + 1}")
            receiver_layout = QGridLayout(receiver_group)
            receiver_metrics = [
                ("Valid Rate", f"receiver_{idx}_valid_rate"),
                ("Packet Loss", f"receiver_{idx}_packet_loss"),
                ("Avg Latency", f"receiver_{idx}_avg_latency"),
                ("Packets Received", f"receiver_{idx}_packets_received"),
                ("Bytes Received", f"receiver_{idx}_bytes_received"),
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
        ports = self.viewmodel.get_available_ports()
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
        else:
            self.sender_port_combo.setCurrentIndex(-1)
            for combo in self.receiver_port_combos:
                combo.setCurrentIndex(-1)
    
    def _connect_sender(self):
        """Connect to sender port"""
        port = self.sender_port_combo.currentText()
        baud = int(self.sender_baud_combo.currentText())
        
        success, message = self.viewmodel.connect_sender(port, baud)
        if success:
            if message == "Disconnected":
                self.sender_connect_btn.setText("Connect")
                self.sender_status_label.setText("Disconnected")
                self.sender_status_label.setStyleSheet("color: red;")
            else:
                self.sender_connect_btn.setText("Disconnect")
                self.sender_status_label.setText(message)
                self.sender_status_label.setStyleSheet("color: green;")
            self._update_button_states()
        else:
            QMessageBox.critical(self, "Connection Error", message)
    
    def _connect_receiver(self, index: int):
        """Connect/disconnect a receiver port"""
        port = self.receiver_port_combos[index].currentText()
        baud = int(self.receiver_baud_combos[index].currentText())
        
        success, message = self.viewmodel.connect_receiver(index, port, baud)
        if success:
            if message == "Disconnected":
                self.receiver_connect_btns[index].setText("Connect")
                self.receiver_status_labels[index].setText("Disconnected")
                self.receiver_status_labels[index].setStyleSheet("color: red;")
            else:
                self.receiver_connect_btns[index].setText("Disconnect")
                self.receiver_status_labels[index].setText(message)
                self.receiver_status_labels[index].setStyleSheet("color: green;")
            self._update_button_states()
        else:
            QMessageBox.critical(self, "Connection Error", message)
    
    def _update_button_states(self):
        """Update button states based on connection status"""
        can_start = self.viewmodel.can_start_test()
        
        if not self.viewmodel.test_running:
            self.start_btn.setEnabled(can_start)
        else:
            self.start_btn.setEnabled(False)
    
    def _append_log(self, formatted_message: str):
        """Append log text (UI thread only)"""
        if hasattr(self, 'log_text') and self.log_text is not None:
            self.log_text.append(formatted_message)
    
    def _on_stats_changed(self):
        """Handle stats changed signal"""
        # Statistics will be updated by the timer
        pass
    
    def _on_test_state_changed(self, running: bool):
        """Handle test state changed signal"""
        if running:
            self.start_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        else:
            self.start_btn.setEnabled(self.viewmodel.can_start_test())
            self.stop_btn.setEnabled(False)
    
    def _on_connection_changed(self):
        """Handle connection changed signal"""
        self._update_button_states()
    
    def _update_total_packet_size(self):
        """Update the payload size label when total size changes"""
        try:
            total = int(self.write_size_edit.text())
            if total < 0:
                return
            payload = max(total - self.viewmodel.packet_header_size, 0)
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
            payload = max(total_size - self.viewmodel.packet_header_size, 0)
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
            min_size = self.viewmodel.packet_header_size + 1
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
            payload = max(buffer_size - self.viewmodel.packet_header_size, 0)
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
            min_size = self.viewmodel.packet_header_size + 1
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
            min_size = self.viewmodel.packet_header_size + 1
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
    
    def _read_rssi(self):
        """Read RSSI values from sender and all receivers"""
        if not self.viewmodel.read_rssi():
            QMessageBox.warning(self, "Warning", 
                              "All connections must be established before reading RSSI")
    
    def _start_test(self):
        """Start the data rate test"""
        if self.viewmodel.test_running:
            return
        
        # Get parameters based on input mode
        mode = self.input_mode_combo.currentText()
        config = TestConfig()
        config.mode = mode
        
        if mode == "Manual":
            try:
                config.total_size = int(self.write_size_edit.text())
                config.write_freq = float(self.write_freq_edit.text())
                config.test_length = float(self.test_length_edit.text())
                config.target_packets = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        elif mode == "Speed-Based":
            try:
                config.test_length = float(self.duration_edit.text())
                config.total_size = int(self.buffer_size_edit.text())
                config.write_freq = float(self.calc_write_freq_label.text())
                config.target_packets = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        else:  # Packet-Count
            try:
                config.total_size = int(self.packet_count_size_edit.text())
                config.write_freq = float(self.packet_count_freq_edit.text())
                config.target_packets = int(self.num_packets_edit.text())
                config.test_length = None
            except ValueError:
                QMessageBox.critical(self, "Invalid Input", "Please enter valid numeric values")
                return
        
        # Validate connections
        if not self.viewmodel.can_start_test():
            missing = []
            if not self.viewmodel.is_sender_connected():
                missing.append("Sender")
            for idx in range(self.viewmodel.num_receivers):
                if (self.viewmodel.receiver_connections[idx] is None or 
                    not self.viewmodel.receiver_connections[idx].is_open):
                    missing.append(f"Receiver {idx + 1}")
            if missing:
                QMessageBox.critical(self, "Error",
                                   f"Please connect all devices before starting the test "
                                   f"(missing: {', '.join(missing)})")
                return
        
        # Start test via ViewModel
        self.viewmodel.start_test(config)
    
    def _stop_test(self):
        """Stop the test"""
        self.viewmodel.stop_test()
    
    def _clear_results(self):
        """Clear test results and log"""
        self.viewmodel.clear_results()
        if hasattr(self, 'log_text') and self.log_text is not None:
            self.log_text.clear()
        self._update_statistics()
    
    def _update_statistics(self):
        """Update statistics display"""
        # Update ViewModel statistics first (all calculations happen there)
        self.viewmodel.update_statistics()
        
        # Get pre-calculated stats from ViewModel
        stats = self.viewmodel.stats
        receiver_stats = self.viewmodel.receiver_stats
        
        # Sender labels
        sender_send_rate = stats.get('send_rate_kbps')
        if sender_send_rate is not None:
            self.stats_labels['sender_send_rate'].setText(
                f"{stats['send_rate_bps']:.2f} bps ({sender_send_rate:.2f} kbps)")
        else:
            self.stats_labels['sender_send_rate'].setText("N/A")
        
        self.stats_labels['sender_packets_sent'].setText(str(stats['packets_sent']))
        self.stats_labels['sender_bytes_sent'].setText(str(stats['bytes_sent']))
        
        elapsed_display = stats.get('elapsed_display')
        if elapsed_display is not None:
            self.stats_labels['sender_test_duration'].setText(f"{elapsed_display:.2f} s")
        else:
            self.stats_labels['sender_test_duration'].setText("N/A")
        
        # Receiver columns (all values are pre-calculated in ViewModel)
        for idx, rstat in enumerate(receiver_stats):
            rate_label = self.stats_labels.get(f"receiver_{idx}_valid_rate")
            if rate_label:
                if rstat['valid_rate_kbps'] is not None:
                    rate_label.setText(f"{rstat['valid_rate_kbps']:.2f} kbps")
                else:
                    rate_label.setText("N/A")
            
            loss_label = self.stats_labels.get(f"receiver_{idx}_packet_loss")
            if loss_label:
                if rstat['packet_loss'] is not None:
                    loss_label.setText(f"{rstat['packet_loss']:.2f}%")
                else:
                    loss_label.setText("N/A")
            
            latency_label = self.stats_labels.get(f"receiver_{idx}_avg_latency")
            if latency_label:
                if rstat['avg_latency'] is not None:
                    latency_label.setText(f"{rstat['avg_latency']:.2f} ms")
                else:
                    latency_label.setText("N/A")
            
            packets_label = self.stats_labels.get(f"receiver_{idx}_packets_received")
            if packets_label:
                packets_label.setText(str(rstat['packets_received']))
            
            bytes_label = self.stats_labels.get(f"receiver_{idx}_bytes_received")
            if bytes_label:
                bytes_label.setText(str(rstat['bytes_received_total']))
    
    def _show_sweep_test(self):
        """Open the sweep test dialog"""
        if self.sweep_dialog is None or not self.sweep_dialog.isVisible():
            self.sweep_dialog = SweepTestDialog(self, self)
        self.sweep_dialog.show()
        self.sweep_dialog.raise_()
        self.sweep_dialog.activateWindow()


def main():
    app = QApplication(sys.argv)
    window = T900DataRateTestQt()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
