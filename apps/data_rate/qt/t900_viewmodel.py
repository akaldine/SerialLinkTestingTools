#!/usr/bin/env python3
"""
T900 Data Rate Test ViewModel
Encapsulates all application logic, separated from UI concerns.
"""

from PyQt5.QtCore import QObject, pyqtSignal, QMutex, QTimer
import serial
import serial.tools.list_ports
import threading
import time
import struct
import hashlib
from collections import deque
from typing import Optional, List, Dict, Any
from datetime import datetime


class TestConfig:
    """Configuration for a test run"""
    def __init__(self):
        self.mode: str = "Manual"  # "Manual", "Speed-Based", "Packet-Count"
        self.total_size: int = 145
        self.write_freq: float = 0.1
        self.test_length: Optional[float] = None  # For Manual/Speed-Based
        self.target_packets: Optional[int] = None  # For Packet-Count


class T900DataRateViewModel(QObject):
    """ViewModel for T900 Data Rate Test - encapsulates all business logic"""
    
    # Signals for UI updates
    log_message = pyqtSignal(str)
    stats_changed = pyqtSignal()  # Emitted when stats need UI refresh
    test_state_changed = pyqtSignal(bool)  # Emitted when test_running changes
    connection_changed = pyqtSignal()  # Emitted when connections change
    
    def __init__(self, num_receivers: int = 3):
        super().__init__()
        self.num_receivers = num_receivers
        self.active_receivers = num_receivers
        
        # Serial connections
        self.sender_connection: Optional[serial.Serial] = None
        self.receiver_connections: List[Optional[serial.Serial]] = [None] * num_receivers
        
        # Test state
        self.test_running = False
        self.test_end_time: Optional[float] = None
        self.target_packets: Optional[int] = None
        self.receiver_grace_period_end: Optional[float] = None
        self.current_write_interval: Optional[float] = None
        
        # Threading
        self.test_thread: Optional[threading.Thread] = None
        self.receiver_threads: List[Optional[threading.Thread]] = [None] * num_receivers
        self.monitor_thread: Optional[threading.Thread] = None
        
        # RSSI values
        self.rssi_current = {
            'sender': {'S123': None, 'S124': None},
            'receivers': [{'S123': None, 'S124': None} for _ in range(num_receivers)]
        }
        
        # Statistics
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
        }
        
        # Per-receiver statistics
        self.receiver_stats: List[Dict[str, Any]] = []
        for _ in range(num_receivers):
            self.receiver_stats.append(self._create_empty_receiver_stats())
        
        self.packet_header_size = 44  # 4 + 8 + 32
        self.stats_mutex = QMutex()
    
    def _create_empty_receiver_stats(self) -> Dict[str, Any]:
        return {
            'bytes_received_total': 0,
            'bytes_received_valid': 0,
            'packets_received': 0,
            'packets_corrupt': 0,
            'latency_samples': deque(maxlen=1000),
            'valid_rate_bps': None,
            'valid_rate_kbps': None,
            'packet_loss': None,
            'avg_latency': None,
        }

    def _reset_receiver_stats(self, index: Optional[int] = None):
        targets = range(self.num_receivers) if index is None else [index]
        for idx in targets:
            self.receiver_stats[idx] = self._create_empty_receiver_stats()

    def get_available_ports(self) -> List[str]:
        """Get list of available serial ports (filtered to /dev/ttyUSB*)"""
        all_ports = [port.device for port in serial.tools.list_ports.comports()]
        return [port for port in all_ports if port.startswith("/dev/ttyUSB")]
    
    def connect_sender(self, port: str, baud: int) -> tuple[bool, str]:
        """Connect to sender port. Returns (success, status_message)"""
        try:
            if self.sender_connection and self.sender_connection.is_open:
                self.disconnect_sender()
                return (True, "Disconnected")
            
            if not port:
                return (False, "Please select a sender port")
            
            self.sender_connection = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            self._log(f"Sender connected to {port} at {baud} baud")
            self.connection_changed.emit()
            return (True, f"Connected @ {baud} baud")
            
        except Exception as e:
            error_msg = f"Failed to connect sender: {str(e)}"
            self._log(f"Sender connection failed: {str(e)}")
            return (False, error_msg)
    
    def disconnect_sender(self):
        """Disconnect sender"""
        try:
            if self.sender_connection and self.sender_connection.is_open:
                self.sender_connection.close()
            self.sender_connection = None
            self._log("Sender disconnected")
            self.connection_changed.emit()
        except Exception as e:
            self._log(f"Error disconnecting sender: {str(e)}")
    
    def connect_receiver(self, index: int, port: str, baud: int) -> tuple[bool, str]:
        """Connect to receiver port. Returns (success, status_message)"""
        try:
            if index < 0 or index >= self.num_receivers:
                return (False, f"Invalid receiver index: {index}")
            if index >= self.active_receivers:
                return (False, f"Receiver {index + 1} is currently inactive")
            
            current_conn = self.receiver_connections[index]
            if current_conn is not None and current_conn.is_open:
                self.disconnect_receiver(index)
                return (True, "Disconnected")
            
            if not port:
                return (False, f"Please select a port for Receiver {index + 1}")
            
            new_conn = serial.Serial(port, baud, timeout=1)
            time.sleep(0.1)
            
            self.receiver_connections[index] = new_conn
            self._log(f"Receiver {index + 1} connected to {port} at {baud} baud")
            self.connection_changed.emit()
            return (True, f"Connected @ {baud} baud")
            
        except Exception as e:
            error_msg = f"Failed to connect Receiver {index + 1}: {str(e)}"
            self._log(f"Receiver {index + 1} connection failed: {str(e)}")
            return (False, error_msg)
    
    def disconnect_receiver(self, index: int):
        """Disconnect receiver"""
        try:
            if 0 <= index < self.num_receivers:
                conn = self.receiver_connections[index]
                if conn is not None and conn.is_open:
                    conn.close()
                self.receiver_connections[index] = None
                self._log(f"Receiver {index + 1} disconnected")
                self.connection_changed.emit()
        except Exception as e:
            self._log(f"Error disconnecting receiver {index + 1}: {str(e)}")
    
    def is_sender_connected(self) -> bool:
        """Check if sender is connected"""
        return (self.sender_connection is not None and 
                hasattr(self.sender_connection, 'is_open') and 
                self.sender_connection.is_open)
    
    def are_all_receivers_connected(self) -> bool:
        """Check if all receivers are connected"""
        for idx in range(self.active_receivers):
            conn = self.receiver_connections[idx]
            if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
                return False
        return True
    
    def can_start_test(self) -> bool:
        """Check if test can be started"""
        return (not self.test_running and 
                self.is_sender_connected() and 
                self.are_all_receivers_connected())

    def set_active_receivers(self, count: int):
        """Set how many receivers are active (1..num_receivers)"""
        count = max(1, min(count, self.num_receivers))
        if count == self.active_receivers:
            return
        previous = self.active_receivers
        if count < self.active_receivers:
            for idx in range(count, self.active_receivers):
                self.disconnect_receiver(idx)
                self._reset_receiver_stats(idx)
        self.active_receivers = count
        if count > previous:
            for idx in range(previous, count):
                self._reset_receiver_stats(idx)
        self.connection_changed.emit()
        self.stats_changed.emit()
    
    def start_test(self, config: TestConfig):
        """Start a test with the given configuration"""
        if self.test_running:
            return
        
        # Validate packet size
        if config.total_size < self.packet_header_size + 1:
            self._log(f"Error: Total packet size must be at least {self.packet_header_size + 1} bytes")
            return
        
        # Clear buffers
        self._clear_serial_buffers()
        
        # Reset statistics
        self.stats_mutex.lock()
        for key in ['bytes_sent', 'bytes_received', 'bytes_received_valid', 'bytes_received_total',
                    'packets_sent', 'packets_received', 'packets_corrupt']:
            if key in self.stats:
                self.stats[key] = 0
        if 'latency_samples' in self.stats:
            self.stats['latency_samples'].clear()
        
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
        self.receiver_grace_period_end = None
        self.stats_mutex.unlock()
        
        self.current_write_interval = config.write_freq
        self.test_running = True
        self.target_packets = config.target_packets
        self.test_end_time = time.time() + config.test_length if config.test_length else None
        self.receiver_threads = [None] * self.num_receivers
        
        # Log test start
        mode_str = config.mode.lower().replace("-", " ")
        self._log(f"Starting test: {mode_str} mode")
        self._log(f"Total packet size: {config.total_size} bytes")
        if config.mode == "Speed-Based":
            self._log(f"Calculated write frequency: {config.write_freq} s")
        self._log(f"Test started - timer started")
        if config.test_length:
            self._log(f"Test will auto-stop after {config.test_length} seconds")
        elif config.target_packets:
            self._log(f"Test will stop after {config.target_packets} packets sent")
        
        # Start receiver threads (only active receivers)
        for idx in range(self.active_receivers):
            conn = self.receiver_connections[idx]
            self._log(f"Starting receiver {idx + 1}")
            thread = threading.Thread(
                target=self._receiver_thread,
                args=(conn, idx, config.total_size, config.test_length, config.target_packets),
                daemon=True
            )
            self.receiver_threads[idx] = thread
            thread.start()
        
        # Start sender thread
        self._log(f"Starting sender: total {config.total_size} bytes (payload {config.total_size - self.packet_header_size}) "
                  f"every {config.write_freq}s for {config.test_length if config.test_length else 'N/A'}s")
        self.test_thread = threading.Thread(
            target=self._sender_thread,
            args=(self.sender_connection, config.total_size, config.write_freq, config.test_length, config.target_packets),
            daemon=True
        )
        self.test_thread.start()
        
        # Start monitor thread for auto-stop
        if config.test_length or config.target_packets:
            self.monitor_thread = threading.Thread(target=self._monitor_test_end, daemon=True)
            self.monitor_thread.start()
        
        self.test_state_changed.emit(True)
        self.stats_changed.emit()
    
    def stop_test(self):
        """Stop the test and calculate final statistics"""
        if not self.test_running and self.stats.get('elapsed_time') is not None:
            # Already stopped and finalized
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
                self.stats['data_rate_total_bps'] = (self.stats['bytes_received_total'] * 8) / elapsed
                self.stats['data_rate_total_kbps'] = self.stats['data_rate_total_bps'] / 1000
                self.stats['data_rate_valid_bps'] = (self.stats['bytes_received_valid'] * 8) / elapsed
                self.stats['data_rate_valid_kbps'] = self.stats['data_rate_valid_bps'] / 1000
                
                # Calculate send rate
                total_sent = self.stats['bytes_sent']
                self.stats['send_rate_bps'] = (total_sent * 8) / elapsed
                self.stats['send_rate_kbps'] = self.stats['send_rate_bps'] / 1000
        
        self.stats['end_time'] = time.time()
        self.stats_mutex.unlock()
        
        # Update statistics for final calculations (will lock mutex internally)
        self.update_statistics()
        
        # Lock mutex again to read stats for logging
        self.stats_mutex.lock()
        
        self._log("Test stopped")
        self._log("=" * 50)
        self._log("=== Test Statistics ===")
        
        # Overall statistics
        self._log(f"Elapsed Time: {self.stats.get('elapsed_time', 0):.2f} s")
        self._log(f"Bytes Sent: {self.stats.get('bytes_sent', 0)}")
        self._log(f"Bytes Received (Total): {self.stats.get('bytes_received_total', 0)}")
        self._log(f"Bytes Received (Valid): {self.stats.get('bytes_received_valid', 0)}")
        self._log(f"Packets Sent: {self.stats.get('packets_sent', 0)}")
        self._log(f"Packets Received: {self.stats.get('packets_received', 0)}")
        self._log(f"Packets Corrupt: {self.stats.get('packets_corrupt', 0)}")
        
        # Data rates
        self._log(f"Send Rate: {self.stats.get('send_rate_bps', 0):.2f} bps ({self.stats.get('send_rate_kbps', 0):.2f} kbps)")
        self._log(f"Data Rate (Total): {self.stats.get('data_rate_total_bps', 0):.2f} bps ({self.stats.get('data_rate_total_kbps', 0):.2f} kbps)")
        self._log(f"Data Rate (Valid): {self.stats.get('data_rate_valid_bps', 0):.2f} bps ({self.stats.get('data_rate_valid_kbps', 0):.2f} kbps)")
        
        # Overall packet loss and corruption
        if self.stats['packets_sent'] > 0:
            loss_percent = ((self.stats['packets_sent'] - self.stats['packets_received']) /
                          self.stats['packets_sent']) * 100.0
        else:
            loss_percent = 0.0
        self._log(f"Overall Packet Loss: {loss_percent:.2f}%")
        
        total_received = self.stats['packets_received']
        total_corrupt = self.stats['packets_corrupt']
        if total_received > 0:
            corrupt_percent = (total_corrupt / total_received) * 100.0
        else:
            corrupt_percent = 0.0
        self._log(f"Overall Corrupt Packets: {corrupt_percent:.2f}%")
        
        # Per-receiver statistics
        self._log("")
        self._log("=== Per-Receiver Statistics ===")
        for idx in range(self.active_receivers):
            rstat = self.receiver_stats[idx]
            self._log(f"--- Receiver {idx + 1} ---")
            self._log(f"  Bytes Received (Total): {rstat.get('bytes_received_total', 0)}")
            self._log(f"  Bytes Received (Valid): {rstat.get('bytes_received_valid', 0)}")
            self._log(f"  Packets Received: {rstat.get('packets_received', 0)}")
            self._log(f"  Packets Corrupt: {rstat.get('packets_corrupt', 0)}")
            
            if rstat.get('valid_rate_kbps') is not None:
                self._log(f"  Valid Data Rate: {rstat['valid_rate_kbps']:.2f} kbps")
            else:
                self._log(f"  Valid Data Rate: N/A")
            
            if rstat.get('packet_loss') is not None:
                self._log(f"  Packet Loss: {rstat['packet_loss']:.2f}%")
            else:
                self._log(f"  Packet Loss: N/A")
            
            if rstat.get('avg_latency') is not None:
                self._log(f"  Average Latency: {rstat['avg_latency']:.2f} ms")
                if rstat['latency_samples']:
                    min_latency = min(rstat['latency_samples'])
                    max_latency = max(rstat['latency_samples'])
                    self._log(f"  Latency Range: {min_latency:.2f} - {max_latency:.2f} ms")
            else:
                self._log(f"  Average Latency: N/A")
        
        self._log("=" * 50)
        
        self.stats_mutex.unlock()
        
        self.test_state_changed.emit(False)
        self.stats_changed.emit()
    
    def clear_results(self):
        """Clear test results"""
        self.stats_mutex.lock()
        for key in ['bytes_sent', 'bytes_received', 'bytes_received_valid', 'bytes_received_total',
                    'packets_sent', 'packets_received', 'packets_corrupt']:
            if key in self.stats:
                self.stats[key] = 0
        if 'latency_samples' in self.stats:
            self.stats['latency_samples'].clear()
        
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
        self.current_write_interval = None
        self.stats_mutex.unlock()
        
        self.stats_changed.emit()
    
    def _sender_thread(self, conn: serial.Serial, total_size: int, 
                      write_freq: float, test_length: Optional[float], target_packets: Optional[int]):
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
                self.stats['bytes_sent'] += len(packet)
                self.stats['packets_sent'] += 1
                self.stats_mutex.unlock()
                
                sequence += 1
                
                # Calculate next packet time (interval between packet starts)
                next_packet_time = next_packet_time + write_freq
                
            except Exception as e:
                self._log(f"Error sending packet: {str(e)}")
                break
    
    def _receiver_thread(self, conn: serial.Serial, receiver_index: int, 
                        expected_packet_size: int, test_length: Optional[float], target_packets: Optional[int]):
        """Receiver thread - receives and validates packets for a specific receiver"""
        if conn is None or not hasattr(conn, 'is_open') or not conn.is_open:
            return
        
        self._clear_serial_buffers()
        
        buffer = b''
        latency_store = self.receiver_stats[receiver_index]['latency_samples']
        
        while self.test_running or (
            self.receiver_grace_period_end is not None and time.time() < self.receiver_grace_period_end
        ):
            try:
                if conn.in_waiting > 0:
                    data = conn.read(conn.in_waiting)
                    buffer += data
                    
                    # Process complete packets
                    while len(buffer) >= expected_packet_size:
                        packet = buffer[:expected_packet_size]
                        buffer = buffer[expected_packet_size:]
                        
                        valid = self._validate_packet(packet, latency_store)
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
                        self._log(f"Target of {self.target_packets} packets sent - waiting for final interval...")
                        # Capture end_time NOW (when target packets are sent)
                        self.stats['end_time'] = time.time()
                        self.test_running = False
                        
                        extra_wait = self.current_write_interval or 0
                        if extra_wait > 0:
                            self.receiver_grace_period_end = time.time() + extra_wait
                            time.sleep(extra_wait)
                        else:
                            self.receiver_grace_period_end = None
                        
                        self._log("Auto-stopping after final interval...")
                        QTimer.singleShot(0, self.stop_test)
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
                        QTimer.singleShot(0, self.stop_test)
                        break
                time.sleep(0.1)  # Check every 100ms
        except Exception as e:
            self._log(f"Monitor thread error: {str(e)}")
            self.test_running = False
            QTimer.singleShot(0, self.stop_test)
    
    def _create_packet(self, sequence: int, payload: bytes) -> bytes:
        """Create a packet with sequence, timestamp, hash, and payload"""
        timestamp = time.time()
        seq_bytes = struct.pack('>I', sequence)
        time_bytes = struct.pack('>d', timestamp)
        hash_bytes = hashlib.sha256(payload).digest()
        return seq_bytes + time_bytes + hash_bytes + payload
    
    def _validate_packet(self, packet: bytes, latency_container: deque) -> bool:
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
            
            return True
        except Exception:
            return False
    
    def _recalculate_receiver_totals(self):
        """Aggregate receiver statistics into legacy fields"""
        active_stats = self.receiver_stats[:self.active_receivers] if self.active_receivers > 0 else []
        receiver_count = len(active_stats) if active_stats else 1
        
        total_packets_received = sum(r['packets_received'] for r in active_stats)
        total_corrupt = sum(r['packets_corrupt'] for r in active_stats)
        total_bytes = sum(r['bytes_received_total'] for r in active_stats)
        total_valid_bytes = sum(r['bytes_received_valid'] for r in active_stats)
        
        avg_packets_received = total_packets_received / receiver_count
        avg_corrupt = total_corrupt / receiver_count
        avg_bytes = total_bytes / receiver_count
        avg_valid_bytes = total_valid_bytes / receiver_count
        
        self.stats['packets_received'] = avg_packets_received
        self.stats['packets_corrupt'] = avg_corrupt
        self.stats['bytes_received_total'] = avg_bytes
        self.stats['bytes_received_valid'] = avg_valid_bytes
        self.stats['bytes_received'] = avg_valid_bytes
    
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
    
    def read_rssi(self) -> bool:
        """Read RSSI values from sender and all receivers. Returns True if successful."""
        if not self.is_sender_connected():
            return False
        
        disconnected = [idx for idx in range(self.active_receivers)
                        if (self.receiver_connections[idx] is None or
                            not hasattr(self.receiver_connections[idx], 'is_open') or
                            not self.receiver_connections[idx].is_open)]
        if disconnected:
            return False
        
        self._log("=== Reading RSSI ===")
        sender_rssi = self._read_rssi_from_device("Sender", self.sender_connection)
        self.rssi_current['sender'] = sender_rssi
        self._log(f"Sender RSSI -> S123: {sender_rssi['S123']} dBm, S124: {sender_rssi['S124']} dBm")
        
        for idx in range(self.active_receivers):
            conn = self.receiver_connections[idx]
            rssi = self._read_rssi_from_device(f"Receiver {idx + 1}", conn)
            self.rssi_current['receivers'][idx] = rssi
            self._log(f"Receiver {idx + 1} RSSI -> S123: {rssi['S123']} dBm, S124: {rssi['S124']} dBm")
            time.sleep(0.2)
        
        self._log("RSSI capture complete.")
        return True
    
    def update_statistics(self):
        """Update statistics calculations (called periodically from UI)"""
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
        
        # Calculate elapsed time for display
        elapsed_for_rates = self.stats['elapsed_time']
        if elapsed_for_rates is None and running_elapsed is not None:
            elapsed_for_rates = running_elapsed
        self.stats['elapsed_display'] = elapsed_for_rates
        
        # Calculate per-receiver statistics
        packets_sent_total = self.stats['packets_sent']
        if elapsed_for_rates and elapsed_for_rates > 0:
            for idx, rstat in enumerate(self.receiver_stats):
                if idx < self.active_receivers:
                    rstat['valid_rate_bps'] = (rstat['bytes_received_valid'] * 8) / elapsed_for_rates
                    rstat['valid_rate_kbps'] = rstat['valid_rate_bps'] / 1000
                else:
                    rstat['valid_rate_bps'] = None
                    rstat['valid_rate_kbps'] = None
        else:
            for idx, rstat in enumerate(self.receiver_stats):
                if idx >= self.active_receivers:
                    rstat['valid_rate_bps'] = None
                    rstat['valid_rate_kbps'] = None
        
        # Calculate packet loss and average latency for each receiver
        for idx, rstat in enumerate(self.receiver_stats):
            if idx >= self.active_receivers:
                rstat['packet_loss'] = None
                rstat['avg_latency'] = None
                continue
            # Packet loss percentage
            if packets_sent_total > 0:
                rstat['packet_loss'] = ((packets_sent_total - rstat['packets_received']) / packets_sent_total) * 100.0
            else:
                rstat['packet_loss'] = None
            
            # Average latency
            if rstat['latency_samples']:
                rstat['avg_latency'] = sum(rstat['latency_samples']) / len(rstat['latency_samples'])
            else:
                rstat['avg_latency'] = None
        
        self.stats_mutex.unlock()
        self.stats_changed.emit()
    
    def _log(self, message: str):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        formatted = f"[{timestamp}] {message}"
        self.log_message.emit(formatted)


