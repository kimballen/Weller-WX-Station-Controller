import serial
import time
from enum import IntEnum
import logging
from datetime import datetime, timedelta
import json
from typing import Dict, List, Optional, Union
from collections import deque
from flask import Flask, jsonify, render_template_string, request
import threading
import csv
from functools import wraps
import serial.tools.list_ports
import random
from flask_basicauth import BasicAuth

html_template = '''
<!DOCTYPE html>
<html>
<head>
    <title>Weller Station Control</title>
    <meta http-equiv="refresh" content="5">
    <style>
        body { font-family: Arial; padding: 20px; background-color: #f0f0f0; }
        .channel { 
            margin: 20px; 
            padding: 20px; 
            border: 1px solid #ccc;
            border-radius: 10px;
            background-color: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .controls { margin-top: 15px; }
        button { 
            margin: 5px; 
            padding: 8px 15px; 
            border: none;
            border-radius: 5px;
            background-color: #4CAF50;
            color: white;
            cursor: pointer;
        }
        button:hover { background-color: #45a049; }
        .status { margin: 10px 0; }
        .temp-slider {
            width: 100%;
            margin: 10px 0;
        }
        .temp-readout {
            font-size: 24px;
            font-weight: bold;
            color: #2196F3;
        }
        .stats {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
            margin: 10px 0;
        }
        .stat-item {
            padding: 5px;
            background-color: #f8f8f8;
            border-radius: 5px;
        }
        .error { color: red; }
        .success { color: green; }
        .station-info {
            background-color: #e8f5e9;
            padding: 15px;
            border-radius: 10px;
            margin-bottom: 20px;
        }
        .chart {
            height: 200px;
            margin: 20px 0;
            background: #f8f8f8;
            border-radius: 5px;
        }
        .temp-control {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 15px 0;
        }
        .slider-container {
            flex-grow: 1;
        }
        .temp-display {
            min-width: 80px;
            text-align: center;
            font-size: 1.2em;
        }
        .settings-btn {
            position: absolute;
            top: 20px;
            right: 20px;
            padding: 10px;
            background: #2196F3;
            border: none;
            border-radius: 5px;
            color: white;
            cursor: pointer;
        }

        .modal {
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0,0,0,0.5);
            z-index: 1000;
        }

        .modal-content {
            position: relative;
            background: white;
            margin: 10% auto;
            padding: 20px;
            width: 80%;
            max-width: 500px;
            border-radius: 10px;
        }

        .close-btn {
            position: absolute;
            right: 10px;
            top: 10px;
            cursor: pointer;
            font-size: 24px;
        }

        .settings-group {
            margin: 15px 0;
        }

        .settings-group label {
            display: block;
            margin-bottom: 5px;
        }
    </style>
    <script src="https://cdn.plot.ly/plotly-latest.min.js"></script>
    <script>
        let tempValues = {};
        let sliderValue = {};  // Nytt objekt för att spara slider-värden
        let charts = {};
        
        function updateTempValue(channel, value) {
            sliderValue[channel] = parseFloat(value);
            document.getElementById(`tempSliderValue${channel}`).textContent = 
                Math.round(value) + '°' + settings.unit;
        }
        
        function setTemp(channel) {
            const temp = sliderValue[channel];
            if (!temp) {
                showMessage('Please select a temperature first', true);
                return;
            }
            
            fetch(`/api/set_temperature/${channel}/${temp}`, {
                method: 'POST',
                headers: {
                    'Accept': 'application/json',
                    'Content-Type': 'application/json'
                }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Temperature set to ${data.temperature}°C`, false);
                    updateDisplay();
                }
            })
            .catch(error => showMessage('Error: ' + error.message, true));
        }

        function setPreset(channel, presetNum, temp) {
            fetch(`/api/set_preset/${channel}/${presetNum}/${temp}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Preset ${presetNum} set to ${Math.round(temp)}°C`, false);
                    // Force update the display
                    const presetElement = document.querySelector(`#preset${presetNum}Value${channel}`);
                    if (presetElement) {
                        presetElement.textContent = Math.round(temp) + '°C';
                    }
                }
            });
        }

        function activatePreset(channel, presetNum) {
            fetch(`/api/activate_preset/${channel}/${presetNum}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Activated preset ${presetNum}`, false);
                    updateDisplay();
                }
            });
        }

        function updateCharts(data) {
            if (!data.status || !data.temperature_history) return;
            
            [1, 2].forEach(channel => {
                const channelKey = `channel${channel}`;
                if (data.temperature_history[channelKey].length > 0) {
                    const temps = data.temperature_history[channelKey].map(d => d.temperature);
                    const times = data.temperature_history[channelKey].map(d => d.time);
                    
                    Plotly.update(`chart${channel}`, {
                        x: [times],
                        y: [temps]
                    });
                }
            });
        }
        
        function showMessage(message, isError) {
            const msgDiv = document.getElementById('messages');
            msgDiv.textContent = message;
            msgDiv.className = isError ? 'error' : 'success';
            setTimeout(() => msgDiv.textContent = '', 3000);
        }

        function initializeCharts() {
            [1, 2].forEach(channel => {
                const layout = {
                    title: `Channel ${channel} Temperature`,
                    xaxis: { title: 'Time' },
                    yaxis: { 
                        title: 'Temperature (°C)',
                        range: [0, 500]
                    },
                    height: 300,
                    margin: { t: 30, r: 10, b: 30, l: 40 }
                };
                
                const config = {
                    responsive: true,
                    displayModeBar: false
                };
                
                Plotly.newPlot(`chart${channel}`, [{
                    y: [],
                    type: 'scatter',
                    mode: 'lines',
                    name: 'Temperature',
                    line: { color: channel === 1 ? '#2196F3' : '#4CAF50' }
                }], layout, config);
            });
        }
        
        let settings = {
            unit: 'C',
            decimals: 1
        };

        function updateDisplaySettings() {
            localStorage.setItem('wellerSettings', JSON.stringify(settings));
            updateAllTemperatures();
        }

        function formatTemperature(temp, forceNoDecimals = false) {
            const value = settings.unit === 'F' ? (temp * 9/5 + 32) : temp;
            if (forceNoDecimals) {
                return Math.round(value) + '°' + settings.unit;
            }
            return value.toFixed(settings.decimals) + '°' + settings.unit;
        }

        function updateAllTemperatures() {
            document.querySelectorAll('.temp-readout').forEach(el => {
                const tempValue = parseFloat(el.getAttribute('data-temp') || '0');
                el.textContent = 'Current: ' + formatTemperature(tempValue);
            });
            
            document.querySelectorAll('.temp-display').forEach(el => {
                const tempValue = parseFloat(el.getAttribute('data-temp') || '0');
                el.textContent = formatTemperature(tempValue, true);  // Force no decimals
            });
        }

        function showSettings() {
            document.getElementById('settingsModal').style.display = 'block';
            document.getElementById('unitSelect').value = settings.unit;
            document.getElementById('decimalsSelect').value = settings.decimals;
        }

        function closeSettings() {
            document.getElementById('settingsModal').style.display = 'none';
        }

        function saveSettings() {
            settings.unit = document.getElementById('unitSelect').value;
            settings.decimals = parseInt(document.getElementById('decimalsSelect').value);
            updateDisplaySettings();
            closeSettings();
        }

        // Modify existing updateDisplay function
        function updateDisplay() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    if (data.success && data.status) {
                        Object.entries(data.status).forEach(([channel, info]) => {
                            const idx = channel.slice(-1);
                            const tempElement = document.querySelector(`#temp${idx}Value`);
                            tempElement.setAttribute('data-temp', info.temperature);
                            tempElement.textContent = formatTemperature(info.temperature);
                        });
                        updateCharts(data);
                    }
                })
                .catch(console.error);
        }

        // Load settings on startup
        document.addEventListener('DOMContentLoaded', () => {
            const savedSettings = localStorage.getItem('wellerSettings');
            if (savedSettings) {
                settings = JSON.parse(savedSettings);
            }
            initializeCharts();
            setInterval(updateDisplay, 1000);
        });

        function triggerFingerswitch(channel) {
            const seconds = document.getElementById(`fingerswitchTime${channel}`).value;
            fetch(`/api/fingerswitch/${channel}/${seconds}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Fingerswitch activated for ${seconds} seconds`, false);
                }
            });
        }

        function setRemoteMode(mode) {
            fetch('/api/remote_mode/' + mode, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    showMessage(`Remote mode set to ${mode}`, false);
                }
            });
        }

        function updateToolInfo(channel) {
            fetch('/api/tool_info/' + channel)
                .then(response => response.json())
                .then(data => {
                    if (data.success) {
                        const info = data.info;
                        const container = document.querySelector(`#toolInfo${channel}`);
                        container.querySelector('.tool-name').textContent = info.name;
                        container.querySelector('.tool-power').textContent = info.power;
                        container.querySelector('.tool-max-temp').textContent = info.max_temp + '°C';
                        container.querySelector('.tool-description').textContent = info.description;
                    }
                });
        }
    </script>
</head>
<body>
    <button class="settings-btn" onclick="showSettings()">⚙️ Settings</button>

    <div id="settingsModal" class="modal">
        <div class="modal-content">
            <span class="close-btn" onclick="closeSettings()">&times;</span>
            <h2>Settings</h2>
            
            <div class="settings-group">
                <label for="unitSelect">Temperature Unit:</label>
                <select id="unitSelect">
                    <option value="C">Celsius</option>
                    <option value="F">Fahrenheit</option>
                </select>
            </div>

            <div class="settings-group">
                <label for="decimalsSelect">Decimal Places:</label>
                <select id="decimalsSelect">
                    <option value="0">0</option>
                    <option value="1">1</option>
                    <option value="2">2</option>
                </select>
            </div>

            <button onclick="saveSettings()">Save</button>
        </div>
    </div>

    <h1>Weller Station Control Panel</h1>
    
    <div class="station-info">
        <h2>Station Information</h2>
        <div class="status-grid">
            <div class="info-item">
                <strong>Model:</strong> {{ station_info.model }}
            </div>
            <div class="info-item">
                <strong>Firmware:</strong> {{ station_info.firmware }}
            </div>
            <div class="info-item">
                <strong>Connection:</strong> 
                <span class="connection-{{ station_info.connection_status.lower() }}">
                    {{ station_info.connection_status }}
                </span>
            </div>
            <div class="info-item">
                <strong>Interface:</strong> {{ station_info.connection }}
            </div>
            <div class="info-item">
                <strong>Uptime:</strong> {{ station_info.uptime }}
            </div>
            <div class="info-item">
                <strong>Last Updated:</strong> 
                <span id="last_updated">{{ station_info.last_updated }}</span>
            </div>
        </div>
    </div>

    <div id="messages"></div>
    
    {% for channel in status %}
    <div class="channel">
        <h2>{{ channel.upper() }}</h2>
        <div class="temp-readout" data-temp="{{ status[channel]['temperature'] }}">
            Current: {{ status[channel]['temperature'] }}°C
        </div>
        
        <div class="stats">
            <div class="stat-item">
                <strong>Status:</strong> {{ status[channel]['status'] }}
            </div>
            <div class="stat-item">
                <strong>Tool:</strong> {{ status[channel]['tool'] }}
            </div>
            {% if stats[channel] %}
            <div class="stat-item">
                <strong>Min/Max:</strong> {{ "%.1f"|format(stats[channel]['min']) }}°C / {{ "%.1f"|format(stats[channel]['max']) }}°C
            </div>
            <div class="stat-item">
                <strong>Average:</strong> {{ "%.1f"|format(stats[channel]['avg']) }}°C
            </div>
            {% endif %}
            {% if presets[channel] %}
            <div class="stat-item">
                <strong>Preset 1:</strong> {{ "%.0f"|format(presets[channel]['preset1']) }}°C
            </div>
            <div class="stat-item">
                <strong>Preset 2:</strong> {{ "%.0f"|format(presets[channel]['preset2']) }}°C
            </div>
            {% endif %}
        </div>

        <div class="controls">
            <h3>Temperature Control</h3>
            <div class="temp-control">
                <div class="slider-container">
                    <input type="range" 
                           id="tempSlider{{loop.index}}" 
                           class="temp-slider"
                           min="{{ station_info.temp_limits.min }}" 
                           max="{{ station_info.temp_limits.max }}" 
                           step="1" 
                           value="200"
                           oninput="updateTempValue({{loop.index}}, this.value)">
                    <div id="tempSliderValue{{loop.index}}" class="temp-display" data-temp="200">200°C</div>
                </div>
                <button onclick="setTemp({{loop.index}})">Set</button>
            </div>

            <div class="preset-controls">
                <h3>Preset Controls</h3>
                <div class="preset-row">
                    <button onclick="setPreset({{loop.index}}, 1, sliderValue[{{loop.index}}])">Save Preset 1</button>
                    <button onclick="setPreset({{loop.index}}, 2, sliderValue[{{loop.index}}])">Save Preset 2</button>
                </div>
                <div class="preset-row">
                    <button onclick="activatePreset({{loop.index}}, 1)">Use Preset 1</button>
                    <button onclick="activatePreset({{loop.index}}, 2)">Use Preset 2</button>
                </div>
            </div>
            
            <h3>Mode Control</h3>
            <button onclick="setMode({{loop.index}}, 'ON')">ON</button>
            <button onclick="setMode({{loop.index}}, 'OFF')">OFF</button>
            <button onclick="setMode({{loop.index}}, 'STANDBY')">STANDBY</button>
        </div>
        <div class="tool-controls">
            <h3>Tool Controls</h3>
            <div class="fingerswitch-control">
                <label for="fingerswitchTime{{loop.index}}">Fingerswitch Time (s):</label>
                <input type="number" 
                       id="fingerswitchTime{{loop.index}}" 
                       min="1" 
                       max="9999" 
                       value="5">
                <button onclick="triggerFingerswitch({{loop.index}})">Activate Fingerswitch</button>
            </div>
            <div class="tool-info">
                <strong>Connected Tool:</strong> 
                <span id="toolInfo{{loop.index}}">{{ status[channel]['tool'] }}</span>
                <br>
                <strong>Max Temperature:</strong> 
                <span id="maxTemp{{loop.index}}">
                    {% set tool_info = get_tool_info(status[channel]['tool_type']) %}
                    {{ tool_info.max_temp }}°C
                </span>
            </div>
        </div>
        <div class="tool-info-extended">
            <h3>Tool Information</h3>
            <div id="toolInfo{{loop.index}}">
                <p><strong>Name:</strong> <span class="tool-name"></span></p>
                <p><strong>Power:</strong> <span class="tool-power"></span></p>
                <p><strong>Max Temperature:</strong> <span class="tool-max-temp"></span></p>
                <p><strong>Description:</strong> <span class="tool-description"></span></p>
            </div>
        </div>
        <div class="remote-controls">
            <h3>Remote Control</h3>
            <button onclick="setRemoteMode(0)">Disable Remote</button>
            <button onclick="setRemoteMode(1)">Enable Remote</button>
            <button onclick="setRemoteMode(2)">Enable with Lock</button>
        </div>
        <div class="chart" id="chart{{loop.index}}"></div>
    </div>
    {% endfor %}
</body>
</html>
'''

