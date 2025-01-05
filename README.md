# Weller WX Station Controller
A Python-based controller for Weller WX series soldering stations with web interface support.

# Compatible WX Stations
- WX1
- WX1 A
- WX1 D
- WX2
- WX2 A
- Wx2 D

## Description
This software provides comprehensive control and monitoring capabilities for Weller WX series soldering stations. It features both a command-line interface and a modern web interface for controlling temperature, monitoring status, and managing station settings.

## Key Features
- 🌡️ Real-time temperature monitoring and control
- 🎯 Preset temperature management
- 📊 Temperature history graphing
- 🌐 Web interface with responsive design
- 📱 Mobile-friendly controls
- 🔄 Auto-detection of serial ports
- 📈 Temperature statistics and logging
- 🧪 Demo mode for testing

## Installation
*Instructions for installation.*

## Usage

### Basic Command Line Usage
The program will prompt you to choose between:
1. Connect to real station
2. Start demo mode

### Web Interface
The web interface can be accessed at `http://localhost:5000` (default port) and provides:
- Temperature controls for both channels
- Real-time temperature graphs
- Tool information display
- Preset temperature management
- Remote mode control

## Configuration Options
The following settings can be configured:
- Port number for web interface
- Basic authentication
- Temperature limits
- Logging options
- History data points

## Command Reference

### Temperature Control
- **Set temperature:** 50°C - 450°C range
- **Preset temperatures:** Two presets per channel
- **Temperature units:** °C/°F switchable

### Operating Modes
- **ON:** Normal operation
- **STANDBY:** Low temperature standby
- **OFF:** Heating off
- **AUTO-OFF:** Automatic shutdown

### Remote Control
- **DISABLED:** Local control only
- **ENABLED:** Remote control active
- **ENABLED_WITH_LOCK:** Remote control with front panel lock

## Requirements
- Python 3.6+
- pyserial
- Flask
- plotly.js (included)

## Acknowledgements
- Weller is a registered trademark of Apex Tool Group, LLC
- This is an unofficial project not affiliated with Weller or Apex Tool Group
