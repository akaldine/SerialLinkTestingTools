"""
Sweep Test GUI for T900 Data Rate Testing
Provides interface for configuring and running parameter sweep tests
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
from t900_sweep_test import SweepTestRunner, SweepTestConfig


class SweepTestGUI:
    """GUI for sweep test configuration and execution"""
    
    def __init__(self, parent, main_gui):
        self.parent = parent
        self.main_gui = main_gui
        self.runner = SweepTestRunner(main_gui)
        self.config = self.runner.config
        
        self.window = tk.Toplevel(parent)
        self.window.title("Sweep Test Configuration")
        self.window.geometry("700x600")
        
        self._create_widgets()
        
    def _create_widgets(self):
        """Create GUI widgets"""
        # Main frame
        main_frame = ttk.Frame(self.window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Vary Mode Selection
        mode_frame = ttk.LabelFrame(main_frame, text="Variable Mode", padding=10)
        mode_frame.pack(fill=tk.X, pady=5)
        
        self.vary_mode_var = tk.StringVar(value="packet_size")
        ttk.Radiobutton(mode_frame, text="Vary Packet Size (keep write frequency stable)", 
                       variable=self.vary_mode_var, value="packet_size").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Vary Write Frequency (keep packet size stable)", 
                       variable=self.vary_mode_var, value="write_freq").pack(anchor=tk.W)
        ttk.Radiobutton(mode_frame, text="Vary Both Packet Size and Write Frequency", 
                       variable=self.vary_mode_var, value="both").pack(anchor=tk.W)
        
        # Packet Size Range
        size_frame = ttk.LabelFrame(main_frame, text="Packet Size Range (bytes)", padding=10)
        size_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(size_frame, text="Min:").grid(row=0, column=0, padx=5, pady=2)
        self.size_min_var = tk.StringVar(value="100")
        ttk.Entry(size_frame, textvariable=self.size_min_var, width=15).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(size_frame, text="Max:").grid(row=0, column=2, padx=5, pady=2)
        self.size_max_var = tk.StringVar(value="1000")
        ttk.Entry(size_frame, textvariable=self.size_max_var, width=15).grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(size_frame, text="Step:").grid(row=0, column=4, padx=5, pady=2)
        self.size_step_var = tk.StringVar(value="100")
        ttk.Entry(size_frame, textvariable=self.size_step_var, width=15).grid(row=0, column=5, padx=5, pady=2)
        
        ttk.Label(size_frame, text="(Or comma-separated list: 100,200,500,1000)").grid(row=1, column=0, columnspan=6, pady=5)
        self.size_list_var = tk.StringVar(value="")
        ttk.Entry(size_frame, textvariable=self.size_list_var, width=50).grid(row=2, column=0, columnspan=6, pady=2)
        
        # Write Frequency Range
        freq_frame = ttk.LabelFrame(main_frame, text="Write Frequency Range (seconds)", padding=10)
        freq_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(freq_frame, text="Min:").grid(row=0, column=0, padx=5, pady=2)
        self.freq_min_var = tk.StringVar(value="0.01")
        ttk.Entry(freq_frame, textvariable=self.freq_min_var, width=15).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(freq_frame, text="Max:").grid(row=0, column=2, padx=5, pady=2)
        self.freq_max_var = tk.StringVar(value="0.1")
        ttk.Entry(freq_frame, textvariable=self.freq_max_var, width=15).grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(freq_frame, text="Step:").grid(row=0, column=4, padx=5, pady=2)
        self.freq_step_var = tk.StringVar(value="0.01")
        ttk.Entry(freq_frame, textvariable=self.freq_step_var, width=15).grid(row=0, column=5, padx=5, pady=2)
        
        ttk.Label(freq_frame, text="(Or comma-separated list: 0.01,0.05,0.1,0.2)").grid(row=1, column=0, columnspan=6, pady=5)
        self.freq_list_var = tk.StringVar(value="")
        ttk.Entry(freq_frame, textvariable=self.freq_list_var, width=50).grid(row=2, column=0, columnspan=6, pady=2)
        
        # Test Constants
        const_frame = ttk.LabelFrame(main_frame, text="Test Constants", padding=10)
        const_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(const_frame, text="Number of Packets:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.num_packets_var = tk.StringVar(value="100")
        ttk.Entry(const_frame, textvariable=self.num_packets_var, width=15).grid(row=0, column=1, padx=5, pady=2)
        
        ttk.Label(const_frame, text="Direction:").grid(row=0, column=2, padx=5, pady=2, sticky=tk.W)
        self.direction_var = tk.StringVar(value="Bidirectional")
        direction_combo = ttk.Combobox(const_frame, textvariable=self.direction_var,
                                      values=["Bidirectional", "Sender → Receiver", "Receiver → Sender"],
                                      width=20, state='readonly')
        direction_combo.grid(row=0, column=3, padx=5, pady=2)
        
        ttk.Label(const_frame, text="Repeats per Point:").grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)
        self.repeats_var = tk.StringVar(value="1")
        ttk.Entry(const_frame, textvariable=self.repeats_var, width=15).grid(row=1, column=1, padx=5, pady=2)
        
        # Output Directory
        output_frame = ttk.LabelFrame(main_frame, text="Output", padding=10)
        output_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(output_frame, text="Output Directory:").grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)
        self.output_dir_var = tk.StringVar(value=".")
        ttk.Entry(output_frame, textvariable=self.output_dir_var, width=40).grid(row=0, column=1, padx=5, pady=2)
        ttk.Button(output_frame, text="Browse", command=self._browse_output_dir).grid(row=0, column=2, padx=5, pady=2)
        
        # Progress
        progress_frame = ttk.LabelFrame(main_frame, text="Progress", padding=10)
        progress_frame.pack(fill=tk.X, pady=5)
        
        self.progress_var = tk.StringVar(value="Ready")
        ttk.Label(progress_frame, textvariable=self.progress_var).pack(anchor=tk.W)
        
        self.progress_bar = ttk.Progressbar(progress_frame, mode='determinate')
        self.progress_bar.pack(fill=tk.X, pady=5)
        
        # Control Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.start_button = ttk.Button(button_frame, text="Start Sweep Test", command=self._start_sweep)
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = ttk.Button(button_frame, text="Stop Test", command=self._stop_sweep, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.export_csv_button = ttk.Button(button_frame, text="Export CSV", command=self._export_csv, state=tk.DISABLED)
        self.export_csv_button.pack(side=tk.LEFT, padx=5)
        
        self.generate_html_button = ttk.Button(button_frame, text="Generate HTML Report", command=self._generate_html, state=tk.DISABLED)
        self.generate_html_button.pack(side=tk.LEFT, padx=5)
        
    def _browse_output_dir(self):
        """Browse for output directory"""
        directory = filedialog.askdirectory(initialdir=self.output_dir_var.get())
        if directory:
            self.output_dir_var.set(directory)
    
    def _parse_range(self, min_str, max_str, step_str, list_str, is_integer=False):
        """Parse range input (either min/max/step or list)
        
        Args:
            min_str: Minimum value string
            max_str: Maximum value string
            step_str: Step value string
            list_str: Comma-separated list string (takes priority if not empty)
            is_integer: If True, convert values to integers (for packet sizes)
        """
        # List takes priority if provided and not empty
        if list_str and list_str.strip():
            # Parse comma-separated list
            try:
                if is_integer:
                    values = [int(float(x.strip())) for x in list_str.split(',') if x.strip()]
                else:
                    values = [float(x.strip()) for x in list_str.split(',') if x.strip()]
                if values:  # Only return if we have at least one value
                    return values
                else:
                    # Empty list after parsing, fall through to min/max/step
                    pass
            except ValueError:
                # Invalid list format, fall through to min/max/step
                pass
        
        # Fall back to min/max/step if list is empty or invalid
        try:
            min_val = float(min_str)
            max_val = float(max_str)
            step_val = float(step_str)
            if is_integer:
                return (int(min_val), int(max_val), int(step_val))
            else:
                return (min_val, max_val, step_val)
        except ValueError:
            return None
    
    def _start_sweep(self):
        """Start sweep test"""
        # Validate inputs
        try:
            # Parse ranges (list takes priority if provided)
            size_range = self._parse_range(
                self.size_min_var.get(),
                self.size_max_var.get(),
                self.size_step_var.get(),
                self.size_list_var.get(),
                is_integer=True  # Packet sizes must be integers
            )
            if size_range is None:
                messagebox.showerror("Error", "Invalid packet size range")
                return
            
            freq_range = self._parse_range(
                self.freq_min_var.get(),
                self.freq_max_var.get(),
                self.freq_step_var.get(),
                self.freq_list_var.get(),
                is_integer=False  # Write frequencies are floats
            )
            if freq_range is None:
                messagebox.showerror("Error", "Invalid write frequency range")
                return
            
            # Validate constants
            num_packets = int(self.num_packets_var.get())
            if num_packets <= 0:
                messagebox.showerror("Error", "Number of packets must be > 0")
                return
            
            repeats = int(self.repeats_var.get())
            if repeats <= 0:
                messagebox.showerror("Error", "Repeats must be > 0")
                return
            
            # Check connections
            if not (self.main_gui.sender_connection and self.main_gui.sender_connection.is_open):
                messagebox.showerror("Error", "Sender not connected")
                return
            
            if not (self.main_gui.receiver_connection and self.main_gui.receiver_connection.is_open):
                messagebox.showerror("Error", "Receiver not connected")
                return
            
            # Configure
            self.config.vary_mode = self.vary_mode_var.get()
            self.config.packet_size_range = size_range
            self.config.write_freq_range = freq_range
            self.config.num_packets = num_packets
            self.config.direction = self.direction_var.get()
            self.config.repeats = repeats
            self.config.output_dir = self.output_dir_var.get()
            
            # Update UI
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.export_csv_button.config(state=tk.DISABLED)
            self.generate_html_button.config(state=tk.DISABLED)
            self.progress_bar['maximum'] = 100
            self.progress_bar['value'] = 0
            
            # Start test in thread
            self.test_thread = threading.Thread(target=self._run_sweep_thread, daemon=True)
            self.test_thread.start()
            
        except ValueError as e:
            messagebox.showerror("Error", f"Invalid input: {str(e)}")
    
    def _run_sweep_thread(self):
        """Run sweep test in background thread"""
        def progress_callback(current, total, message):
            self.window.after(0, lambda: self._update_progress(current, total, message))
        
        try:
            results = self.runner.run_sweep_test(progress_callback)
            
            self.window.after(0, lambda: self._sweep_complete(results))
        except Exception as e:
            self.window.after(0, lambda: messagebox.showerror("Error", f"Sweep test failed: {str(e)}"))
            self.window.after(0, lambda: self._sweep_complete([]))
    
    def _update_progress(self, current, total, message):
        """Update progress display"""
        if total > 0:
            progress = (current / total) * 100
            self.progress_bar['value'] = progress
        self.progress_var.set(f"{current}/{total}: {message}")
    
    def _sweep_complete(self, results):
        """Handle sweep test completion"""
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        
        if results:
            self.export_csv_button.config(state=tk.NORMAL)
            self.generate_html_button.config(state=tk.NORMAL)
            self.progress_var.set(f"Complete: {len(results)} test results")
            messagebox.showinfo("Success", f"Sweep test complete: {len(results)} results")
        else:
            self.progress_var.set("Test stopped or failed")
    
    def _stop_sweep(self):
        """Stop sweep test"""
        self.runner.is_running = False
        self.progress_var.set("Stopping...")
    
    def _export_csv(self):
        """Export results to CSV"""
        if not self.runner.results:
            messagebox.showwarning("Warning", "No results to export")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=self.config.output_dir
        )
        
        if filename:
            self.runner.export_csv(filename)
    
    def _generate_html(self):
        """Generate HTML report"""
        if not self.runner.results:
            messagebox.showwarning("Warning", "No results to generate report")
            return
        
        filename = filedialog.asksaveasfilename(
            defaultextension=".html",
            filetypes=[("HTML files", "*.html"), ("All files", "*.*")],
            initialdir=self.config.output_dir
        )
        
        if filename:
            self.runner.generate_html_report(filename)

