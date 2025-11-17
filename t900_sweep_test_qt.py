"""
Qt Sweep Test Module for T900 Data Rate Testing
"""

import csv
import json
import os
import time
import webbrowser
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

from PyQt5.QtWidgets import QApplication


class SweepTestConfig:
    """Configuration for sweep test parameters"""

    def __init__(self):
        self.packet_size_range = None  # (min, max, step) tuple or list of ints
        self.write_freq_range = None  # (min, max, step) tuple or list of floats
        self.vary_mode = "packet_size"  # "packet_size", "write_freq", "both"
        self.num_packets = 100
        self.repeats = 1
        self.output_dir = ""


class QtSweepTestRunner:
    """Runs sweep tests against the Qt data rate tester"""

    def __init__(self, main_gui):
        self.main_gui = main_gui
        self.config = SweepTestConfig()
        self.results: List[Dict] = []
        self.is_running = False
        self.current_test = 0
        self.total_tests = 0

    def _process_events(self):
        app = QApplication.instance()
        if app:
            app.processEvents()

    def generate_test_combinations(self) -> List[Tuple[int, float]]:
        """Generate combinations of packet size and write frequency"""
        combinations: List[Tuple[int, float]] = []

        if self.config.vary_mode == "packet_size":
            if isinstance(self.config.packet_size_range, tuple):
                min_size, max_size, step = self.config.packet_size_range
                packet_sizes = list(range(int(min_size), int(max_size) + 1, int(step)))
            else:
                packet_sizes = [int(s) for s in self.config.packet_size_range]

            if isinstance(self.config.write_freq_range, tuple):
                write_freq = float(self.config.write_freq_range[0])
            else:
                write_freq = float(self.config.write_freq_range[0])

            for size in packet_sizes:
                combinations.append((size, write_freq))

        elif self.config.vary_mode == "write_freq":
            if isinstance(self.config.write_freq_range, tuple):
                min_freq, max_freq, step = self.config.write_freq_range
                write_freqs: List[float] = []
                current = min_freq
                while current <= max_freq + 1e-12:
                    write_freqs.append(round(current, 12))
                    current += step
            else:
                write_freqs = [float(v) for v in self.config.write_freq_range]

            if isinstance(self.config.packet_size_range, tuple):
                packet_size = int(self.config.packet_size_range[0])
            else:
                packet_size = int(self.config.packet_size_range[0])

            for freq in write_freqs:
                combinations.append((packet_size, freq))

        else:  # both
            if isinstance(self.config.packet_size_range, tuple):
                min_size, max_size, step = self.config.packet_size_range
                packet_sizes = list(range(int(min_size), int(max_size) + 1, int(step)))
            else:
                packet_sizes = [int(s) for s in self.config.packet_size_range]

            if isinstance(self.config.write_freq_range, tuple):
                min_freq, max_freq, step = self.config.write_freq_range
                write_freqs: List[float] = []
                current = min_freq
                while current <= max_freq + 1e-12:
                    write_freqs.append(round(current, 12))
                    current += step
            else:
                write_freqs = [float(v) for v in self.config.write_freq_range]

            for size in packet_sizes:
                for freq in write_freqs:
                    combinations.append((size, freq))

        return combinations

    def run_sweep_test(self, progress_callback=None) -> List[Dict]:
        """Run the configured sweep test"""
        self.is_running = True
        self.results = []
        combinations = self.generate_test_combinations()
        self.total_tests = len(combinations) * self.config.repeats
        self.current_test = 0

        try:
            for packet_size, write_freq in combinations:
                if not self.is_running:
                    break

                for repeat in range(self.config.repeats):
                    if not self.is_running:
                        break

                    self.current_test += 1
                    if progress_callback:
                        progress_callback(
                            self.current_test,
                            self.total_tests,
                            f"size={packet_size}, freq={write_freq:.6f}, repeat {repeat + 1}"
                        )

                    result = self._run_single_test(packet_size, write_freq)
                    if result:
                        self.results.append(result)

                    self._process_events()
                    time.sleep(0.2)
        finally:
            self.is_running = False

        return self.results

    def _run_single_test(self, packet_size: int, write_freq: float) -> Optional[Dict]:
        """Configure and run a single test from the sweep"""
        try:
            # Configure GUI for packet-count mode
            self.main_gui.input_mode_combo.setCurrentText("Packet-Count")
            self._process_events()

            self.main_gui.packet_count_size_edit.setText(str(packet_size))
            self.main_gui.packet_count_freq_edit.setText(f"{write_freq:.6f}")
            self.main_gui.num_packets_edit.setText(str(self.config.num_packets))
            self.main_gui._update_packet_count_calculations()
            self._process_events()

            # Clear buffers
            self.main_gui._clear_serial_buffers()
            time.sleep(0.1)

            # Start test
            self.main_gui._start_test()

            # Wait for completion
            max_wait = 300
            wait_time = 0
            while self.main_gui.test_running and wait_time < max_wait and self.is_running:
                time.sleep(0.1)
                wait_time += 0.1
                self._process_events()

            if wait_time >= max_wait:
                self.main_gui._stop_test()
                return None

            # Ensure final calculations are done
            calc_wait = 0
            while calc_wait < 3.0:
                stats = self.main_gui.stats
                elapsed = stats.get('elapsed_time')
                if elapsed is not None and elapsed > 0 and stats.get('data_rate_total_bps') is not None:
                    break
                self._process_events()
                time.sleep(0.1)
                calc_wait += 0.1

            stats = self.main_gui.stats

            result: Dict = {
                'packet_size': packet_size,
                'write_freq': write_freq,
                'num_packets': self.config.num_packets,
                'direction': "Sender → Receiver",
                'timestamp': time.time(),
            }

            total_sent = stats.get('packets_sent', 0)
            total_received = stats.get('packets_received', 0)
            total_corrupt = stats.get('packets_corrupt', 0)

            result['speed_total_bps'] = stats.get('data_rate_total_bps') or 0
            result['speed_valid_bps'] = stats.get('data_rate_valid_bps') or 0
            result['send_rate_bps'] = stats.get('send_rate_bps') or 0

            latencies = []
            for rstat in getattr(self.main_gui, 'receiver_stats', []):
                latencies.extend(list(rstat['latency_samples']))

            if latencies:
                result['latency_avg_ms'] = sum(latencies) / len(latencies)
                result['latency_min_ms'] = min(latencies)
                result['latency_max_ms'] = max(latencies)
            else:
                result['latency_avg_ms'] = 0
                result['latency_min_ms'] = 0
                result['latency_max_ms'] = 0

            if total_sent > 0:
                result['packet_loss_percent'] = ((total_sent - total_received) / total_sent) * 100
            else:
                result['packet_loss_percent'] = 0

            if total_received > 0:
                result['corruption_percent'] = (total_corrupt / total_received) * 100
            else:
                result['corruption_percent'] = 0

            elapsed_time_val = stats.get('elapsed_time')
            if elapsed_time_val is not None and elapsed_time_val > 0:
                result['elapsed_time'] = elapsed_time_val
            elif stats.get('start_time') and stats.get('end_time'):
                result['elapsed_time'] = stats['end_time'] - stats['start_time']
            else:
                result['elapsed_time'] = 0

            result['packets_sent'] = total_sent
            result['packets_received'] = total_received
            result['packets_corrupt'] = total_corrupt

            return result
        except Exception:
            return None

    def export_csv(self, filename: str):
        """Export sweep results to CSV"""
        if not self.results:
            raise ValueError("No results to export")

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

    def generate_html_report(self, filename: str):
        """Generate HTML report with graphs"""
        if not self.results:
            raise ValueError("No results to generate report")

        data = self._prepare_plot_data()
        html = self._generate_html_content(data)

        with open(filename, 'w') as f:
            f.write(html)

        webbrowser.open(f'file://{os.path.abspath(filename)}')

    def _prepare_plot_data(self) -> Dict:
        """Prepare data for plotting"""
        data = defaultdict(list)
        if self.config.vary_mode == "both":
            by_freq = defaultdict(list)
            for result in self.results:
                by_freq[result['write_freq']].append(result)

            data['series'] = []
            for freq, results in sorted(by_freq.items()):
                series_data = {
                    'write_freq': freq,
                    'x': [r['packet_size'] for r in results],
                    'speed_total': [r['speed_total_bps'] / 1000 for r in results],
                    'speed_valid': [r['speed_valid_bps'] / 1000 for r in results],
                    'send_rate': [r['send_rate_bps'] / 1000 for r in results],
                    'latency_avg': [r['latency_avg_ms'] for r in results],
                    'packet_loss': [r['packet_loss_percent'] for r in results],
                    'corruption': [r['corruption_percent'] for r in results],
                }
                data['series'].append(series_data)
            data['x_label'] = "Packet Size (bytes)"
        else:
            x_label = "Packet Size (bytes)" if self.config.vary_mode == "packet_size" else "Write Frequency (s)"
            data['x_label'] = x_label
            for result in self.results:
                x = result['packet_size'] if self.config.vary_mode == "packet_size" else result['write_freq']
                data['x'].append(x)
                data['speed_total'].append(result['speed_total_bps'] / 1000)
                data['speed_valid'].append(result['speed_valid_bps'] / 1000)
                data['send_rate'].append(result['send_rate_bps'] / 1000)
                data['latency_avg'].append(result['latency_avg_ms'])
                data['packet_loss'].append(result['packet_loss_percent'])
                data['corruption'].append(result['corruption_percent'])

        return data

    def _generate_html_content(self, data: Dict) -> str:
        """Generate HTML content with Plotly graphs"""
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
            max-width: 1200px;
            margin: 0 auto;
            background: #fff;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 2px solid #4CAF50;
            padding-bottom: 10px;
        }}
        .graph-container {{
            margin: 30px 0;
        }}
        .graph-title {{
            font-size: 18px;
            margin-bottom: 10px;
        }}
        .info {{
            background: #e3f2fd;
            padding: 10px;
            border-radius: 4px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>T900 Sweep Test Results</h1>
        <div class="info">
            <p><strong>Vary Mode:</strong> {self.config.vary_mode}</p>
            <p><strong>Number of Packets:</strong> {self.config.num_packets}</p>
            <p><strong>Repeats:</strong> {self.config.repeats}</p>
            <p><strong>Total Tests:</strong> {len(self.results)}</p>
        </div>
"""
        html += self._generate_speed_graph(data)
        html += self._generate_latency_graph(data)
        html += self._generate_packet_loss_graph(data)
        html += self._generate_corruption_graph(data)
        html += """
    </div>
</body>
</html>
"""
        return html

    def _generate_speed_graph(self, data: Dict) -> str:
        if self.config.vary_mode == "both":
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
                    'marker': {'color': color},
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['speed_valid'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Speed Valid (kbps)',
                'marker': {'color': 'green'},
            }]

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
                    yaxis: {{ title: 'Data Rate (kbps)' }}
                }};
                Plotly.newPlot('speed-graph', data, layout);
            </script>
        </div>
"""

    def _generate_latency_graph(self, data: Dict) -> str:
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
                    'marker': {'color': color},
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['latency_avg'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Avg Latency (ms)',
                'marker': {'color': 'blue'},
            }]

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
                    yaxis: {{ title: 'Latency (ms)' }}
                }};
                Plotly.newPlot('latency-graph', data, layout);
            </script>
        </div>
"""

    def _generate_packet_loss_graph(self, data: Dict) -> str:
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
                    'marker': {'color': color},
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['packet_loss'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Packet Loss (%)',
                'marker': {'color': 'red'},
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
                    yaxis: {{ title: 'Packet Loss (%)' }}
                }};
                Plotly.newPlot('packet-loss-graph', data, layout);
            </script>
        </div>
"""

    def _generate_corruption_graph(self, data: Dict) -> str:
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
                    'marker': {'color': color},
                })
        else:
            traces = [{
                'x': data['x'],
                'y': data['corruption'],
                'type': 'scatter',
                'mode': 'lines+markers',
                'name': 'Corruption (%)',
                'marker': {'color': 'purple'},
            }]

        graph_data = json.dumps(traces)
        return f"""
        <div class="graph-container">
            <div class="graph-title">Packet Corruption (%)</div>
            <div id="corruption-graph"></div>
            <script>
                var data = {graph_data};
                var layout = {{
                    title: 'Corruption vs {data["x_label"]}',
                    xaxis: {{ title: '{data["x_label"]}' }},
                    yaxis: {{ title: 'Corruption (%)' }}
                }};
                Plotly.newPlot('corruption-graph', data, layout);
            </script>
        </div>
"""

