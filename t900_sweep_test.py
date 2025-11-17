"""
Sweep Test Module for T900 Data Rate Testing
Allows running multiple tests with varying parameters and generating CSV/HTML reports
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import json
import time
import threading
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import webbrowser
import os


class SweepTestConfig:
    """Configuration for sweep test parameters"""
    def __init__(self):
        self.packet_size_range = None  # (min, max, step) or list of values
        self.write_freq_range = None  # (min, max, step) or list of values
        self.vary_mode = "packet_size"  # "packet_size", "write_freq", "both"
        self.num_packets = 100
        self.direction = "Bidirectional"
        self.repeats = 1
        self.output_dir = ""


class SweepTestRunner:
    """Runs sweep tests and generates reports"""
    
    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.config = SweepTestConfig()
        self.results = []  # List of test results
        self.is_running = False
        self.current_test = 0
        self.total_tests = 0
        
    def generate_test_combinations(self) -> List[Tuple[int, float]]:
        """Generate all combinations of packet_size and write_freq to test"""
        combinations = []
        
        if self.config.vary_mode == "packet_size":
            # Vary packet size, keep write_freq stable
            if isinstance(self.config.packet_size_range, tuple):
                min_size, max_size, step = self.config.packet_size_range
                packet_sizes = list(range(int(min_size), int(max_size) + 1, int(step)))
            else:
                # List from comma-separated input (already integers from parsing)
                packet_sizes = [int(s) for s in self.config.packet_size_range]
            
            # Use first write_freq if range, or single value
            if isinstance(self.config.write_freq_range, tuple):
                write_freq = float(self.config.write_freq_range[0])
            else:
                # List from comma-separated input - use first value
                write_freq = float(self.config.write_freq_range[0])
            
            for size in packet_sizes:
                combinations.append((size, write_freq))
                
        elif self.config.vary_mode == "write_freq":
            # Vary write_freq, keep packet_size stable
            if isinstance(self.config.write_freq_range, tuple):
                min_freq, max_freq, step = self.config.write_freq_range
                # Generate frequency values
                write_freqs = []
                current = min_freq
                while current <= max_freq:
                    write_freqs.append(current)
                    current += step
            else:
                write_freqs = self.config.write_freq_range
            
            # Use first packet_size if range, or single value
            if isinstance(self.config.packet_size_range, tuple):
                packet_size = int(self.config.packet_size_range[0])
            else:
                # List from comma-separated input - use first value
                packet_size = int(self.config.packet_size_range[0])
            
            for freq in write_freqs:
                combinations.append((packet_size, freq))
                
        elif self.config.vary_mode == "both":
            # Vary both parameters
            if isinstance(self.config.packet_size_range, tuple):
                min_size, max_size, step = self.config.packet_size_range
                packet_sizes = list(range(int(min_size), int(max_size) + 1, int(step)))
            else:
                # List from comma-separated input (already integers from parsing)
                packet_sizes = [int(s) for s in self.config.packet_size_range]
            
            if isinstance(self.config.write_freq_range, tuple):
                min_freq, max_freq, step = self.config.write_freq_range
                write_freqs = []
                current = min_freq
                while current <= max_freq:
                    write_freqs.append(current)
                    current += step
            else:
                write_freqs = self.config.write_freq_range
            
            for size in packet_sizes:
                for freq in write_freqs:
                    combinations.append((size, freq))
        
        return combinations
    
    def run_sweep_test(self, progress_callback=None):
        """Run all test combinations"""
        self.is_running = True
        self.results = []
        
        combinations = self.generate_test_combinations()
        self.total_tests = len(combinations) * self.config.repeats
        self.current_test = 0
        
        try:
            for packet_size, write_freq in combinations:
                if not self.is_running:
                    break
                
                # Run test multiple times
                for repeat in range(self.config.repeats):
                    if not self.is_running:
                        break
                    
                    self.current_test += 1
                    if progress_callback:
                        progress_callback(self.current_test, self.total_tests, 
                                         f"Testing: size={packet_size}, freq={write_freq:.6f}, repeat={repeat+1}")
                    
                    # Configure main GUI for this test
                    result = self._run_single_test(packet_size, write_freq)
                    
                    if result:
                        self.results.append(result)
                    
                    time.sleep(0.5)  # Small delay between tests
            
        except Exception as e:
            messagebox.showerror("Error", f"Sweep test error: {str(e)}")
        finally:
            self.is_running = False
            
        return self.results
    
    def _run_single_test(self, packet_size: int, write_freq: float) -> Optional[Dict]:
        """Run a single test with given parameters"""
        try:
            # Set parameters in main GUI
            self.main_gui.input_mode_var.set("Packet-Count")
            self.main_gui.packet_count_size_var.set(str(packet_size))
            self.main_gui.packet_count_freq_var.set(str(write_freq))
            self.main_gui.num_packets_var.set(str(self.config.num_packets))
            self.main_gui.direction_var.set(self.config.direction)
            
            # Wait for GUI to update
            self.main_gui.root.update()
            time.sleep(0.1)
            
            # Clear buffers before starting test (additional safety for sweep tests)
            self.main_gui._clear_serial_buffers()
            time.sleep(0.1)  # Small delay after clearing buffers
            
            # Start test
            self.main_gui._start_test()
            
            # Wait for test to complete
            max_wait = 300  # 5 minutes max per test
            wait_time = 0
            while self.main_gui.test_running and wait_time < max_wait:
                time.sleep(0.1)
                wait_time += 0.1
            
            if wait_time >= max_wait:
                self.main_gui._stop_test()
                return None
            
            # Wait for test to fully stop and final calculations to complete
            # The monitor thread calls _stop_test() via root.after(), so we need to process
            # the event queue to ensure _stop_test() executes
            max_stop_wait = 5  # 5 seconds max
            stop_wait_time = 0
            while self.main_gui.test_running and stop_wait_time < max_stop_wait:
                # Process Tkinter event queue to ensure root.after() callbacks execute
                self.main_gui.root.update_idletasks()
                time.sleep(0.1)
                stop_wait_time += 0.1
            
            # Process event queue to ensure _stop_test() executes (it's queued via root.after())
            # Process multiple times to ensure all queued callbacks run
            for _ in range(10):
                self.main_gui.root.update_idletasks()
                time.sleep(0.05)
            
            # Wait for _stop_test() to complete calculations
            # Check that elapsed_time has been calculated (indicates _stop_test() has run)
            calculation_wait = 0
            max_calc_wait = 3  # 3 seconds max
            while calculation_wait < max_calc_wait:
                stats_temp = self.main_gui.stats
                # Check if elapsed_time is set and > 0 (indicates _stop_test() has completed calculations)
                elapsed = stats_temp.get('elapsed_time')
                if elapsed is not None and elapsed > 0:
                    # Also check that rates are calculated
                    if (stats_temp.get('data_rate_total_bps') is not None or 
                        stats_temp.get('data_rate_total_bps_combined') is not None):
                        break
                # Process event queue while waiting
                self.main_gui.root.update_idletasks()
                time.sleep(0.1)
                calculation_wait += 0.1
            
            # Final event queue processing to ensure everything is complete
            self.main_gui.root.update_idletasks()
            time.sleep(0.1)
            
            # Extract results - use pre-calculated values from stats as single source of truth
            stats = self.main_gui.stats
            direction = self.main_gui.direction_var.get()
            
            result = {
                'packet_size': packet_size,
                'write_freq': write_freq,
                'num_packets': self.config.num_packets,
                'direction': direction,
                'timestamp': time.time()
            }
            
            if direction == "Bidirectional":
                # Combined results
                total_sent = stats['packets_sent'] + stats['packets_sent_2']
                total_received = stats['packets_received'] + stats['packets_received_2']
                total_corrupt = stats['packets_corrupt'] + stats['packets_corrupt_2']
                
                # Use pre-calculated rates from _stop_test() as single source of truth
                if stats['data_rate_total_bps_combined'] is not None:
                    result['speed_total_bps'] = stats['data_rate_total_bps_combined']
                else:
                    result['speed_total_bps'] = 0
                
                if stats['data_rate_valid_bps_combined'] is not None:
                    result['speed_valid_bps'] = stats['data_rate_valid_bps_combined']
                else:
                    result['speed_valid_bps'] = 0
                
                if stats['send_rate_bps_combined'] is not None:
                    result['send_rate_bps'] = stats['send_rate_bps_combined']
                else:
                    result['send_rate_bps'] = 0
                
                # Latency
                all_latencies = list(stats['latency_samples']) + list(stats['latency_samples_2'])
                if all_latencies:
                    result['latency_avg_ms'] = (sum(all_latencies) / len(all_latencies)) * 1000
                    result['latency_min_ms'] = min(all_latencies) * 1000
                    result['latency_max_ms'] = max(all_latencies) * 1000
                else:
                    result['latency_avg_ms'] = 0
                    result['latency_min_ms'] = 0
                    result['latency_max_ms'] = 0
                
                # Packet loss
                if total_sent > 0:
                    result['packet_loss_percent'] = ((total_sent - total_received) / total_sent) * 100
                else:
                    result['packet_loss_percent'] = 0
                
                # Corruption
                if total_received > 0:
                    result['corruption_percent'] = (total_corrupt / total_received) * 100
                else:
                    result['corruption_percent'] = 0
            else:
                # Unidirectional
                total_sent = stats['packets_sent']
                total_received = stats['packets_received']
                total_corrupt = stats['packets_corrupt']
                
                # Use pre-calculated rates from _stop_test() as single source of truth
                if stats['data_rate_total_bps'] is not None:
                    result['speed_total_bps'] = stats['data_rate_total_bps']
                else:
                    result['speed_total_bps'] = 0
                
                if stats['data_rate_valid_bps'] is not None:
                    result['speed_valid_bps'] = stats['data_rate_valid_bps']
                else:
                    result['speed_valid_bps'] = 0
                
                if stats['send_rate_bps'] is not None:
                    result['send_rate_bps'] = stats['send_rate_bps']
                else:
                    result['send_rate_bps'] = 0
                
                # Latency
                if stats['latency_samples']:
                    latencies = list(stats['latency_samples'])
                    result['latency_avg_ms'] = (sum(latencies) / len(latencies)) * 1000
                    result['latency_min_ms'] = min(latencies) * 1000
                    result['latency_max_ms'] = max(latencies) * 1000
                else:
                    result['latency_avg_ms'] = 0
                    result['latency_min_ms'] = 0
                    result['latency_max_ms'] = 0
                
                # Packet loss
                if total_sent > 0:
                    result['packet_loss_percent'] = ((total_sent - total_received) / total_sent) * 100
                else:
                    result['packet_loss_percent'] = 0
                
                # Corruption
                if total_received > 0:
                    result['corruption_percent'] = (total_corrupt / total_received) * 100
                else:
                    result['corruption_percent'] = 0
            
            # Use elapsed_time from stats (calculated in _stop_test()) as single source of truth
            # Ensure we use the stored value properly
            elapsed_time_val = stats.get('elapsed_time')
            if elapsed_time_val is not None and elapsed_time_val > 0:
                result['elapsed_time'] = elapsed_time_val
            else:
                # If elapsed_time is not set or is 0, try to calculate from start/end times as fallback
                if stats.get('start_time') and stats.get('end_time'):
                    result['elapsed_time'] = stats['end_time'] - stats['start_time']
                else:
                    result['elapsed_time'] = 0
            
            result['packets_sent'] = total_sent
            result['packets_received'] = total_received
            result['packets_corrupt'] = total_corrupt
            
            return result
            
        except Exception as e:
            print(f"Error in single test: {str(e)}")
            return None
    
    def export_csv(self, filename: str):
        """Export results to CSV"""
        if not self.results:
            messagebox.showwarning("Warning", "No results to export")
            return
        
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=[
                    'packet_size', 'write_freq', 'num_packets', 'direction',
                    'speed_total_bps', 'speed_valid_bps', 'send_rate_bps',
                    'latency_avg_ms', 'latency_min_ms', 'latency_max_ms',
                    'packet_loss_percent', 'corruption_percent',
                    'elapsed_time', 'packets_sent', 'packets_received', 'packets_corrupt', 'timestamp'
                ])
                writer.writeheader()
                writer.writerows(self.results)
            
            messagebox.showinfo("Success", f"CSV exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to export CSV: {str(e)}")
    
    def generate_html_report(self, filename: str):
        """Generate HTML report with interactive graphs"""
        if not self.results:
            messagebox.showwarning("Warning", "No results to generate report")
            return
        
        try:
            # Group data for plotting
            data = self._prepare_plot_data()
            
            html = self._generate_html_content(data)
            
            with open(filename, 'w') as f:
                f.write(html)
            
            messagebox.showinfo("Success", f"HTML report generated: {filename}")
            # Open in browser
            webbrowser.open(f'file://{os.path.abspath(filename)}')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to generate HTML: {str(e)}")
    
    def _prepare_plot_data(self) -> Dict:
        """Prepare data for plotting"""
        data = defaultdict(list)
        
        # For "both" mode, we need to group by write_freq
        if self.config.vary_mode == "both":
            # Group results by write_freq
            by_freq = defaultdict(list)
            for result in self.results:
                by_freq[result['write_freq']].append(result)
            
            data['x_label'] = "Packet Size (bytes)"
            data['series'] = []
            for freq, results in sorted(by_freq.items()):
                series_data = {
                    'write_freq': freq,
                    'x': [r['packet_size'] for r in results],
                    'speed_total': [r['speed_total_bps'] / 1000 for r in results],
                    'speed_valid': [r['speed_valid_bps'] / 1000 for r in results],
                    'send_rate': [r['send_rate_bps'] / 1000 for r in results],
                    'latency_avg': [r['latency_avg_ms'] for r in results],
                    'latency_min': [r['latency_min_ms'] for r in results],
                    'latency_max': [r['latency_max_ms'] for r in results],
                    'packet_loss': [r['packet_loss_percent'] for r in results],
                    'corruption': [r['corruption_percent'] for r in results]
                }
                data['series'].append(series_data)
        else:
            # Single series
            for result in self.results:
                # X-axis depends on vary_mode
                if self.config.vary_mode == "packet_size":
                    x = result['packet_size']
                    x_label = "Packet Size (bytes)"
                elif self.config.vary_mode == "write_freq":
                    x = result['write_freq']
                    x_label = "Write Frequency (s)"
                
                data['x'].append(x)
                data['x_label'] = x_label
                data['speed_total'].append(result['speed_total_bps'] / 1000)  # Convert to kbps
                data['speed_valid'].append(result['speed_valid_bps'] / 1000)
                data['send_rate'].append(result['send_rate_bps'] / 1000)
                data['latency_avg'].append(result['latency_avg_ms'])
                data['latency_min'].append(result['latency_min_ms'])
                data['latency_max'].append(result['latency_max_ms'])
                data['packet_loss'].append(result['packet_loss_percent'])
                data['corruption'].append(result['corruption_percent'])
        
        return data
    
    def _generate_html_content(self, data: Dict) -> str:
        """Generate HTML with Plotly graphs"""
        html = f"""<!DOCTYPE html>
