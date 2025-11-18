# Serial Link Testing Tools

Two utilities live in this repository:

- **Serial Data Rate Tester (PyQt5)** – generic MVVM tester for any serial link (throughput, latency, corruption, sweeps). Files live in the repo root.
- **T900 Configuration GUI (Tkinter)** – vendor-specific tool for configuring Tianze T900 radios via AT commands. See `apps/config/README.md`.

Install dependencies once:

```bash
pip install -r requirements.txt
```

## Serial Data Rate Tester (Qt)

Files:

- `serial_data_rate_test_qt.py`
- `serial_data_rate_viewmodel.py`
- `serial_sweep_test_qt.py`
- `serial_sweep_test_qt_gui.py`

Launch the GUI:

```bash
python serial_data_rate_test_qt.py
```

Key capabilities:

- Manual, speed-target, and packet-count modes
- Multi-receiver (up to 3) monitoring with loss/corruption/latency metrics
- Configurable packet sizes, write frequency, and sweep automation
- RSSI capture for attached radios
- CSV + HTML sweep exports powered by Plotly

### Sweep Dialog (optional)

You can start sweep tests inside the main app via **Sweep Test**, or run the dialog directly:

```bash
python serial_sweep_test_qt_gui.py
```

## T900 Configuration GUI

Source: `apps/config/t900_config_gui.py`

Usage instructions, register reference, and troubleshooting tips live in [`apps/config/README.md`](apps/config/README.md).

## Repository Layout

- `serial_*.py` – serial data rate tester and supporting modules
- `apps/config/` – T900 configuration GUI + README
- `results/` – ignored workspace for local sweep outputs/logs
- `.gitignore`, `requirements.txt`, `README.md`

## License

MIT License – see `LICENSE`.

