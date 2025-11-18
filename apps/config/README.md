# T900 Configuration GUI

A Tkinter-based utility for configuring Tianze T900 radio modules over a serial link.

## Features

- Serial connection management with selectable ports and baud rates
- Device information queries (hardware, firmware, software, serial number)
- Register read/write for every T900 setting (basic, network, advanced, read-only)
- Command console for arbitrary AT commands
- Factory default presets for common topologies
- Parameter management (bulk read/write, save to device)

## Installation

```bash
pip install -r ../../requirements.txt
```

## Usage

```bash
python apps/config/t900_config_gui.py
```

1. Connect to the desired serial port (use **Refresh** if needed) and click **Connect**.
2. Enter AT mode (idle 1 s → send `+++` → idle 1 s) to interact with registers.
3. Use the **Device Information** tab to query hardware/firmware/software/serial.
4. Configure registers via the **Configuration** tab; remember to save with `AT&W`.
5. Send ad-hoc AT commands from the **Command Console**.
6. Load factory defaults, apply, then save to device.

### Register Reference Highlights

- **Basic**: S101 (mode), S102 (serial baud), S103 (wireless rate), S104/S105 (addresses)
- **Network**: S133 (network type), S140 (destination), S118 (sync), repeater controls
- **Advanced**: S142 (RS232/RS485), S159/S160 (encryption), S244 (RTS/CTS/TDMA)
- **Read-only**: S123/S124 RSSI

### Notes

1. Always run `AT&W` (or the GUI equivalent) after writing registers.
2. Keep network address, type, and wireless rate consistent across radios.
3. TDMA mode (S244=1) requires proper slot/index configuration.
4. For manual addressing, configure S105, S118, and S140 per device.

For additional detail, consult the Tianze T900 Radio Module Manual.