<html>
<head>
    <title>T900 Sweep Test Results</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .graph-container {{
            margin: 30px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 4px;
        }}
        .graph-title {{
            font-size: 18px;
            font-weight: bold;
            margin-bottom: 10px;
            color: #555;
        }}
        .info {{
            background: #e3f2fd;
            padding: 15px;
            border-radius: 4px;
            margin-bottom: 20px;
        }}
        .info p {{
            margin: 5px 0;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>T900 Sweep Test Results</h1>
        <div class="info">
            <p><strong>Test Configuration:</strong></p>
            <p>Vary Mode: {self.config.vary_mode}</p>
            <p>Number of Packets: {self.config.num_packets}</p>
            <p>Direction: {self.config.direction}</p>
            <p>Repeats per Point: {self.config.repeats}</p>
            <p>Total Tests: {len(self.results)}</p>
        </div>
"""
        
        # Speed Graph
        html += self._generate_speed_graph(data)
        
        # Latency Graph
        html += self._generate_latency_graph(data)
        
        # Packet Loss Graph
        html += self._generate_packet_loss_graph(data)
        
        # Corruption Graph
        html += self._generate_corruption_graph(data)
        
        html += """
    </div>
</body>
</html>
"""
        return html
    
    def _generate_speed_graph(self, data: Dict) -> str:
        """Generate speed graph"""
        if self.config.vary_mode == "both":
            # Multiple series
            traces = []
            colors = ['green', 'blue', 'red', 'orange', 'purple', 'brown', 'pink', 'gray']
            for i, series in enumerate(data['series']):
                color = colors[i % len(colors)]
                freq_label = f"freq={series['write_freq']:.6f}s"
                traces.append({
                    'x': series['x'],
                    'y': series['speed_valid'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': f'Speed Valid - {freq_label}',
                    'marker': {'color': color}
                })
        else:
            # Single series
            traces = [
                {
                    'x': data['x'],
                    'y': data['speed_valid'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': 'Speed Valid (kbps)',
                    'marker': {'color': 'green'}
                }
            ]
        
        graph_data = json.dumps(traces)
        
        return f"""
        <div class="graph-container">
            <div class="graph-title">Data Rate (kbps)</div>
            <div id="speed-graph"></div>
            <script>
                var data = {graph_data};
                var layout = {{
                    title: 'Data Rate vs {data["x_label"]}',
                    xaxis: {{ title: '{data["x_label"]}' }},
                    yaxis: {{ title: 'Data Rate (kbps)' }},
                    hovermode: 'closest'
                }};
                Plotly.newPlot('speed-graph', data, layout);
            </script>
        </div>
"""
    
    def _generate_latency_graph(self, data: Dict) -> str:
        """Generate latency graph"""
        if self.config.vary_mode == "both":
            traces = []
            colors = ['blue', 'red', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']
            for i, series in enumerate(data['series']):
                color = colors[i % len(colors)]
                freq_label = f"freq={series['write_freq']:.6f}s"
                traces.append({
                    'x': series['x'],
                    'y': series['latency_avg'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': f'Avg Latency - {freq_label}',
                    'marker': {'color': color}
                })
        else:
            traces = [
                {
                    'x': data['x'],
                    'y': data['latency_avg'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': 'Avg Latency (ms)',
                    'marker': {'color': 'blue'}
                }
            ]
        
        graph_data = json.dumps(traces)
        
        return f"""
        <div class="graph-container">
            <div class="graph-title">Latency (ms)</div>
            <div id="latency-graph"></div>
            <script>
                var data = {graph_data};
                var layout = {{
                    title: 'Latency vs {data["x_label"]}',
                    xaxis: {{ title: '{data["x_label"]}' }},
                    yaxis: {{ title: 'Latency (ms)' }},
                    hovermode: 'closest'
                }};
                Plotly.newPlot('latency-graph', data, layout);
            </script>
        </div>
"""
    
    def _generate_packet_loss_graph(self, data: Dict) -> str:
        """Generate packet loss graph"""
        if self.config.vary_mode == "both":
            traces = []
            colors = ['red', 'blue', 'green', 'orange', 'purple', 'brown', 'pink', 'gray']
            for i, series in enumerate(data['series']):
                color = colors[i % len(colors)]
                freq_label = f"freq={series['write_freq']:.6f}s"
                traces.append({
                    'x': series['x'],
                    'y': series['packet_loss'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': f'Packet Loss - {freq_label}',
                    'marker': {'color': color}
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['packet_loss'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Packet Loss (%)',
                'marker': {'color': 'red'}
            }]
        
        graph_data = json.dumps(traces)
        
        return f"""
        <div class="graph-container">
            <div class="graph-title">Packet Loss (%)</div>
            <div id="packet-loss-graph"></div>
            <script>
                var data = {graph_data};
                var layout = {{
                    title: 'Packet Loss vs {data["x_label"]}',
                    xaxis: {{ title: '{data["x_label"]}' }},
                    yaxis: {{ title: 'Packet Loss (%)' }},
                    hovermode: 'closest'
                }};
                Plotly.newPlot('packet-loss-graph', data, layout);
            </script>
        </div>
"""
    
    def _generate_corruption_graph(self, data: Dict) -> str:
        """Generate corruption graph"""
        if self.config.vary_mode == "both":
            traces = []
            colors = ['purple', 'blue', 'red', 'green', 'orange', 'brown', 'pink', 'gray']
            for i, series in enumerate(data['series']):
                color = colors[i % len(colors)]
                freq_label = f"freq={series['write_freq']:.6f}s"
                traces.append({
                    'x': series['x'],
                    'y': series['corruption'],
                    'type': 'scatter',
                    'mode': 'lines+markers',
                    'name': f'Corruption - {freq_label}',
                    'marker': {'color': color}
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['corruption'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Corruption (%)',
                'marker': {'color': 'purple'}
            }]
        
        graph_data = json.dumps(traces)
        
        return f"""
        <div class="graph-container">
            <div class="graph-title">Packet Corruption (%)</div>
            <div id="corruption-graph"></div>
            <script>
                var data = {graph_data};
                var layout = {{
                    title: 'Packet Corruption vs {data["x_label"]}',
                    xaxis: {{ title: '{data["x_label"]}' }},
                    yaxis: {{ title: 'Corruption (%)' }},
                    hovermode: 'closest'
                }};
                Plotly.newPlot('corruption-graph', data, layout);
            </script>
        </div>
"""

