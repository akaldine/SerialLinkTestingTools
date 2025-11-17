# T900 Data Rate Test Tool

A separate GUI application for testing end-to-end data rate, packet corruption, and latency between two T900 radios.

## Features

- **Dual Connection Management**: Connect to both sender and receiver USB ports independently
- **Configurable Test Parameters**:
  - Write Size (buffer): Packet payload size in bytes
  - Write Frequency: Time between packet transmissions in seconds
  - Test Length: Duration of the test in seconds (default: 10s)
- **Real-Time Measurements**:
  - Aggregate Data Rate (B/s and KB/s)
  - Packet Loss Rate (%)
  - Corrupt Packet Rate (%)
  - Average, Min, and Max Latency (ms)
  - Packet counts (sent/received)
  - Byte counts (sent/received)
- **Packet Integrity**: Uses SHA-256 hashing to detect corrupted packets
- **Latency Measurement**: Measures end-to-end latency using packet timestamps

## Installation

Same requirements as the main configuration tool:
```bash
pip install -r requirements.txt
```

## Usage

1. **Run the application**:
   ```bash
   python t900_data_rate_test.py
   ```

2. **Connect Devices**:
   - Connect the sender T900 radio to one USB port
   - Connect the receiver T900 radio to another USB port
   - Select the appropriate ports in the GUI
   - Set baud rates (default: 9600)
   - Click "Connect" for both sender and receiver

3. **Configure Test Parameters**:
   - **Write Size**: Size of each packet payload in bytes (e.g., 100 bytes)
   - **Write Frequency**: Time between sending packets in seconds (e.g., 0.1s = 10 packets/second)
   - **Test Length**: How long to run the test in seconds (default: 10s)

4. **Run Test**:
   - Click "Start Test" to begin
   - Statistics update in real-time
   - Click "Stop Test" to stop early (or wait for test to complete)
   - View results in the statistics panel and log

5. **Clear Results**:
   - Click "Clear Results" to reset statistics and log

## Packet Structure

Each test packet contains:
- **Sequence Number** (4 bytes): Packet sequence number
- **Timestamp** (8 bytes): Send timestamp (double precision)
- **Hash** (32 bytes): SHA-256 hash of payload for integrity checking
- **Payload** (variable): Test data (size = Write Size)

Total packet size = 44 bytes (header) + Write Size (payload)

## Measurements Explained

- **Aggregate Data Rate**: Total bytes received per second (includes packet overhead)
- **Packet Loss Rate**: Percentage of sent packets that were never received
- **Corrupt Packet Rate**: Percentage of received packets that failed integrity check
- **Latency**: Time from packet transmission to reception (one-way delay)
  - Average: Mean latency across all received packets
  - Min: Minimum observed latency
  - Max: Maximum observed latency

## Test Setup Recommendations

1. **Ensure Radios are Configured**:
   - Both radios should be in data mode (not AT command mode)
   - Same network address (S104)
   - Same network type (S133)
   - Same wireless link rate (S103)
   - Proper addressing (S105, S118, S140) for point-to-point or point-to-multipoint

2. **Baud Rate**:
   - Use the same baud rate on both sender and receiver
   - Ensure baud rate matches the radio's serial port configuration (S102)

3. **Test Parameters**:
   - Start with small write sizes (100-500 bytes) and low frequency (0.1-1.0s)
   - Gradually increase to find maximum throughput
   - Be aware that very high frequencies may cause buffer overflows

4. **Interpretation**:
   - High packet loss may indicate network issues or buffer overflow
   - High corruption rate may indicate signal quality issues
   - Latency measurements help identify network delays

## Notes

- The test runs in separate threads for sender and receiver to ensure accurate timing
- Statistics update every 100ms during the test
- Latency measurements are limited to the last 1000 samples for performance
- Packet corruption is detected using SHA-256 hash verification
- The test automatically stops after the specified test length

## Troubleshooting

- **No packets received**: Check that both radios are connected and in data mode
- **High packet loss**: Verify network configuration, signal strength, and buffer sizes
- **Connection errors**: Ensure ports are not in use by other applications
- **Invalid parameters**: Make sure all numeric values are positive numbers

