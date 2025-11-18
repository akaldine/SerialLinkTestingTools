#!/usr/bin/env python3
"""
Tianze T900 Radio Configuration GUI
A graphical interface for configuring Tianze T900 radios via AT commands.
"""

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import serial
import serial.tools.list_ports
import threading
import time
from typing import Optional, Dict, Any


class T900ConfigGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Tianze T900 Radio Configuration Tool")
        self.root.geometry("900x750")
        
        self.serial_connection: Optional[serial.Serial] = None
        self.response_buffer = ""
        self.at_mode = False  # Track if we're in AT command mode
        
        # Register definitions with their properties
        self.registers = self._define_registers()
        
        # Create GUI
        self._create_widgets()
        
    def _define_registers(self) -> Dict[str, Dict[str, Any]]:
        """Define all T900 registers with their properties"""
        return {
            'S101': {
                'name': 'Operating Mode',
                'type': 'choice',
                'values': ['0 - Master', '1 - Repeater', '2 - Slave'],
                'default': '0',
                'description': 'Defines the role of each device on the network'
            },
            'S102': {
                'name': 'Serial Baud Rate',
                'type': 'choice',
                'values': [
                    '0 - 230400', '1 - 115200', '2 - 57600', '3 - 38400',
                    '4 - 28800', '5 - 19200', '6 - 14400', '7 - 9600 (Default)',
                    '8 - 7200', '9 - 4800', '15 - 460800', '16 - 921600'
                ],
                'default': '7',
                'description': 'Serial port baud rate'
            },
            'S103': {
                'name': 'Wireless Link Rate',
                'type': 'choice',
                'values': [
                    '0 - 172800 (default)', '1 - 230400', '2 - 276480',
                    '3 - 57600', '4 - 115200'
                ],
                'default': '0',
                'description': 'Communication rate of the entire network'
            },
            'S104': {
                'name': 'Network Address (ID)',
                'type': 'number',
                'min': 0,
                'max': 4294967295,
                'default': '1234567890',
                'description': 'Network address - all devices must have the same'
            },
            'S105': {
                'name': 'Unit Address (Local Address)',
                'type': 'number',
                'min': 0,
                'max': 65535,
                'default': '0',
                'description': 'Unique unit address for identification on the network'
            },
            'S108': {
                'name': 'Output Power (dBm)',
                'type': 'choice',
                'values': [
                    '20 - 100mW', '21 - 125mW', '22 - 160mW', '23 - 200mW',
                    '24 - 250mW', '25 - 320mW', '26 - 400mW', '27 - 500mW',
                    '28 - 630mW', '29 - 800mW', '30 - 1000mW (default)'
                ],
                'default': '30',
                'description': 'Transmitting power of the local device'
            },
            'S110': {
                'name': 'Serial Data Format',
                'type': 'choice',
                'values': ['1 - 8N1 (default)'],
                'default': '1',
                'description': 'Serial port data format (only 8N1 supported)'
            },
            'S113': {
                'name': 'Packet Retransmissions',
                'type': 'number',
                'min': 0,
                'max': 255,
                'default': '3',
                'description': 'Maximum number of packet retransmissions'
            },
            'S114': {
                'name': 'Repeater Index',
                'type': 'number',
                'min': 1,
                'max': 254,
                'default': '1',
                'description': 'Relative position of repeater on network'
            },
            'S118': {
                'name': 'Sync Address',
                'type': 'number',
                'min': 0,
                'max': 65535,
                'default': '0',
                'description': 'Address to synchronize from local address'
            },
            'S123': {
                'name': 'RSSI From Master (dBm)',
                'type': 'readonly',
                'description': 'Received signal strength from master (read-only)'
            },
            'S124': {
                'name': 'RSSI From Slave (dBm)',
                'type': 'readonly',
                'description': 'Received signal strength from slave (read-only)'
            },
            'S133': {
                'name': 'Network Type',
                'type': 'choice',
                'values': [
                    '0 - Point to Multipoint',
                    '1 - Point to Point',
                    '2 - Mesh with Center'
                ],
                'default': '0',
                'description': 'Network type - all devices must be the same'
            },
            'S140': {
                'name': 'Destination Address',
                'type': 'number',
                'min': 0,
                'max': 65535,
                'default': '0',
                'description': 'Address of subordinate device'
            },
            'S141': {
                'name': 'Repeater Y/N',
                'type': 'choice',
                'values': ['0 - Without repeater (default)', '1 - With repeater'],
                'default': '0',
                'description': 'Whether repeater exists in network (master only)'
            },
            'S142': {
                'name': 'Serial Channel Mode',
                'type': 'choice',
                'values': [
                    '0 - RS232 (default)',
                    '1 - RS485 half-duplex',
                    '2 - RS485 full-duplex'
                ],
                'default': '0',
                'description': 'Operating mode of data serial port'
            },
            'S143': {
                'name': 'Repeater Index Use GPIO',
                'type': 'choice',
                'values': [
                    '0 - Use S114 register (default)',
                    '1 - Use GPIO[4:1] to indicate repeater number'
                ],
                'default': '0',
                'description': 'Method to configure repeater serial number'
            },
            'S159': {
                'name': 'Encryption Enable',
                'type': 'choice',
                'values': ['0 - Disable encryption (default)', '1 - Enable encryption'],
                'default': '0',
                'description': 'Enable 256-bit data encryption'
            },
            'S160': {
                'name': 'Encryption Key',
                'type': 'text',
                'default': '',
                'description': '256-bit encryption key (hex string)'
            },
            'S244': {
                'name': 'Channel Access Mode',
                'type': 'choice',
                'values': ['0 - RTS/CTS', '1 - TDMA'],
                'default': '0',
                'description': 'How slave accesses the network'
            },
            'S221': {
                'name': 'Unit Address Max for TDMA',
                'type': 'number',
                'min': 0,
                'max': 65535,
                'default': '6',
                'description': 'Maximum address for master polling in TDMA mode'
            },
            'S220': {
                'name': 'TDMA TX Time Slot',
                'type': 'number',
                'min': 0,
                'max': 65535,
                'default': '15',
                'description': 'Maximum number of TDMA slots in TDMA_AUTO mode'
            }
        }
    
    def _create_widgets(self):
        """Create the main GUI widgets"""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Connection tab
        self.connection_frame = ttk.Frame(notebook)
        notebook.add(self.connection_frame, text="Connection")
        self._create_connection_tab()
        
        # Device Info tab
        self.info_frame = ttk.Frame(notebook)
        notebook.add(self.info_frame, text="Device Information")
        self._create_info_tab()
        
        # Configuration tab
        self.config_frame = ttk.Frame(notebook)
        notebook.add(self.config_frame, text="Configuration")
        self._create_config_tab()
        
        # Command Console tab
        self.console_frame = ttk.Frame(notebook)
        notebook.add(self.console_frame, text="Command Console")
        self._create_console_tab()
        
    def _create_connection_tab(self):
        """Create connection management tab"""
        frame = self.connection_frame
        
        # Connection settings
        settings_frame = ttk.LabelFrame(frame, text="Serial Port Settings", padding=10)
        settings_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(settings_frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        self.port_var = tk.StringVar()
        port_combo = ttk.Combobox(settings_frame, textvariable=self.port_var, width=20)
        port_combo.grid(row=0, column=1, padx=5, pady=2)
        self.port_combo = port_combo
        
        ttk.Button(settings_frame, text="Refresh", command=self._refresh_ports).grid(row=0, column=2, padx=5)
        
        ttk.Label(settings_frame, text="Baud Rate:").grid(row=1, column=0, sticky=tk.W, pady=2)
        self.baud_var = tk.StringVar(value="9600")
        baud_combo = ttk.Combobox(settings_frame, textvariable=self.baud_var, 
                                  values=["9600", "115200", "57600", "38400", "19200", "14400"],
                                  width=20)
        baud_combo.grid(row=1, column=1, padx=5, pady=2)
        
        ttk.Label(settings_frame, text="Timeout:").grid(row=2, column=0, sticky=tk.W, pady=2)
        self.timeout_var = tk.StringVar(value="1")
        timeout_entry = ttk.Entry(settings_frame, textvariable=self.timeout_var, width=20)
        timeout_entry.grid(row=2, column=1, padx=5, pady=2)
        
        # AT Mode entry option (removed - no longer automatic)
        
        # Connection buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.connect_button = ttk.Button(button_frame, text="Connect", command=self._connect)
        self.connect_button.pack(side=tk.LEFT, padx=5)
        
        self.disconnect_button = ttk.Button(button_frame, text="Disconnect", 
                                           command=self._disconnect, state=tk.DISABLED)
        self.disconnect_button.pack(side=tk.LEFT, padx=5)
        
        self.enter_at_button = ttk.Button(button_frame, text="Enter AT Mode", 
                                          command=self._enter_at_mode, state=tk.DISABLED)
        self.enter_at_button.pack(side=tk.LEFT, padx=5)
        
        self.exit_at_button = ttk.Button(button_frame, text="Exit AT Mode (ATA)", 
                                         command=self._exit_at_mode, state=tk.DISABLED)
        self.exit_at_button.pack(side=tk.LEFT, padx=5)
        
        # Status
        status_frame = ttk.LabelFrame(frame, text="Connection Status", padding=10)
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = ttk.Label(status_frame, text="Disconnected", foreground="red")
        self.status_label.pack(anchor=tk.W)
        
        # Refresh ports on startup
        self._refresh_ports()
        
    def _create_info_tab(self):
        """Create device information tab"""
        frame = self.info_frame
        
        # Info display
        info_frame = ttk.LabelFrame(frame, text="Device Information", padding=10)
        info_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.info_text = scrolledtext.ScrolledText(info_frame, height=15, width=60)
        self.info_text.pack(fill=tk.BOTH, expand=True)
        
        # Query buttons
        button_frame = ttk.Frame(frame)
        button_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame, text="Query Hardware Version (ATI1)", 
                  command=lambda: self._send_command("ATI1")).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Query Firmware Version (ATI2)", 
                  command=lambda: self._send_command("ATI2")).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Query Software Version (ATI3)", 
                  command=lambda: self._send_command("ATI3")).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Query SN Number (ATI4)", 
                  command=lambda: self._send_command("ATI4")).pack(side=tk.LEFT, padx=5)
        
        button_frame2 = ttk.Frame(frame)
        button_frame2.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Button(button_frame2, text="Display All Parameters (AT&V)", 
                  command=self._display_all_parameters).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame2, text="Clear", 
                  command=lambda: self.info_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
        
    def _create_config_tab(self):
        """Create configuration tab with register editors"""
        frame = self.config_frame
        
        # Create scrollable canvas
        canvas = tk.Canvas(frame)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # Register widgets storage
        self.register_widgets = {}
        
        # Group registers by category
        basic_registers = ['S101', 'S102', 'S103', 'S104', 'S105', 'S108', 'S110', 'S113']
        network_registers = ['S133', 'S140', 'S141', 'S118', 'S114', 'S143']
        advanced_registers = ['S142', 'S159', 'S160', 'S244', 'S221', 'S220']
        read_only_registers = ['S123', 'S124']
        
        # Create register groups
        self._create_register_group(scrollable_frame, "Basic Settings", basic_registers, 0)
        self._create_register_group(scrollable_frame, "Network Settings", network_registers, 1)
        self._create_register_group(scrollable_frame, "Advanced Settings", advanced_registers, 2)
        self._create_register_group(scrollable_frame, "Read-Only Status", read_only_registers, 3)
        
        # Action buttons
        action_frame = ttk.Frame(scrollable_frame)
        action_frame.grid(row=4, column=0, columnspan=3, pady=20, padx=10, sticky=tk.W+tk.E)
        
        ttk.Button(action_frame, text="Read All Registers", 
                  command=self._read_all_registers).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Write All Registers", 
                  command=self._write_all_registers).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Save Configuration (AT&W)", 
                  command=self._save_configuration).pack(side=tk.LEFT, padx=5)
        ttk.Button(action_frame, text="Factory Defaults", 
                  command=self._show_factory_defaults).pack(side=tk.LEFT, padx=5)
        
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def _create_register_group(self, parent, title, register_list, row):
        """Create a group of register editors"""
        group_frame = ttk.LabelFrame(parent, text=title, padding=10)
        group_frame.grid(row=row, column=0, columnspan=3, sticky=tk.W+tk.E, padx=10, pady=5)
        
        for idx, reg_name in enumerate(register_list):
            if reg_name not in self.registers:
                continue
                
            reg_info = self.registers[reg_name]
            reg_frame = ttk.Frame(group_frame)
            reg_frame.grid(row=idx, column=0, sticky=tk.W+tk.E, pady=2)
            
            # Label
            label_text = f"{reg_name}: {reg_info['name']}"
            ttk.Label(reg_frame, text=label_text, width=35).grid(row=0, column=0, sticky=tk.W)
            
            # Value widget
            widget_frame = ttk.Frame(reg_frame)
            widget_frame.grid(row=0, column=1, padx=10)
            
            if reg_info['type'] == 'choice':
                var = tk.StringVar()
                combo = ttk.Combobox(widget_frame, textvariable=var, values=reg_info['values'], 
                                    width=30, state='readonly')
                combo.set(reg_info['default'])
                combo.pack(side=tk.LEFT)
                self.register_widgets[reg_name] = {
                    'var': var,
                    'type': 'choice',
                    'widget': combo,
                    'values': reg_info['values']
                }
                
            elif reg_info['type'] == 'number':
                var = tk.StringVar(value=reg_info['default'])
                entry = ttk.Entry(widget_frame, textvariable=var, width=20)
                entry.pack(side=tk.LEFT)
                self.register_widgets[reg_name] = {'var': var, 'type': 'number', 
                                                   'min': reg_info['min'], 'max': reg_info['max']}
                
            elif reg_info['type'] == 'text':
                var = tk.StringVar(value=reg_info['default'])
                entry = ttk.Entry(widget_frame, textvariable=var, width=30)
                entry.pack(side=tk.LEFT)
                self.register_widgets[reg_name] = {'var': var, 'type': 'text'}
                
            elif reg_info['type'] == 'readonly':
                var = tk.StringVar(value="N/A")
                entry = ttk.Entry(widget_frame, textvariable=var, width=20, state='readonly')
                entry.pack(side=tk.LEFT)
                self.register_widgets[reg_name] = {'var': var, 'type': 'readonly'}
            
            # Action buttons
            btn_frame = ttk.Frame(reg_frame)
            btn_frame.grid(row=0, column=2, padx=5)
            
            ttk.Button(btn_frame, text="Read", width=8,
                      command=lambda r=reg_name: self._read_register(r)).pack(side=tk.LEFT, padx=2)
            if reg_info['type'] != 'readonly':
                ttk.Button(btn_frame, text="Write", width=8,
                          command=lambda r=reg_name: self._write_register(r)).pack(side=tk.LEFT, padx=2)
            
            # Description tooltip
            tooltip_text = reg_info['description']
            help_label = tk.Label(reg_frame, text="?", cursor="hand2", fg="blue")
            help_label.grid(row=0, column=3, padx=5)
            help_label.bind("<Button-1>", lambda e, t=tooltip_text: messagebox.showinfo("Description", t))
        
    def _create_console_tab(self):
        """Create command console tab"""
        frame = self.console_frame
        
        # Console output
        console_frame = ttk.LabelFrame(frame, text="Command Console", padding=10)
        console_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.console_text = scrolledtext.ScrolledText(console_frame, height=20, width=80)
        self.console_text.pack(fill=tk.BOTH, expand=True)
        
        # Command input
        input_frame = ttk.Frame(frame)
        input_frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(input_frame, text="Command:").pack(side=tk.LEFT, padx=5)
        self.command_entry = ttk.Entry(input_frame, width=50)
        self.command_entry.pack(side=tk.LEFT, padx=5)
        self.command_entry.bind('<Return>', lambda e: self._send_console_command())
        
        ttk.Button(input_frame, text="Send", command=self._send_console_command).pack(side=tk.LEFT, padx=5)
        ttk.Button(input_frame, text="Clear", command=lambda: self.console_text.delete(1.0, tk.END)).pack(side=tk.LEFT, padx=5)
        
    def _refresh_ports(self):
        """Refresh available serial ports"""
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.port_combo['values'] = ports
        if ports:
            self.port_combo.set(ports[0])
    
    def _connect(self):
        """Connect to serial port"""
        try:
            port = self.port_var.get()
            baud = int(self.baud_var.get())
            timeout = float(self.timeout_var.get())
            
            if not port:
                messagebox.showerror("Error", "Please select a serial port")
                return
            
            self.serial_connection = serial.Serial(port, baud, timeout=timeout)
            time.sleep(0.1)  # Allow connection to settle
            
            self.connect_button.config(state=tk.DISABLED)
            self.disconnect_button.config(state=tk.NORMAL)
            self.enter_at_button.config(state=tk.NORMAL)
            self.exit_at_button.config(state=tk.DISABLED)
            self.status_label.config(text=f"Connected to {port} @ {baud} baud", foreground="green")
            
            self._log_console(f"Connected to {port} at {baud} baud")
            
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect: {str(e)}")
            self._log_console(f"Connection failed: {str(e)}")
    
    def _disconnect(self):
        """Disconnect from serial port"""
        if self.serial_connection and self.serial_connection.is_open:
            if self.at_mode:
                self._exit_at_mode(silent=True)
            self.serial_connection.close()
        
        self.serial_connection = None
        self.at_mode = False
        self.connect_button.config(state=tk.NORMAL)
        self.disconnect_button.config(state=tk.DISABLED)
        self.enter_at_button.config(state=tk.DISABLED)
        self.exit_at_button.config(state=tk.DISABLED)
        self.status_label.config(text="Disconnected", foreground="red")
        self._log_console("Disconnected")
    
    def _enter_at_mode(self):
        """Enter AT command configuration mode from data mode"""
        if not self.serial_connection or not self.serial_connection.is_open:
            messagebox.showwarning("Not Connected", "Please connect to a device first")
            return
        
        try:
            self._log_console("Entering AT command mode...")
            self.status_label.config(text="Entering AT mode...", foreground="orange")
            
            # Clear any pending data
            if self.serial_connection.in_waiting > 0:
                self.serial_connection.read(self.serial_connection.in_waiting)
            
            # Step 1: Idle for 1 second
            time.sleep(1.0)
            
            # Step 2: Send "+++"
            self.serial_connection.write("+++".encode())
            self._log_console("> +++")
            
            # Step 3: Idle for another 1 second
            time.sleep(1.0)
            
            # Step 4: Read response (should be "Welcome To Use T900 OK")
            response = ""
            start_time = time.time()
            while time.time() - start_time < 2.0:  # Wait up to 2 seconds for response
                if self.serial_connection.in_waiting > 0:
                    response += self.serial_connection.read(self.serial_connection.in_waiting).decode('utf-8', errors='ignore')
                    if "OK" in response.upper() or "Welcome" in response:
                        break
                time.sleep(0.1)
            
            # Read any remaining data
            if self.serial_connection.in_waiting > 0:
                response += self.serial_connection.read(self.serial_connection.in_waiting).decode('utf-8', errors='ignore')
            
            response = response.strip()
            if response:
                self._log_console(f"< {response}")
            
            # Check if we successfully entered AT mode
            if "OK" in response.upper() or "Welcome" in response:
                self.at_mode = True
                self.status_label.config(text=f"Connected - AT Mode Active", foreground="green")
                self.enter_at_button.config(state=tk.DISABLED)
                self.exit_at_button.config(state=tk.NORMAL)
                self._log_console("✓ Successfully entered AT command mode")
                messagebox.showinfo("Success", "Entered AT command configuration mode")
            else:
                self.at_mode = False
                self.status_label.config(text=f"Connected - AT Mode: Unknown", foreground="orange")
                self.enter_at_button.config(state=tk.NORMAL)
                self.exit_at_button.config(state=tk.DISABLED)
                self._log_console("⚠ AT mode entry response unclear. You may need to try again.")
                messagebox.showwarning("Uncertain", "AT mode entry response unclear. Device may already be in AT mode or may need retry.")
                
        except Exception as e:
            error_msg = f"Error entering AT mode: {str(e)}"
            self._log_console(f"ERROR: {error_msg}")
            messagebox.showerror("Error", error_msg)
            self.at_mode = False
            self.enter_at_button.config(state=tk.NORMAL)
            self.exit_at_button.config(state=tk.DISABLED)
    
    def _exit_at_mode(self, silent: bool = False):
        """Exit AT command configuration mode and enter data mode using ATA command"""
        if not self.serial_connection or not self.serial_connection.is_open:
            if not silent:
                messagebox.showwarning("Not Connected", "Please connect to a device first")
            return False
        
        if not self.at_mode:
            if not silent:
                messagebox.showinfo("Info", "Device is not in AT command mode")
            return False
        
        try:
            self._log_console("Exiting AT command mode...")
            self.status_label.config(text="Exiting AT mode...", foreground="orange")
            
            # Send ATA command to exit AT mode
            response = self._send_command("ATA", append_cr=True, suppress_ui_errors=silent)
            
            if response:
                # Check for success indicators
                if "OK" in response.upper():
                    self.at_mode = False
                    self.status_label.config(text=f"Connected - Data Mode", foreground="green")
                    self.enter_at_button.config(state=tk.NORMAL)
                    self.exit_at_button.config(state=tk.DISABLED)
                    self._log_console("✓ Successfully exited AT command mode (entered data mode)")
                    if not silent:
                        messagebox.showinfo("Success", "Exited AT command mode and entered data mode")
                else:
                    # Even if no OK response, assume it worked if we got a response
                    self.at_mode = False
                    self.status_label.config(text=f"Connected - Data Mode", foreground="green")
                    self.enter_at_button.config(state=tk.NORMAL)
                    self.exit_at_button.config(state=tk.DISABLED)
                    self._log_console("✓ Exited AT command mode (entered data mode)")
                    if not silent:
                        messagebox.showinfo("Success", "Exited AT command mode and entered data mode")
            else:
                # No response, but assume it worked
                self.at_mode = False
                self.status_label.config(text=f"Connected - Data Mode", foreground="green")
                self.enter_at_button.config(state=tk.NORMAL)
                self.exit_at_button.config(state=tk.DISABLED)
                self._log_console("✓ Exited AT command mode (entered data mode)")
                if not silent:
                    messagebox.showinfo("Success", "Exited AT command mode and entered data mode")
                
        except Exception as e:
            error_msg = f"Error exiting AT mode: {str(e)}"
            self._log_console(f"ERROR: {error_msg}")
            if not silent:
                messagebox.showerror("Error", error_msg)
            return False
        
        return True
    
    def _send_command(self, command: str, append_cr=True, suppress_ui_errors: bool = False) -> Optional[str]:
        """Send AT command and return response"""
        if not self.serial_connection or not self.serial_connection.is_open:
            messagebox.showwarning("Not Connected", "Please connect to a device first")
            return None
        
        # Warn if not in AT mode (but allow command to proceed)
        if not self.at_mode and not command.startswith("+++"):
            self._log_console("⚠ Warning: May not be in AT mode. Consider entering AT mode first.")
        
        try:
            # Send command
            cmd = command + "\r\n" if append_cr else command
            self.serial_connection.write(cmd.encode())
            self._log_console(f"> {command}")
            
            # Read response
            time.sleep(0.1)
            response = ""
            while self.serial_connection.in_waiting > 0:
                response += self.serial_connection.read(self.serial_connection.in_waiting).decode('utf-8', errors='ignore')
                time.sleep(0.1)
            
            response = response.strip()
            if response:
                self._log_console(f"< {response}")
                return response
            return None
            
        except Exception as e:
            error_msg = f"Error sending command: {str(e)}"
            self._log_console(f"ERROR: {error_msg}")
            if not suppress_ui_errors:
                messagebox.showerror("Error", error_msg)
            return None
    
    def _send_console_command(self):
        """Send command from console input"""
        command = self.command_entry.get().strip()
        if command:
            self._send_command(command)
            self.command_entry.delete(0, tk.END)
    
    def _log_console(self, message: str):
        """Log message to console"""
        self.console_text.insert(tk.END, f"{message}\n")
        self.console_text.see(tk.END)
    
    def _log_info(self, message: str):
        """Log message to info tab"""
        self.info_text.insert(tk.END, f"{message}\n")
        self.info_text.see(tk.END)
    
    def _display_all_parameters(self):
        """Display all parameters using AT&V"""
        response = self._send_command("AT&V")
        if response:
            self._log_info("=== Current Parameters ===\n")
            self._log_info(response)
            self._log_info("\n=== End of Parameters ===")
    
    def _extract_register_value(self, response: str) -> Optional[str]:
        """Extract register value from ATS response"""
        if not response:
            return None
        lines = [line.strip() for line in response.splitlines() if line.strip()]
        for line in lines:
            if '=' in line:
                return line.split('=', 1)[1].strip()
        return lines[0] if lines else None
    
    def _apply_register_value(self, reg_name: str, value: str):
        """Set the GUI widget to the parsed register value"""
        widget_info = self.register_widgets.get(reg_name)
        if not widget_info:
            return
        
        display_value = value
        if widget_info['type'] == 'choice':
            for option in widget_info.get('values', []):
                code = option.split(' - ')[0].strip()
                if code == value.strip():
                    display_value = option
                    break
        widget_info['var'].set(display_value)
    
    def _read_register(self, reg_name: str):
        """Read a single register"""
        command = f"ATS{reg_name[1:]}?"
        response = self._send_command(command)
        if response:
            value = self._extract_register_value(response)
            if value is not None:
                self._apply_register_value(reg_name, value)
                self._log_info(f"{reg_name} = {value}")
    
    def _write_register(self, reg_name: str):
        """Write a single register"""
        if reg_name not in self.register_widgets:
            return
        
        widget_info = self.register_widgets[reg_name]
        value = widget_info['var'].get()
        
        # Extract numeric value from choice if needed
        if widget_info['type'] == 'choice':
            value = value.split(' - ')[0]
        
        # Validate number
        if widget_info['type'] == 'number':
            try:
                num_value = int(value)
                if num_value < widget_info['min'] or num_value > widget_info['max']:
                    messagebox.showerror("Invalid Value", 
                                       f"Value must be between {widget_info['min']} and {widget_info['max']}")
                    return
            except ValueError:
                messagebox.showerror("Invalid Value", "Value must be a number")
                return
        
        command = f"ATS{reg_name[1:]}={value}"
        response = self._send_command(command)
        if response:
            self._log_info(f"Written {reg_name} = {value}")
            if "OK" in response.upper():
                messagebox.showinfo("Success", f"Register {reg_name} written successfully")
    
    def _read_all_registers(self):
        """Read all readable registers"""
        self._log_info("=== Reading All Registers ===\n")
        for reg_name in self.register_widgets:
            self._read_register(reg_name)
            time.sleep(0.1)
        self._log_info("\n=== Finished Reading ===")
    
    def _write_all_registers(self):
        """Write all registers"""
        if messagebox.askyesno("Confirm", "Write all registers to device?"):
            self._log_info("=== Writing All Registers ===\n")
            for reg_name in self.register_widgets:
                if self.registers[reg_name]['type'] != 'readonly':
                    self._write_register(reg_name)
                    time.sleep(0.1)
            self._log_info("\n=== Finished Writing ===")
            messagebox.showinfo("Complete", "All registers written. Don't forget to save with AT&W!")
    
    def _save_configuration(self):
        """Save configuration using AT&W"""
        if messagebox.askyesno("Confirm", "Save current configuration to device?"):
            response = self._send_command("AT&W")
            if response:
                if "OK" in response.upper():
                    messagebox.showinfo("Success", "Configuration saved successfully")
                    self._log_info("Configuration saved to device")
                else:
                    messagebox.showerror("Error", "Failed to save configuration")
    
    def _show_factory_defaults(self):
        """Show factory defaults dialog"""
        dialog = tk.Toplevel(self.root)
        dialog.title("Factory Defaults")
        dialog.geometry("400x350")
        
        ttk.Label(dialog, text="Select factory default configuration:").pack(pady=10)
        
        options = [
            "4: Mesh with center master",
            "5: Mesh with center slave",
            "7: Point-to-multipoint master",
            "8: Point-to-multipoint slave",
            "9: Point-to-multipoint repeater",
            "10: Point-to-point master",
            "11: Point-to-point slave",
            "12: Point-to-point repeater"
        ]
        
        selected = tk.StringVar()
        for option in options:
            ttk.Radiobutton(dialog, text=option, variable=selected, value=option.split(':')[0]).pack(anchor=tk.W, padx=20)
        
        def apply_defaults():
            mode_num = selected.get()
            if mode_num:
                if messagebox.askyesno("Confirm", f"Load factory defaults for mode {mode_num}?"):
                    command = f"AT&F{mode_num}"
                    response = self._send_command(command)
                    if response:
                        if "OK" in response.upper():
                            messagebox.showinfo("Success", "Factory defaults loaded. Don't forget to save with AT&W!")
                            dialog.destroy()
                        else:
                            messagebox.showerror("Error", "Failed to load factory defaults")
        
        ttk.Button(dialog, text="Apply", command=apply_defaults).pack(pady=10)
        ttk.Button(dialog, text="Cancel", command=dialog.destroy).pack()


def main():
    root = tk.Tk()
    app = T900ConfigGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()

