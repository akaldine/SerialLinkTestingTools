"""
Qt Sweep Test Dialog for T900 Data Rate Tester
"""

import os

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QLineEdit,
    QComboBox,
    QRadioButton,
    QGroupBox,
    QPushButton,
    QFileDialog,
    QMessageBox,
    QProgressBar,
    QWidget,
    QApplication,
)

from t900_sweep_test_qt import QtSweepTestRunner


class SweepTestDialog(QDialog):
    """Qt dialog to configure and run sweep tests"""

    def __init__(self, parent, main_gui):
        super().__init__(parent)
        self.setWindowTitle("Sweep Test Configuration")
        self.setAttribute(Qt.WA_DeleteOnClose, True)
        self.setModal(False)
        self.resize(700, 640)

        self.main_gui = main_gui
        self.runner = QtSweepTestRunner(main_gui)

        self._create_widgets()

    def _create_widgets(self):
        layout = QVBoxLayout(self)

        # Vary mode
        vary_group = QGroupBox("Variable Mode")
        vary_layout = QVBoxLayout(vary_group)
        self.mode_packet = QRadioButton("Vary Packet Size (keep write frequency stable)")
        self.mode_packet.setChecked(True)
        self.mode_freq = QRadioButton("Vary Write Frequency (keep packet size stable)")
        self.mode_both = QRadioButton("Vary Both Packet Size and Write Frequency")
        vary_layout.addWidget(self.mode_packet)
        vary_layout.addWidget(self.mode_freq)
        vary_layout.addWidget(self.mode_both)
        layout.addWidget(vary_group)

        # Packet size range
        size_group = QGroupBox("Packet Size Range (bytes)")
        size_layout = QGridLayout(size_group)
        size_layout.addWidget(QLabel("Min:"), 0, 0)
        self.size_min_edit = QLineEdit("100")
        size_layout.addWidget(self.size_min_edit, 0, 1)
        size_layout.addWidget(QLabel("Max:"), 0, 2)
        self.size_max_edit = QLineEdit("1000")
        size_layout.addWidget(self.size_max_edit, 0, 3)
        size_layout.addWidget(QLabel("Step:"), 0, 4)
        self.size_step_edit = QLineEdit("100")
        size_layout.addWidget(self.size_step_edit, 0, 5)
        size_layout.addWidget(QLabel("(Or comma-separated list: 100,200,500,1000)"), 1, 0, 1, 6)
        self.size_list_edit = QLineEdit()
        size_layout.addWidget(self.size_list_edit, 2, 0, 1, 6)
        layout.addWidget(size_group)

        # Write frequency range
        freq_group = QGroupBox("Write Frequency Range (seconds)")
        freq_layout = QGridLayout(freq_group)
        freq_layout.addWidget(QLabel("Min:"), 0, 0)
        self.freq_min_edit = QLineEdit("0.01")
        freq_layout.addWidget(self.freq_min_edit, 0, 1)
        freq_layout.addWidget(QLabel("Max:"), 0, 2)
        self.freq_max_edit = QLineEdit("0.1")
        freq_layout.addWidget(self.freq_max_edit, 0, 3)
        freq_layout.addWidget(QLabel("Step:"), 0, 4)
        self.freq_step_edit = QLineEdit("0.01")
        freq_layout.addWidget(self.freq_step_edit, 0, 5)
        freq_layout.addWidget(QLabel("(Or comma-separated list: 0.01,0.05,0.1,0.2)"), 1, 0, 1, 6)
        self.freq_list_edit = QLineEdit()
        freq_layout.addWidget(self.freq_list_edit, 2, 0, 1, 6)
        layout.addWidget(freq_group)

        # Test constants
        const_group = QGroupBox("Test Constants")
        const_layout = QGridLayout(const_group)
        const_layout.addWidget(QLabel("Number of Packets:"), 0, 0)
        self.num_packets_edit = QLineEdit("100")
        const_layout.addWidget(self.num_packets_edit, 0, 1)
        const_layout.addWidget(QLabel("Repeats per Point:"), 0, 2)
        self.repeats_edit = QLineEdit("1")
        const_layout.addWidget(self.repeats_edit, 0, 3)
        const_layout.addWidget(QLabel("Direction:"), 1, 0)
        direction_label = QLabel("Sender → Receiver (fixed)")
        const_layout.addWidget(direction_label, 1, 1)
        layout.addWidget(const_group)

        # Output
        output_group = QGroupBox("Output")
        output_layout = QGridLayout(output_group)
        output_layout.addWidget(QLabel("Output Directory:"), 0, 0)
        self.output_dir_edit = QLineEdit(os.getcwd())
        output_layout.addWidget(self.output_dir_edit, 0, 1)
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self._browse_output_dir)
        output_layout.addWidget(browse_button, 0, 2)
        layout.addWidget(output_group)

        # Progress
        progress_group = QGroupBox("Progress")
        progress_layout = QVBoxLayout(progress_group)
        self.progress_label = QLabel("Ready")
        progress_layout.addWidget(self.progress_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        layout.addWidget(progress_group)

        # Buttons
        button_row = QHBoxLayout()
        self.start_button = QPushButton("Start Sweep Test")
        self.start_button.clicked.connect(self._start_sweep)
        button_row.addWidget(self.start_button)
        self.stop_button = QPushButton("Stop Test")
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop_sweep)
        button_row.addWidget(self.stop_button)
        self.export_button = QPushButton("Export CSV")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_csv)
        button_row.addWidget(self.export_button)
        self.html_button = QPushButton("Generate HTML Report")
        self.html_button.setEnabled(False)
        self.html_button.clicked.connect(self._generate_html)
        button_row.addWidget(self.html_button)
        button_row.addStretch()
        close_button = QPushButton("Close")
        close_button.clicked.connect(self.close)
        button_row.addWidget(close_button)
        layout.addLayout(button_row)

    def _browse_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "Select Output Directory", self.output_dir_edit.text())
        if directory:
            self.output_dir_edit.setText(directory)

    def _parse_range(self, min_str: str, max_str: str, step_str: str, list_str: str, is_integer=False):
        if list_str and list_str.strip():
            try:
                if is_integer:
                    values = [int(float(x.strip())) for x in list_str.split(',') if x.strip()]
                else:
                    values = [float(x.strip()) for x in list_str.split(',') if x.strip()]
                if values:
                    return values
            except ValueError:
                pass

        try:
            min_val = float(min_str)
            max_val = float(max_str)
            step_val = float(step_str)
            if is_integer:
                return (int(min_val), int(max_val), int(step_val))
            return (min_val, max_val, step_val)
        except ValueError:
            return None

    def _validate_connections(self) -> bool:
        if not (self.main_gui.sender_connection and self.main_gui.sender_connection.is_open):
            QMessageBox.critical(self, "Error", "Sender not connected")
            return False
        for idx, conn in enumerate(self.main_gui.receiver_connections):
            if conn is None or not conn.is_open:
                QMessageBox.critical(self, "Error", f"Receiver {idx + 1} not connected")
                return False
        return True

    def _start_sweep(self):
        if self.runner.is_running:
            return

        size_range = self._parse_range(
            self.size_min_edit.text(),
            self.size_max_edit.text(),
            self.size_step_edit.text(),
            self.size_list_edit.text(),
            is_integer=True,
        )
        if size_range is None:
            QMessageBox.critical(self, "Error", "Invalid packet size range")
            return

        freq_range = self._parse_range(
            self.freq_min_edit.text(),
            self.freq_max_edit.text(),
            self.freq_step_edit.text(),
            self.freq_list_edit.text(),
            is_integer=False,
        )
        if freq_range is None:
            QMessageBox.critical(self, "Error", "Invalid write frequency range")
            return

        try:
            num_packets = int(self.num_packets_edit.text())
            repeats = int(self.repeats_edit.text())
        except ValueError:
            QMessageBox.critical(self, "Error", "Number of packets and repeats must be integers")
            return

        if num_packets <= 0 or repeats <= 0:
            QMessageBox.critical(self, "Error", "Number of packets and repeats must be > 0")
            return

        if not self._validate_connections():
            return

        self.runner.config.packet_size_range = size_range
        self.runner.config.write_freq_range = freq_range
        if self.mode_packet.isChecked():
            self.runner.config.vary_mode = "packet_size"
        elif self.mode_freq.isChecked():
            self.runner.config.vary_mode = "write_freq"
        else:
            self.runner.config.vary_mode = "both"
        self.runner.config.num_packets = num_packets
        self.runner.config.repeats = repeats
        self.runner.config.output_dir = self.output_dir_edit.text()

        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.export_button.setEnabled(False)
        self.html_button.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Starting sweep...")
        self.runner.results = []

        try:
            results = self.runner.run_sweep_test(progress_callback=self._update_progress)
            self._sweep_complete(results)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Sweep test failed: {str(e)}")
            self._sweep_complete([])

    def _update_progress(self, current: int, total: int, message: str):
        if total > 0:
            self.progress_bar.setMaximum(total)
            self.progress_bar.setValue(current)
        self.progress_label.setText(f"{current}/{total} - {message}")
        QApplication.processEvents()

    def _sweep_complete(self, results):
        self.runner.is_running = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)

        if results:
            self.export_button.setEnabled(True)
            self.html_button.setEnabled(True)
            self.progress_label.setText(f"Complete: {len(results)} results")
            QMessageBox.information(self, "Success", f"Sweep test complete: {len(results)} results")
        else:
            self.progress_label.setText("Test stopped or failed")

    def _stop_sweep(self):
        self.runner.is_running = False
        self.progress_label.setText("Stopping...")

    def _export_csv(self):
        if not self.runner.results:
            QMessageBox.warning(self, "Warning", "No results to export")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save CSV",
            os.path.join(self.output_dir_edit.text(), "sweep_results.csv"),
            "CSV Files (*.csv);;All Files (*)",
        )
        if not filename:
            return
        try:
            self.runner.export_csv(filename)
            QMessageBox.information(self, "Success", f"CSV exported to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to export CSV: {str(e)}")

    def _generate_html(self):
        if not self.runner.results:
            QMessageBox.warning(self, "Warning", "No results to generate report")
            return

        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Save HTML Report",
            os.path.join(self.output_dir_edit.text(), "sweep_report.html"),
            "HTML Files (*.html);;All Files (*)",
        )
        if not filename:
            return
        try:
            self.runner.generate_html_report(filename)
            QMessageBox.information(self, "Success", f"Report generated: {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to generate HTML: {str(e)}")

    def closeEvent(self, event):
        if self.runner.is_running:
            self.runner.is_running = False
            self.progress_label.setText("Stopping...")
        if hasattr(self.main_gui, "sweep_dialog"):
            self.main_gui.sweep_dialog = None
        super().closeEvent(event)