class StationStatus(IntEnum):
    OFF = 0
    ON = 1
    STANDBY = 2
    AUTOOFF = 3

class ConnectionType(IntEnum):
    FRONT = 1
    REAR = 2

class ToolType(IntEnum):
    NOTOOL = 0
    WXP120 = 1
    WXP200 = 2
    WXMP = 3
    WXMT = 4
    WXP65 = 5
    WXP80 = 6
    WXB200 = 7

    @classmethod
    def get_name(cls, value):
        try:
            return cls(value).name
        except ValueError:
            return "UNKNOWN"

class RemoteMode(IntEnum):
    DISABLED = 0
    ENABLED = 1
    ENABLED_WITH_LOCK = 2

class WellerError(Exception):
    """Custom exception for Weller station errors"""
    pass

def retry_on_error(retries=3, delay=1):
    """Decorator for retrying failed commands"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            for _ in range(retries):
                try:
                    return func(*args, **kwargs)
                except WellerError as e:
                    last_error = e
                    time.sleep(delay)
            raise last_error
        return wrapper
    return decorator

class WebConfig:
    def __init__(self, port=5000, username=None, password=None):
        self.port = port
        self.username = username
        self.password = password

# Lägg till ny hjälpklass för temperaturkonvertering
class TemperatureConverter:
    @staticmethod
    def to_internal(temp: float) -> int:
        """Convert temperature from °C to internal representation (1/10°C)"""
        return int(temp * 10)
    
    @staticmethod
    def from_internal(value: int) -> float:
        """Convert temperature from internal representation to °C"""
        return value / 10.0

# Lägg till efter existerande klasser
class ResponseParser:
    """Parser för Weller station-svar"""
    @staticmethod
    def parse_response(response: str, expected_prefix: str) -> Dict[str, Union[str, int, float]]:
        """Parse a response from the station with validation"""
        if not response or len(response) < 3:
            raise WellerError("Response too short")
            
        if not response.startswith(expected_prefix):
            raise WellerError(f"Expected prefix {expected_prefix}, got {response[:2]}")
            
        result = {
            'raw': response,
            'prefix': response[:2],
            'checksum': response[-1]
        }
        
        # Parse based on command type
        if expected_prefix in ['R1', 'S1', 'T1', 'U1']:  # Temperature commands
            result['value'] = float(response[2:6]) / 10.0
        elif expected_prefix == 'Q1':  # Status command
            result['ch1_status'] = int(response[2])
            result['ch2_status'] = int(response[3])
        elif expected_prefix == 'Y1':  # Tool type command
            result['ch1_tool'] = int(response[2])
            result['ch2_tool'] = int(response[9]) if len(response) >= 10 else None
            
        return result

class WellerStation:
    @staticmethod
    def list_available_ports():
        """List all available COM ports"""
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append({
                'port': port.device,
                'description': port.description,
                'manufacturer': port.manufacturer
            })
        return ports

    @staticmethod
    def find_weller_port():
        """Try to automatically find the Weller station port"""
        for port in serial.tools.list_ports.comports():
            # Look for common USB-Serial adapters or Weller in description
            if any(x in port.description.lower() for x in ['weller', 'usb', 'serial', 'uart', 'cp210x', 'ch340']):
                return port.device
        return None

    def __init__(self, port=None, baudrate=1200, log_file=None, max_history=1000, web_interface=False, web_config=None):
        """Initialize WellerStation with automatic port discovery"""
        if port is None:
            port = self.find_weller_port()
            if port is None:
                available_ports = self.list_available_ports()
                raise WellerError(
                    f"No Weller station found. Available ports:\n" +
                    "\n".join([f"{p['port']}: {p['description']}"] for p in available_ports)
                )
        
        try:
            self.ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=8,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=1
            )
        except serial.SerialException as e:
            available_ports = self.list_available_ports()
            raise WellerError(
                f"Failed to open port {port}. Error: {str(e)}\n"
                f"Available ports:\n" +
                "\n".join([f"{p['port']}: {p['description']}"] for p in available_ports)
            )

        self.status_map = {
            StationStatus.OFF: "OFF",
            StationStatus.ON: "ON",
            StationStatus.STANDBY: "STANDBY",
            StationStatus.AUTOOFF: "AUTO-OFF"
        }
        
        # Add logging setup
        self.logger = logging.getLogger('WellerStation')
        if log_file:
            handler = logging.FileHandler(log_file)
            handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
            self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

        self.temperature_history = {
            'channel1': deque(maxlen=max_history),
            'channel2': deque(maxlen=max_history)
        }
        self.last_status = None
        self.connection_type = None
        self.temp_limits = {'min': 50, 'max': 450}  # Default temperature limits in °C
        self.web_interface = web_interface
        self.web_config = web_config or WebConfig()
        self.start_time = datetime.now()
        if web_interface:
            self.start_web_interface()

    def calculate_checksum(self, command: str) -> str:
        """Enhanced checksum calculation with validation"""
        if not command:
            raise WellerError("Empty command")
            
        try:
            sum_ascii = sum(ord(c) for c in command)
            # Log detailed calculation
            self.logger.debug(f"Checksum calculation for '{command}':")
            self.logger.debug(f"ASCII values: {[ord(c) for c in command]}")
            self.logger.debug(f"Sum: {sum_ascii}")
            
            while sum_ascii > 255:
                sum_ascii -= 256
                self.logger.debug(f"Adjusted sum: {sum_ascii}")
                
            return chr(sum_ascii)
        except Exception as e:
            raise WellerError(f"Checksum calculation failed: {str(e)}")

    def verify_checksum(self, response: str) -> bool:
        """Enhanced checksum verification with detailed reporting"""
        if len(response) < 2:
            self.logger.error("Response too short for checksum verification")
            return False
            
        data = response[:-1]
        received_checksum = response[-1]
        calculated_checksum = self.calculate_checksum(data)
        
        if received_checksum != calculated_checksum:
            self.logger.error(
                f"Checksum mismatch:\n"
                f"Received: {ord(received_checksum)} ({received_checksum})\n"
                f"Calculated: {ord(calculated_checksum)} ({calculated_checksum})\n"
                f"Data: {[ord(c) for c in data]}"
            )
            return False
        return True

    @retry_on_error(retries=3)
    def send_command(self, command: Union[str, bytes], expect_response=True, cmd_type=None) -> Optional[str]:
        """Enhanced command sending with validation"""
        try:
            if isinstance(command, str):
                command = command.encode()
                
            self.logger.debug(f"Sending command: {command!r}")
            self.ser.write(command)
            
            if expect_response:
                response = self.ser.readline().decode().strip()
                if not response:
                    raise WellerError("No response received")
                    
                self.logger.debug(f"Raw response: {response!r}")
                
                if cmd_type and not WellerCommand.validate_response_length(cmd_type, response):
                    raise WellerError(f"Invalid response length for {cmd_type}")
                    
                if not self.verify_checksum(response):
                    self.logger.error(f"Checksum failed for response: {response!r}")
                    raise WellerError("Checksum validation failed")
                    
                return response
                
        except serial.SerialException as e:
            raise WellerError(f"Serial communication error: {e}")

    def enable_remote(self):
        self.send_command(b"remote1")
        
    def disable_remote(self):
        self.send_command(b"remote0", expect_response=False)
        
    def read_status(self):
        response = self.send_command(b"Q")
        if len(response) >= 7:
            status_ch1 = response[2]
            status_ch2 = response[3]
            return {
                'channel1': int(status_ch1),
                'channel2': int(status_ch2)
            }
        return None
        
    def read_temperature(self) -> Dict[str, float]:
        """Read temperature with enhanced error handling"""
        response = self.send_command(b"R", cmd_type='read_temperature')
        return WellerResponse.parse_temperature_response(response)
        
    def set_temperature(self, channel: int, temp: float) -> None:
        """Set temperature with enhanced validation"""
        command = WellerCommand.build_temp_command('s', channel, temp)
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)
        
    def set_status(self, ch1_status, ch2_status):
        command = f"q1{ch1_status}{ch2_status}00"
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)
        
    def read_tool_type(self):
        response = self.send_command(b"Y")
        tool_types = {
            '0': 'NOTOOL',
            '1': 'WXP120',
            '2': 'WXP200',
            '3': 'WXMP',
            '4': 'WXMT',
            '5': 'WXP65',
            '6': 'WXP80',
            '7': 'WXB200'
        }
        if len(response) >= 14:
            tool1 = tool_types.get(response[2], 'Unknown')
            tool2 = tool_types.get(response[9], 'Unknown')
            return {'channel1': tool1, 'channel2': tool2}
        return None

    def close(self):
        self.ser.close()

    def enable_remote_with_lock(self):
        """Enable remote control with front button lock"""
        return self.send_command(b"remote2")

    def read_unit_id(self):
        """Read the unit ID and return model information"""
        response = self.send_command(b"?")
        if len(response) >= 3:
            models = {
                '1': 'WX 1',
                '2': 'WX 2',
                '3': 'WX 2D',
                '4': 'WX 2A',
                '5': 'WX 1D',
                '6': 'WX 1A'
            }
            return models.get(response[2], 'Unknown')
        return None

    def read_set_temperature(self):
        """Read the set temperature for both channels"""
        response = self.send_command(b"S")
        if len(response) >= 14:
            temp1 = float(response[2:6]) / 10.0
            temp2 = float(response[9:13]) / 10.0
            return {'channel1': temp1, 'channel2': temp2}
        return None

    def read_preset_temperature1(self):
        """Read preset temperature 1 for both channels"""
        response = self.send_command(b"T")
        if len(response) >= 14:
            temp1 = float(response[2:6]) / 10.0
            temp2 = float(response[9:13]) / 10.0
            return {'channel1': temp1, 'channel2': temp2}
        return None

    def read_preset_temperature2(self):
        """Read preset temperature 2 for both channels"""
        response = self.send_command(b"U")
        if len(response) >= 14:
            temp1 = float(response[2:6]) / 10.0
            temp2 = float(response[9:13]) / 10.0
            return {'channel1': temp1, 'channel2': temp2}
        return None

    def set_preset_temperature1(self, channel, temp):
        """Set preset temperature 1 for specified channel"""
        temp_str = f"{int(temp*10):04d}"
        command = f"t{channel}{temp_str}"
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)

    def set_preset_temperature2(self, channel, temp):
        """Set preset temperature 2 for specified channel"""
        temp_str = f"{int(temp*10):04d}"
        command = f"u{channel}{temp_str}"
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)

    def read_firmware_version(self):
        """Read the firmware version"""
        response = self.send_command(b"V")
        if len(response) >= 6:
            return response[2:6]
        return None

    def verify_firmware_compatibility(self):
        """Check if firmware version is compatible (>= 0.64)"""
        version = self.read_firmware_version()
        if version:
            try:
                version_num = float(version) / 100  # Convert format like "0064" to 0.64
                if version_num < 0.64:
                    self.logger.warning(f"Firmware version {version_num} might not support all features")
                return version_num >= 0.64
            except ValueError:
                return False
        return False

    def log_temperature_data(self):
        """Log temperature data to file if logging is enabled"""
        temps = self.read_temperature()
        if temps:
            self.logger.info(f"Temperature data: CH1={temps['channel1']}°C, CH2={temps['channel2']}°C")

    def fingerswitch_action(self, channel, seconds):
        """Trigger fingerswitch action for specified channel"""
        seconds_str = f"{int(seconds):04d}"
        command = f"x{channel}{seconds_str}"
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)

    def get_status_string(self, status_code):
        """Convert status code to readable string"""
        return self.status_map.get(StationStatus(int(status_code)), "UNKNOWN")

    def read_all_status(self):
        """Read comprehensive status of the station"""
        status = self.read_status()
        temps = self.read_temperature()
        tools = self.read_tool_type()
        
        if all([status, temps, tools]):
            return {
                'channel1': {
                    'status': self.get_status_string(status['channel1']),
                    'temperature': temps['channel1'],
                    'tool': tools['channel1']
                },
                'channel2': {
                    'status': self.get_status_string(status['channel2']),
                    'temperature': temps['channel2'],
                    'tool': tools['channel2']
                }
            }
        return None

    def set_channel_mode(self, channel, mode):
        """Set channel mode (ON/OFF/STANDBY/AUTOOFF)"""
        if not isinstance(mode, StationStatus):
            raise ValueError("Mode must be a StationStatus enum value")
        
        current_status = self.read_status()
        if current_status:
            if channel == 1:
                self.set_status(mode.value, current_status['channel2'])
            else:
                self.set_status(current_status['channel1'], mode.value)

    def monitor_status(self, interval=1.0):
        """Monitor station status continuously"""
        try:
            while True:
                status = self.read_all_status()
                if status:
                    print("\033[2J\033[H")  # Clear screen
                    print("=== Weller Station Status ===")
                    for channel in ['channel1', 'channel2']:
                        print(f"\n{channel.upper()}:")
                        print(f"Status: {status[channel]['status']}")
                        print(f"Temperature: {status[channel]['temperature']}°C")
                        print(f"Tool: {status[channel]['tool']}")
                    print("\nPress Ctrl+C to stop monitoring")
                time.sleep(interval)
        except KeyboardInterrupt:
            print("\nMonitoring stopped")

    def enhanced_monitor(self, interval=1.0, log_data=True):
        """Enhanced monitoring with additional features"""
        try:
            print("Initializing enhanced monitoring...")
            
            # Try legacy mode if modern fails
            try:
                self.enable_remote()
            except WellerError:
                print("Trying legacy remote mode...")
                self.enable_remote_legacy()
            
            self.detect_connection_type()
            
            while True:
                status = self.read_all_status()
                self.update_history()
                
                if status:
                    print("\033[2J\033[H")  # Clear screen
                    print(f"=== Weller Station Enhanced Status ({self.connection_type.name} Connection) ===")
                    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                    
                    for channel in ['channel1', 'channel2']:
                        print(f"\n{channel.upper()}:")
                        print(f"Status: {status[channel]['status']}")
                        print(f"Current Temp: {status[channel]['temperature']}°C")
                        
                        # Add temperature statistics
                        stats = self.get_temperature_statistics(channel)
                        if stats:
                            print(f"Min/Max/Avg: {stats['min']:.1f}°C / {stats['max']:.1f}°C / {stats['avg']:.1f}°C")
                        
                        # Show presets and tool info
                        presets = self.read_preset_temperature1()
                        if presets:
                            print(f"Preset 1: {presets[channel]}°C")
                        presets = self.read_preset_temperature2()
                        if presets:
                            print(f"Preset 2: {presets[channel]}°C")
                        print(f"Tool: {status[channel]['tool']}")
                    
                    print(f"\nTemperature Limits: {self.temp_limits['min']}°C - {self.temp_limits['max']}°C")
                    print("\nPress Ctrl+C to stop monitoring")
                
                if log_data:
                    self.log_temperature_data()
                    
                time.sleep(interval)
                
        except KeyboardInterrupt:
            print("\nMonitoring stopped")
        except WellerError as e:
            print(f"\nError: {e}")

    def set_temperature_limits(self, min_temp: int, max_temp: int) -> None:
        """Set safety temperature limits"""
        if not (0 <= min_temp < max_temp <= 550):
            raise ValueError("Invalid temperature limits")
        self.temp_limits = {'min': min_temp, 'max': max_temp}

    def detect_connection_type(self) -> Optional[ConnectionType]:
        """Detect whether front or rear connection is used"""
        response = self.send_command(b"remote1")
        if "FRONT" in response:
            self.connection_type = ConnectionType.FRONT
        elif "REAR" in response:
            self.connection_type = ConnectionType.REAR
        return self.connection_type

    def save_temperature_profile(self, name: str) -> None:
        """Save current temperature settings as a profile"""
        profile = {
            'set_temps': self.read_set_temperature(),
            'preset1': self.read_preset_temperature1(),
            'preset2': self.read_preset_temperature2(),
            'timestamp': datetime.now().isoformat()
        }
        
        try:
            with open(f"{name}_profile.json", 'w') as f:
                json.dump(profile, f, indent=2)
        except Exception as e:
            self.logger.error(f"Failed to save profile: {e}")

    def load_temperature_profile(self, name: str) -> bool:
        """Load and apply a saved temperature profile"""
        try:
            with open(f"{name}_profile.json", 'r') as f:
                profile = json.load(f)
                
            # Apply temperatures with safety checks
            for channel in [1, 2]:
                if 'set_temps' in profile:
                    temp = profile['set_temps'][f'channel{channel}']
                    if self.temp_limits['min'] <= temp <= self.temp_limits['max']:
                        self.set_temperature(channel, temp)
                
            return True
        except Exception as e:
            self.logger.error(f"Failed to load profile: {e}")
            return False

    def update_history(self) -> None:
        """Update temperature history"""
        temps = self.read_temperature()
        if temps:
            timestamp = datetime.now()
            for channel in ['channel1', 'channel2']:
                self.temperature_history[channel].append({
                    'timestamp': timestamp,
                    'temperature': temps[channel]
                })

    def get_temperature_statistics(self, channel: str) -> Dict:
        """Get temperature statistics for a channel"""
        if not self.temperature_history[channel]:
            return {}
            
        temps = [entry['temperature'] for entry in self.temperature_history[channel]]
        return {
            'min': min(temps),
            'max': max(temps),
            'avg': sum(temps) / len(temps),
            'current': temps[-1]
        }

    def enable_remote_legacy(self):
        """Enable remote control for legacy firmware (<0.52)"""
        self.send_command(b"REMOTE")
        return self.read_unit_id()

    def export_temperature_log(self, filename: str) -> None:
        """Export temperature history to CSV file"""
        try:
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['Timestamp', 'Channel', 'Temperature'])
                for channel in ['channel1', 'channel2']:
                    for entry in self.temperature_history[channel]:
                        writer.writerow([
                            entry['timestamp'].isoformat(),
                            channel,
                            entry['temperature']
                        ])
        except Exception as e:
            self.logger.error(f"Failed to export temperature log: {e}")

    def get_uptime(self):
        """Get station uptime"""
        delta = datetime.now() - self.start_time
        hours = delta.total_seconds() / 3600
        return f"{hours:.1f} hours"

    def start_web_interface(self):
        """Start enhanced web interface with full control"""
        app = Flask(__name__)
        
        if self.web_config.username and self.web_config.password:
            app.config['BASIC_AUTH_USERNAME'] = self.web_config.username
            app.config['BASIC_AUTH_PASSWORD'] = self.web_config.password
            app.config['BASIC_AUTH_FORCE'] = True
            basic_auth = BasicAuth(app)
        
        @app.route('/')
        def home():
            status = self.read_all_status()
            station_info = {
                'model': self.read_unit_id(),
                'firmware': self.read_firmware_version(),
                'connection': self.connection_type.name if self.connection_type else 'Unknown',
                'temp_limits': self.temp_limits,
                'uptime': self.get_uptime(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'connection_status': 'Connected' if status else 'Disconnected'
            }
            return render_template_string(html_template, 
            status=status,
            stats={
                'channel1': self.get_temperature_statistics('channel1'),
                'channel2': self.get_temperature_statistics('channel2')
            },
            presets=self.get_preset_temperatures(),
            station_info=station_info,
            get_tool_info=get_tool_info  # Lägg till denna rad
        )

        @app.route('/api/set_temperature/<int:channel>/<float:temp>', methods=['OPTIONS'])
        def options_handler():
            return '', 200

        @app.route('/api/set_temperature/<int:channel>/<float:temp>', methods=['POST'])
        def api_set_temperature(channel, temp):
            try:
                # Validate temperature range
                if not (self.temp_limits['min'] <= temp <= self.temp_limits['max']):
                    raise ValueError(f"Temperature must be between {self.temp_limits['min']} and {self.temp_limits['max']}°C")
                
                self.set_temperature(channel, temp)
                return jsonify({
                    'success': True,
                    'message': f'Temperature set to {temp}°C',
                    'temperature': temp,
                    'channel': channel
                })
            except Exception as e:
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400

        @app.route('/api/set_mode/<int:channel>/<string:mode>', methods=['POST'])
        def api_set_mode(channel, mode):
            try:
                mode_map = {'ON': StationStatus.ON, 'OFF': StationStatus.OFF, 
                           'STANDBY': StationStatus.STANDBY, 'AUTOOFF': StationStatus.AUTOOFF}
                self.set_channel_mode(channel, mode_map[mode])
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'error': str(e)}), 400

        @app.route('/api/status')
        def api_status():
            status = self.read_all_status()
            temps = self.read_temperature()
            stats = {
                'channel1': self.get_temperature_statistics('channel1'),
                'channel2': self.get_temperature_statistics('channel2')
            }
            return jsonify({
                'status': status,
                'temperatures': temps,
                'statistics': stats,
                'timestamp': datetime.now().isoformat()
            })

        @app.route('/api/temperature_history/<channel>')
        def api_temperature_history(channel):
            history = self.temperature_history[f'channel{channel}']
            return jsonify({
                'temperatures': [entry['temperature'] for entry in history],
                'timestamps': [entry['timestamp'].isoformat() for entry in history]
            })

        @app.route('/api/fingerswitch/<int:channel>/<int:seconds>', methods=['POST'])
        def trigger_fingerswitch(channel, seconds):
            try:
                station.fingerswitch_action(channel, seconds)
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/remote_mode/<int:mode>', methods=['POST'])
        def set_remote_mode(mode):
            try:
                station.set_remote_mode(RemoteMode(mode))
                return jsonify({'success': True, 'mode': mode})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/tool_info/<int:channel>')
        def get_tool_info(channel):
            try:
                info = station.get_detailed_tool_info(channel)
                return jsonify({'success': True, 'info': info})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/connection_details')
        def get_connection_details():
            try:
                details = station.get_connection_details()
                return jsonify({'success': True, 'details': details})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        def run_flask():
            app.run(port=self.web_config.port, host='0.0.0.0')

        threading.Thread(target=run_flask, daemon=True).start()

    def get_preset_temperatures(self):
        """Helper method to get all preset temperatures"""
        preset1 = self.read_preset_temperature1() or {'channel1': None, 'channel2': None}
        preset2 = self.read_preset_temperature2() or {'channel1': None, 'channel2': None}
        return {
            'channel1': {
                'preset1': preset1['channel1'],
                'preset2': preset2['channel1']
            },
            'channel2': {
                'preset1': preset1['channel2'],
                'preset2': preset2['channel2']
            }
        }

    def set_remote_mode(self, mode: RemoteMode) -> None:
        """Set remote control mode"""
        command = f"remote{mode.value}"
        response = self.send_command(command.encode())
        if mode != RemoteMode.DISABLED:
            # Verify response contains unit ID
            if not response or not response.startswith('?1'):
                raise WellerError("Invalid response for remote mode setting")
        self.remote_mode = mode

    def get_detailed_tool_info(self, channel: int) -> dict:
        """Get detailed information about connected tool"""
        tool_info = {
            ToolType.WXP120: {
                'name': 'WXP 120',
                'max_temp': 450,
                'power': '120W',
                'description': 'High-power soldering iron'
            },
            ToolType.WXP200: {
                'name': 'WXP 200',
                'max_temp': 450,
                'power': '200W',
                'description': 'High-power soldering iron'
            },
            ToolType.WXMP: {
                'name': 'WXMP',
                'max_temp': 450,
                'power': '40W',
                'description': 'Micro soldering iron'
            },
            ToolType.WXMT: {
                'name': 'WXMT',
                'max_temp': 450,
                'power': '120W',
                'description': 'Desoldering tweezers'
            },
            ToolType.WXP65: {
                'name': 'WXP 65',
                'max_temp': 450,
                'power': '65W',
                'description': 'Standard soldering iron'
            },
            ToolType.WXP80: {
                'name': 'WXP 80',
                'max_temp': 450,
                'power': '80W',
                'description': 'Standard soldering iron'
            },
            ToolType.WXB200: {
                'name': 'WXB 200',
                'max_temp': 450,
                'power': '200W',
                'description': 'Bath'
            }
        }
        
        tool_type = self.get_tool_type(channel)
        return tool_info.get(tool_type, {
            'name': 'Unknown/No Tool',
            'max_temp': 450,
            'power': 'N/A',
            'description': 'Unknown tool or no tool connected'
        })

    def get_connection_details(self) -> Dict[str, str]:
        """Get detailed connection information"""
        details = {
            'type': self.connection_type.name if self.connection_type else 'Unknown',
            'mode': self.remote_mode.name if hasattr(self, 'remote_mode') else 'Unknown',
            'button_lock': 'Enabled' if hasattr(self, 'button_lock') and self.button_lock else 'Disabled',
            'firmware_version': self.read_firmware_version() or 'Unknown'
        }
        return details

class DemoWellerStation(WellerStation):
    """Simulated Weller station for demo purposes"""
    def __init__(self, *args, **kwargs):
        self.status_map = {
            StationStatus.OFF: "OFF",
            StationStatus.ON: "ON",
            StationStatus.STANDBY: "STANDBY",
            StationStatus.AUTOOFF: "AUTO-OFF"
        }
        self.logger = logging.getLogger('DemoWellerStation')
        self.temperature_history = {
            'channel1': deque(maxlen=1000),
            'channel2': deque(maxlen=1000)
        }
        self.connection_type = ConnectionType.FRONT
        self.temp_limits = {'min': 50, 'max': 450}
        self.current_temps = {'channel1': 250, 'channel2': 200}
        self.set_temps = {'channel1': 250, 'channel2': 200}
        self.current_status = {'channel1': StationStatus.ON, 'channel2': StationStatus.STANDBY}
        self.tools = {'channel1': 'WXP120', 'channel2': 'WXMP'}
        self.start_time = datetime.now()
        self.web_config = kwargs.get('web_config') or WebConfig()
        self.last_update = datetime.now()
        self.demo_update_interval = timedelta(seconds=1)
        self.max_history_points = 100  # Begränsa antalet datapunkter i grafen
        self.start_demo_updates()
        self.last_temps = {'channel1': None, 'channel2': None}
        self.presets = {
            'channel1': {'preset1': 200, 'preset2': 300},
            'channel2': {'preset1': 200, 'preset2': 300}
        }
        self.remote_mode = RemoteMode.ENABLED
        self.button_lock = False

    def start_demo_updates(self):
        """Start a background thread to update demo values"""
        def update_loop():
            while True:
                now = datetime.now()
                if now - self.last_update >= self.demo_update_interval:
                    self.update_demo_temperatures()
                    self.last_update = now
                time.sleep(0.1)

        thread = threading.Thread(target=update_loop, daemon=True)
        thread.start()

    def update_demo_temperatures(self):
        """Update demo temperatures with realistic variations and maintain history"""
        temps = self.read_temperature()
        current_time = datetime.now()
        
        for channel in ['channel1', 'channel2']:
            # Trim history if needed
            while len(self.temperature_history[channel]) >= self.max_history_points:
                self.temperature_history[channel].popleft()
            
            # Add new temperature data
            self.temperature_history[channel].append({
                'timestamp': current_time,
                'temperature': temps[channel]
            })

    def send_command(self, command, expect_response=True):
        """Simulate command sending"""
        return "OK"

    def read_temperature(self) -> Dict[str, float]:
        """Simulate temperature readings with realistic variations"""
        now = datetime.now()
        for channel in ['channel1', 'channel2']:
            target_temp = self.set_temps[channel]
            current_temp = self.current_temps[channel]
            
            if self.current_status[channel] == StationStatus.ON:
                if self.last_temps[channel] is None:
                    self.last_temps[channel] = current_temp
                
                # Mer realistisk temperaturvariation
                noise = random.uniform(-0.5, 0.5)
                if abs(current_temp - target_temp) > 1:
                    # Gradvis närma sig måltemperaturen
                    direction = 1 if target_temp > current_temp else -1
                    delta = min(2.0, abs(target_temp - current_temp)) * direction
                    new_temp = self.last_temps[channel] + delta + noise
                else:
                    # Små variationer runt måltemperaturen
                    new_temp = target_temp + noise
                
                self.current_temps[channel] = new_temp
                self.last_temps[channel] = new_temp
                
            elif self.current_status[channel] == StationStatus.STANDBY:
                # Gradvis nedkylning till standby-temperatur (150°C)
                if current_temp > 150:
                    self.current_temps[channel] = max(150, current_temp - 1)
            elif self.current_status[channel] == StationStatus.OFF:
                # Snabbare nedkylning när avstängd
                self.current_temps[channel] = max(25, current_temp - 2)
        
        return self.current_temps.copy()

    def read_status(self):
        return {
            'channel1': self.current_status['channel1'].value,
            'channel2': self.current_status['channel2'].value
        }

    def set_temperature(self, channel: int, temp: float) -> None:
        """Set temperature with proper conversion in demo mode"""
        try:
            internal_temp = TemperatureConverter.to_internal(temp)
            if not (self.temp_limits['min'] <= temp <= self.temp_limits['max']):
                raise ValueError(
                    f"Temperature must be between {self.temp_limits['min']} "
                    f"and {self.temp_limits['max']}°C"
                )
            
            channel_key = f'channel{channel}'
            self.set_temps[channel_key] = temp
            self.current_temps[channel_key] = temp
            
            # Uppdatera temperaturhistorik
            self.temperature_history[channel_key].append({
                'timestamp': datetime.now(),
                'temperature': temp,
                'internal_value': internal_temp
            })
            
            return True
        except ValueError as e:
            raise ValueError(f"Invalid temperature value: {str(e)}")

    def set_status(self, ch1_status, ch2_status):
        self.current_status['channel1'] = StationStatus(ch1_status)
        self.current_status['channel2'] = StationStatus(ch2_status)

    def read_tool_type(self):
        return self.tools.copy()

    def read_firmware_version(self):
        return "0064"  # Demo firmware version

    def read_unit_id(self):
        return "WX 2 (Demo)"

    def read_all_status(self):
        """Read comprehensive status including temperature history"""
        temps = self.read_temperature()
        status = self.read_status()
        
        return {
            'channel1': {
                'status': self.get_status_string(self.current_status['channel1']),
                'temperature': temps['channel1'],
                'tool': self.tools['channel1']
            },
            'channel2': {
                'status': self.get_status_string(self.current_status['channel2']),
                'temperature': temps['channel2'],
                'tool': self.tools['channel2']
            }
        }

    def start_web_interface(self):
        app = Flask(__name__)
        
        @app.after_request
        def after_request(response):
            headers = {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET, POST, PUT, DELETE, OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type, Authorization',
                'Access-Control-Max-Age': '3600'
            }
            for key, value in headers.items():
                response.headers.add(key, value)
            return response

        @app.route('/')
        def home():
            try:
                status = self.read_all_status()
                station_info = {
                    'model': self.read_unit_id(),
                    'firmware': self.read_firmware_version(),
                    'connection': self.connection_type.name if self.connection_type else 'Unknown',
                    'temp_limits': self.temp_limits,
                    'uptime': self.get_uptime(),
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'connection_status': 'Connected' if status else 'Disconnected'
                }
                return render_template_string(html_template,
                    status=status,
                    stats={
                        'channel1': self.get_temperature_statistics('channel1'),
                        'channel2': self.get_temperature_statistics('channel2')
                    },
                    presets=self.get_preset_temperatures(),
                    station_info=station_info,
                    get_tool_info=get_tool_info  # Lägg till denna rad
                )
            except Exception as e:
                app.logger.error(f"Error in home route: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f"Error loading interface: {str(e)}"
                }), 500

        @app.route('/api/set_temperature/<int:channel>/<float:temp>', methods=['POST', 'OPTIONS'])
        def set_temperature_handler(channel, temp):
            if request.method == 'OPTIONS':
                return '', 204

            try:
                if channel not in [1, 2]:
                    return jsonify({
                        'success': False,
                        'error': "Invalid channel"
                    }), 400

                if not (self.temp_limits['min'] <= temp <= self.temp_limits['max']):
                    return jsonify({
                        'success': False,
                        'error': f"Temperature must be between {self.temp_limits['min']} and {self.temp_limits['max']}°C"
                    }), 400

                self.set_temperature(channel, temp)
                return jsonify({
                    'success': True,
                    'temperature': temp,
                    'channel': channel,
                    'message': f'Temperature set to {temp}°C'
                })
            except Exception as e:
                app.logger.error(f"Temperature setting error: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': str(e)
                }), 400

        @app.route('/api/set_mode/<int:channel>/<string:mode>', methods=['POST', 'OPTIONS'])
        def set_mode_handler(channel, mode):
            if request.method == 'OPTIONS':
                return '', 204

            try:
                mode_map = {'ON': StationStatus.ON, 'OFF': StationStatus.OFF, 
                           'STANDBY': StationStatus.STANDBY, 'AUTOOFF': StationStatus.AUTOOFF}
                if mode not in mode_map:
                    return jsonify({'success': False, 'error': f'Invalid mode: {mode}'}), 400
                
                self.set_channel_mode(channel, mode_map[mode])
                return jsonify({'success': True, 'mode': mode})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/status')
        def api_status():
            try:
                status = self.read_all_status()
                temps = self.read_temperature()
                history_data = {'channel1': [], 'channel2': []}
                for ch in ['channel1', 'channel2']:
                    history_data[ch] = [{
                        'temperature': entry['temperature'],
                        'time': entry['timestamp'].strftime('%H:%M:%S')
                    } for entry in self.temperature_history[ch]]
                return jsonify({
                    'success': True,
                    'status': status,
                    'temperatures': temps,
                    'statistics': {
                        'channel1': self.get_temperature_statistics('channel1'),
                        'channel2': self.get_temperature_statistics('channel2')
                    },
                    'temperature_history': history_data,
                    'timestamp': datetime.now().isoformat()
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/temperature_history/<channel>')
        def api_temperature_history(channel):
            try:
                history = self.temperature_history[f'channel{channel}']
                return jsonify({
                    'success': True,
                    'temperatures': [entry['temperature'] for entry in history],
                    'timestamps': [entry['timestamp'].isoformat() for entry in history]
                })
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/set_preset/<int:channel>/<int:presetNum>/<float:temp>', methods=['POST'])
        def set_preset(channel, presetNum, temp):
            channel_key = f'channel{channel}'
            if channel_key in self.presets:
                if presetNum == 1:
                    self.presets[channel_key]['preset1'] = temp
                else:
                    self.presets[channel_key]['preset2'] = temp
            return jsonify({'success': True, 'presetNum': presetNum, 'temperature': temp})

        @app.route('/api/activate_preset/<int:channel>/<int:presetNum>', methods=['POST'])
        def activate_preset(channel, presetNum):
            channel_key = f'channel{channel}'
            if channel_key in self.presets:
                if presetNum == 1:
                    self.set_temperature(channel, self.presets[channel_key]['preset1'])
                else:
                    self.set_temperature(channel, self.presets[channel_key]['preset2'])
            return jsonify({'success': True, 'presetNum': presetNum})

        @app.route('/api/fingerswitch/<int:channel>/<int:seconds>', methods=['POST'])
        def trigger_fingerswitch(channel, seconds):
            try:
                station.fingerswitch_action(channel, seconds)
                return jsonify({'success': True})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/remote_mode/<int:mode>', methods=['POST'])
        def set_remote_mode(mode):
            try:
                station.set_remote_mode(RemoteMode(mode))
                return jsonify({'success': True, 'mode': mode})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/tool_info/<int:channel>')
        def get_tool_info(channel):
            try:
                info = station.get_detailed_tool_info(channel)
                return jsonify({'success': True, 'info': info})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        @app.route('/api/connection_details')
        def get_connection_details():
            try:
                details = station.get_connection_details()
                return jsonify({'success': True, 'details': details})
            except Exception as e:
                return jsonify({'success': False, 'error': str(e)}), 400

        def run_flask():
            app.run(port=self.web_config.port, host='0.0.0.0', threaded=True)

        thread = threading.Thread(target=run_flask, daemon=True)
        thread.start()
        time.sleep(1)

    def get_preset_temperatures(self):
        """Helper method to get all preset temperatures"""
        return {
            'channel1': {
                'preset1': self.presets['channel1']['preset1'],
                'preset2': self.presets['channel1']['preset2']
            },
            'channel2': {
                'preset1': self.presets['channel2']['preset1'],
                'preset2': self.presets['channel2']['preset2']
            }
        }

    def read_preset_temperature1(self):
        """Simulated read of preset temperature 1"""
        return {
            'channel1': self.presets['channel1']['preset1'],
            'channel2': self.presets['channel2']['preset1']
        }

    def read_preset_temperature2(self):
        """Simulated read of preset temperature 2"""
        return {
            'channel1': self.presets['channel1']['preset2'],
            'channel2': self.presets['channel2']['preset2']
        }

    def set_preset_temperature1(self, channel, temp):
        """Set preset temperature 1"""
        channel_key = f'channel{channel}'
        self.presets[channel_key]['preset1'] = temp

    def set_preset_temperature2(self, channel, temp):
        """Set preset temperature 2"""
        channel_key = f'channel{channel}'
        self.presets[channel_key]['preset2'] = temp

    def set_remote_mode(self, mode: RemoteMode) -> None:
        """Simulate remote mode setting"""
        self.remote_mode = mode
        self.button_lock = (mode == RemoteMode.ENABLED_WITH_LOCK)

# ...rest of DemoWellerStation methods...

# ...rest of existing code...

def show_menu():
    """Display the main menu"""
    print("\n=== Weller Station Control ===")
    print("1. Start Monitor Mode")
    print("2. Start Enhanced Monitor Mode")
    print("3. Set Temperature")
    print("4. Set Channel Mode (ON/OFF/STANDBY)")
    print("5. Save Temperature Profile")
    print("6. Load Temperature Profile")
    print("7. Configure Web Interface")
    print("8. Start Web Interface")
    print("9. Export Temperature Log")
    print("10. Exit")
    return input("Select option (1-10): ")

def handle_set_temperature(station):
    """Handle temperature setting menu"""
    channel = input("Enter channel (1/2): ")
    if channel not in ['1', '2']:
        print("Invalid channel")
        return
    
    try:
        temp = float(input("Enter temperature (50-450°C): "))
        station.set_temperature(int(channel), temp)
        print(f"Temperature for channel {channel} set to {temp}°C")
    except ValueError:
        print("Invalid temperature value")

def handle_set_mode(station):
    """Handle mode setting menu"""
    print("\nAvailable modes:")
    for mode in StationStatus:
        print(f"{mode.value}: {mode.name}")
    
    channel = input("Enter channel (1/2): ")
    if channel not in ['1', '2']:
        print("Invalid channel")
        return
    
    try:
        mode = int(input("Enter mode number: "))
        station.set_channel_mode(int(channel), StationStatus(mode))
        print(f"Channel {channel} mode set to {StationStatus(mode).name}")
    except ValueError:
        print("Invalid mode value")

def configure_web_interface():
    """Configure web interface settings"""
    print("\n=== Web Interface Configuration ===")
    port = input("Enter port number (default 5000): ") or "5000"
    use_auth = input("Enable authentication? (y/n): ").lower() == 'y'
    
    username = None
    password = None
    if use_auth:
        username = input("Enter username: ")
        password = input("Enter password: ")
    
    return WebConfig(int(port), username, password)

# Example usage:
if __name__ == "__main__":
    try:
        print("=== Weller Station Control ===")
        print("1. Connect to real station")
        print("2. Start demo mode")
        mode = input("Select mode (1/2): ")

        if mode == "1":
            # List available ports
            print("\nAvailable COM ports:")
            ports = WellerStation.list_available_ports()
            for port in ports:
                print(f"{port['port']}: {port['description']}")
            
            station = WellerStation(log_file="weller_station.log")
        else:
            print("\nStarting demo mode...")
            station = DemoWellerStation()

        # Enable remote control
        if isinstance(station, WellerStation):
            station.enable_remote()

        web_config = None

        while True:
            choice = show_menu()
            
            if choice == "1":
                station.monitor_status()
            elif choice == "2":
                station.enhanced_monitor()
            elif choice == "3":
                handle_set_temperature(station)
            elif choice == "4":
                handle_set_mode(station)
            elif choice == "5":
                name = input("Enter profile name: ")
                station.save_temperature_profile(name)
            elif choice == "6":
                name = input("Enter profile name: ")
                station.load_temperature_profile(name)
            elif choice == "7":
                web_config = configure_web_interface()
                station.web_config = web_config
            elif choice == "8":
                if web_config is None:
                    web_config = configure_web_interface()
                    station.web_config = web_config
                station.start_web_interface()
                print(f"Web interface started at http://localhost:{web_config.port}")
            elif choice == "9":
                filename = f"temp_log_{datetime.now().strftime('%Y%m%d_%H%M')}.csv"
                station.export_temperature_log(filename)
                print(f"Log exported to {filename}")
            elif choice == "10":
                break
            else:
                print("Invalid option")

    except WellerError as e:
        print(f"Error: {e}")
    except KeyboardInterrupt:
        print("\nProgram terminated by user")
    finally:
        try:
            if isinstance(station, WellerStation):
                station.disable_remote()
                station.close()
        except:
            pass

# Lägg till en ny funktion i det globala scopet (utanför klasserna)
def get_tool_info(tool_type):
    """Helper function for getting tool information in templates"""
    tool_info = {
        'NOTOOL': {'max_temp': 0},
        'WXP120': {'max_temp': 450},
        'WXP200': {'max_temp': 450},
        'WXMP': {'max_temp': 450},
        'WXMT': {'max_temp': 450},
        'WXP65': {'max_temp': 450},
        'WXP80': {'max_temp': 450},
        'WXB200': {'max_temp': 450}
    }
    return tool_info.get(str(tool_type), {'max_temp': 450})

# Uppdatera start_web_interface metoden i både WellerStation och DemoWellerStation
class WellerStation:
    # ...existing code...

    def start_web_interface(self):
        app = Flask(__name__)
        
        # ...existing code...
        
        @app.route('/')
        def home():
            status = self.read_all_status()
            station_info = {
                'model': self.read_unit_id(),
                'firmware': self.read_firmware_version(),
                'connection': self.connection_type.name if self.connection_type else 'Unknown',
                'temp_limits': self.temp_limits,
                'uptime': self.get_uptime(),
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'connection_status': 'Connected' if status else 'Disconnected'
            }
            return render_template_string(html_template, 
                status=status,
                stats={
                    'channel1': self.get_temperature_statistics('channel1'),
                    'channel2': self.get_temperature_statistics('channel2')
                },
                presets=self.get_preset_temperatures(),
                station_info=station_info,
                get_tool_info=get_tool_info  # Lägg till denna rad
            )

        # ...rest of existing code...

class DemoWellerStation(WellerStation):
    # ...existing code...

    def start_web_interface(self):
        app = Flask(__name__)
        
        # ...existing code...
        
        @app.route('/')
        def home():
            try:
                status = self.read_all_status()
                station_info = {
                    'model': self.read_unit_id(),
                    'firmware': self.read_firmware_version(),
                    'connection': self.connection_type.name if self.connection_type else 'Unknown',
                    'temp_limits': self.temp_limits,
                    'uptime': self.get_uptime(),
                    'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'connection_status': 'Connected' if status else 'Disconnected'
                }
                return render_template_string(html_template,
                    status=status,
                    stats={
                        'channel1': self.get_temperature_statistics('channel1'),
                        'channel2': self.get_temperature_statistics('channel2')
                    },
                    presets=self.get_preset_temperatures(),
                    station_info=station_info,
                    get_tool_info=get_tool_info  # Lägg till denna rad
                )
            except Exception as e:
                app.logger.error(f"Error in home route: {str(e)}")
                return jsonify({
                    'success': False,
                    'error': f"Error loading interface: {str(e)}"
                }), 500

        # ...rest of existing code...

# Add new command validation class
class WellerCommand:
    """Command validator and builder for Weller protocol"""
    COMMANDS = {
        'read_unit_id': {'cmd': '?', 'response_len': 7},
        'read_status': {'cmd': 'Q', 'response_len': 7},
        'read_temperature': {'cmd': 'R', 'response_len': 14},
        'read_set_temp': {'cmd': 'S', 'response_len': 14},
        'read_preset1': {'cmd': 'T', 'response_len': 14},
        'read_preset2': {'cmd': 'U', 'response_len': 14},
        'read_firmware': {'cmd': 'V', 'response_len': 7},
        'read_tool': {'cmd': 'Y', 'response_len': 14},
    }

    @staticmethod
    def validate_response_length(cmd_type: str, response: str) -> bool:
        """Validate response length for command type"""
        if cmd_type not in WellerCommand.COMMANDS:
            raise WellerError(f"Unknown command type: {cmd_type}")
        expected_len = WellerCommand.COMMANDS[cmd_type]['response_len']
        return len(response) >= expected_len

    @staticmethod
    def build_temp_command(cmd: str, channel: int, temp: float) -> str:
        """Build temperature related command with validation"""
        if cmd not in ['s', 't', 'u']:
            raise WellerError(f"Invalid temperature command: {cmd}")
        if not (1 <= channel <= 2):
            raise WellerError(f"Invalid channel: {channel}")
            
        temp_int = int(temp * 10)  # Convert to 1/10°C
        if not (0 <= temp_int <= 9999):
            raise WellerError(f"Temperature out of range: {temp}")
            
        command = f"{cmd}{channel}{temp_int:04d}"
        return command

# Add new response parser class
class WellerResponse:
    """Enhanced response parser for Weller protocol"""
    @staticmethod
    def parse_temperature_response(response: str) -> Dict[str, float]:
        """Parse temperature response with validation"""
        if len(response) < 14:
            raise WellerError("Invalid temperature response length")
            
        try:
            temps = {
                'channel1': float(response[2:6]) / 10.0,
                'channel2': float(response[9:13]) / 10.0
            }
            return temps
        except ValueError as e:
            raise WellerError(f"Invalid temperature format: {e}")

    @staticmethod
    def parse_tool_response(response: str) -> Dict[str, str]:
        """Parse tool type response with validation"""
        if len(response) < 14:
            raise WellerError("Invalid tool response length")
            
        try:
            tools = {
                'channel1': int(response[2]),
                'channel2': int(response[9])
            }
            return tools
        except ValueError as e:
            raise WellerError(f"Invalid tool type format: {e}")

# Update WellerStation class with new validation methods
class WellerStation:
    # ...existing code...

    def send_command(self, command: Union[str, bytes], expect_response=True, cmd_type=None) -> Optional[str]:
        """Enhanced command sending with validation"""
        try:
            if isinstance(command, str):
                command = command.encode()
                
            self.logger.debug(f"Sending command: {command!r}")
            self.ser.write(command)
            
            if expect_response:
                response = self.ser.readline().decode().strip()
                if not response:
                    raise WellerError("No response received")
                    
                self.logger.debug(f"Raw response: {response!r}")
                
                if cmd_type and not WellerCommand.validate_response_length(cmd_type, response):
                    raise WellerError(f"Invalid response length for {cmd_type}")
                    
                if not self.verify_checksum(response):
                    self.logger.error(f"Checksum failed for response: {response!r}")
                    raise WellerError("Checksum validation failed")
                    
                return response
                
        except serial.SerialException as e:
            raise WellerError(f"Serial communication error: {e}")

    def set_temperature(self, channel: int, temp: float) -> None:
        """Set temperature with enhanced validation"""
        command = WellerCommand.build_temp_command('s', channel, temp)
        checksum = self.calculate_checksum(command)
        full_command = f"{command}{checksum}".encode()
        self.send_command(full_command, expect_response=False)

    def read_temperature(self) -> Dict[str, float]:
        """Read temperature with enhanced validation"""
        response = self.send_command(b"R", cmd_type='read_temperature')
        return WellerResponse.parse_temperature_response(response)

# ...rest of existing code...









