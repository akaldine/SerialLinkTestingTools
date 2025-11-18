# Tianze T900 Application Suite

This repository now contains several related GUI tools for Tianze T900 radios. Project files are grouped under `apps/`:

- `apps/config/` – AT command configuration utility (Tkinter)
- `apps/data_rate/tk/` – legacy Tkinter-based data-rate tester and sweep tool
- `apps/data_rate/qt/` – PyQt5 data-rate tester with MVVM architecture and sweep dialog
- `results/` – captured sweep logs, HTML reports, and related analysis outputs

Install dependencies once via:

```bash
pip install -r requirements.txt
```

## Applications

### Config GUI (Tkinter)

A graphical user interface (GUI) application for configuring Tianze T900 radio modules via AT commands.

## Features

- **Serial Connection Management**: Connect to T900 radios via serial port with configurable baud rates
- **Device Information**: Query hardware version, firmware version, software version, and serial number
- **Register Configuration**: Configure all T900 registers with an intuitive GUI:
  - Basic settings (operating mode, baud rates, addresses, power)
  - Network settings (network type, addresses, repeaters)
  - Advanced settings (encryption, channel access modes, TDMA)
  - Read-only status (RSSI values)
- **Command Console**: Send custom AT commands and view responses
- **Factory Defaults**: Load pre-configured factory default settings for different network topologies
- **Parameter Management**: Read/write individual or all registers, save configuration to device

## Installation

1. Install Python 3.7 or higher
2. Install required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Run the application:
   ```bash
   python apps/config/t900_config_gui.py
   ```

2. **Connect to Device**:
   - Go to the "Connection" tab
   - Select your serial port (click "Refresh" if needed)
   - Set baud rate (default: 9600)
   - Click "Connect"
   - After connecting, click "Enter AT Mode" button to enter AT command configuration mode
   - The device must be in AT command mode to send AT commands. The sequence is: idle 1s → send "+++" → idle 1s
   - Use "Exit AT Mode (ATA)" button to exit AT mode and return to data mode

3. **Query Device Information**:
   - Go to the "Device Information" tab
   - Click buttons to query hardware version, firmware version, software version, or serial number
   - Use "Display All Parameters" to see current configuration

4. **Configure Registers**:
   - Go to the "Configuration" tab
   - For each register:
     - Click "Read" to read current value from device
     - Modify the value in the dropdown/entry field
     - Click "Write" to write the value to device
   - Use "Read All Registers" or "Write All Registers" for bulk operations
   - **Important**: After writing registers, click "Save Configuration (AT&W)" to save to device

5. **Send Custom Commands**:
   - Go to the "Command Console" tab
   - Type AT commands in the input field
   - Press Enter or click "Send"

6. **Factory Defaults**:
   - Go to the "Configuration" tab
   - Click "Factory Defaults"
   - Select desired network topology
   - Click "Apply"
   - Remember to save with AT&W after loading defaults

## Register Descriptions

### Basic Settings
- **S101**: Operating Mode (Master/Repeater/Slave)
- **S102**: Serial Baud Rate
- **S103**: Wireless Link Rate
- **S104**: Network Address (ID) - All devices must have the same
- **S105**: Unit Address (Local Address) - Unique per device
- **S108**: Output Power (dBm)
- **S110**: Serial Data Format (8N1 only)
- **S113**: Packet Retransmissions

### Network Settings
- **S133**: Network Type (Point-to-Multipoint/Point-to-Point/Mesh with Center)
- **S140**: Destination Address
- **S141**: Repeater Y/N (master only)
- **S118**: Sync Address
- **S114**: Repeater Index
- **S143**: Repeater Index Use GPIO

### Advanced Settings
- **S142**: Serial Channel Mode (RS232/RS485)
- **S159**: Encryption Enable
- **S160**: Encryption Key (256-bit)
- **S244**: Channel Access Mode (RTS/CTS/TDMA)
- **S221**: Unit Address Max for TDMA
- **S220**: TDMA TX Time Slot

### Read-Only Status
- **S123**: RSSI From Master (dBm)
- **S124**: RSSI From Slave (dBm)

## Important Notes

1. **Save Configuration**: After modifying any register, you must execute `AT&W` (or use "Save Configuration" button) to save changes to non-volatile memory. Otherwise, changes will be lost on power cycle.

2. **Network Consistency**: All devices on a network must have:
   - Same Network Address (S104)
   - Same Network Type (S133)
   - Same Wireless Link Rate (S103)

3. **Address Assignment**: For point-to-point networks with automatic address assignment, set S105 (Unit Address) to 0. For manual assignment, configure S105, S118 (Sync Address), and S140 (Destination Address) for each device.

4. **TDMA Mode**: TDMA mode (S244=1) supports only point-to-multipoint and mesh with center networks. Configure S221 (Unit Address Max) appropriately for TDMA.

5. **Encryption**: When enabling encryption (S159=1), ensure all devices on the network use the same encryption key (S160).

## Troubleshooting

- **Connection Issues**: Ensure the correct serial port is selected and the device is powered on
- **No Response**: Check baud rate matches device configuration (default is 9600)
- **Command Errors**: Verify device is in AT command mode (may need to send "+++" first on some devices)
- **Changes Not Saving**: Remember to execute AT&W command after making changes

## AT Command Reference

- `+++` (with 1s idle before and after) - Enter AT command configuration mode from data mode
- `ATI1` - Query hardware version
- `ATI2` - Query firmware version
- `ATI3` - Query software version
- `ATI4` - Query serial number
- `AT&V` - Display current parameter table
- `AT&W` - Save current parameter table
- `ATSxxx?` - Query register Sxxx
- `ATSxxx=yyy` - Write register Sxxx as yyy
- `AT&Fn` - Load factory default (n = 4,5,7-12)
- `ATA` - Exit AT command mode and enter data mode

# Data Rate Test Applications

### Tkinter Version
- Files: `apps/data_rate/tk/t900_data_rate_test.py`, `t900_sweep_test.py`, `t900_sweep_test_gui.py`
- Launch data-rate tester:
  ```bash
  python apps/data_rate/tk/t900_data_rate_test.py
  ```
- Launch sweep tester UI:
  ```bash
  python apps/data_rate/tk/t900_sweep_test_gui.py
  ```

### PyQt5 Version
- Files: `apps/data_rate/qt/t900_data_rate_test_qt.py`, `t900_viewmodel.py`, `t900_sweep_test_qt.py`, `t900_sweep_test_qt_gui.py`
- Launch MVVM Qt tester:
  ```bash
  python apps/data_rate/qt/t900_data_rate_test_qt.py
  ```
- Launch sweep dialog from within the Qt app via the **Sweep Test** button, or run directly:
  ```bash
  python apps/data_rate/qt/t900_sweep_test_qt_gui.py
  ```

# License

This toolset is provided as-is for working with Tianze T900 radio modules.

# References

- Tianze T900 Radio Module Manual
- Zhejiang Tianze Communication Technology Co., Ltd. - www.okseeker.com

