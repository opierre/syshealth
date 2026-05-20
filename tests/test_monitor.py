# Copyright 2026 Pierre OLIVIER - pierreolivier.pro@gmail.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Integration tests for the PyMonitor Python wrapper and Rust backend."""

import json
import threading
import time

import paho.mqtt.client as mqtt_client
import pytest
from pymonitor.monitor import ExporterType, PyMonitor

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MQTT_HOST = "localhost"
MQTT_PORT = 1883
MQTT_TOPIC = "pymonitor/metrics"

# Fields expected in every published JSON payload
REQUIRED_METRIC_KEYS = {
    "cpu_usage",
    "cpu_brand",
    "ram_percent",
    "max_ram",
    "disk_percent",
    "available_disk",
    "boot_time",
    "os_name",
    "os_version",
    "kernel_version",
    "hostname",
    "core_count_logical",
    "swap_total",
    "swap_used",
    "network_rx_bytes",
    "network_tx_bytes",
    "network_interfaces",
    "per_core_usage",
    "load_avg_1m",
    "load_avg_5m",
    "load_avg_15m",
    "users",
    "top_processes",
}


# ---------------------------------------------------------------------------
# Existing metric tests
# ---------------------------------------------------------------------------


def test_get_process_metrics() -> None:
    """Test that the Rust backend returns process metrics."""
    monitor = PyMonitor()
    processes = monitor.get_process_metrics("python")
    assert isinstance(processes, list)
    for process in processes:
        assert isinstance(process, tuple)
        assert len(process) == 3


def test_global_metrics() -> None:
    """Test that the Rust backend successfully returns global metrics."""
    monitor = PyMonitor()
    metrics = monitor.get_global_metrics()

    assert isinstance(metrics.cpu_usage, float)
    assert isinstance(metrics.cpu_brand, str)
    assert isinstance(metrics.ram_percent, float)
    assert isinstance(metrics.max_ram, int)
    assert isinstance(metrics.disk_percent, float)
    assert isinstance(metrics.available_disk, int)
    assert isinstance(metrics.boot_time, int)
    assert metrics.ram_percent > 0
    assert metrics.max_ram > 0
    assert metrics.available_disk > 0
    assert metrics.boot_time > 0


# ---------------------------------------------------------------------------
# Thread lifecycle tests
# ---------------------------------------------------------------------------


def test_start_raises_if_already_running() -> None:
    """Starting a second time without stopping must raise RuntimeError."""
    monitor = PyMonitor()
    monitor.start(refresh_rate=60, exporter_type=ExporterType.MQTT, priority=5)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            monitor.start(refresh_rate=60, exporter_type=ExporterType.MQTT, priority=5)
    finally:
        monitor.stop()


def test_stop_is_idempotent() -> None:
    """Calling stop() multiple times must not raise."""
    monitor = PyMonitor()
    monitor.start(refresh_rate=60, exporter_type=ExporterType.MQTT, priority=5)
    monitor.stop()
    monitor.stop()  # second call must be silent


def test_invalid_priority_raises() -> None:
    """Priority outside [0, 5] must raise ValueError."""
    monitor = PyMonitor()
    with pytest.raises(ValueError, match="[Pp]riority"):
        monitor.start(refresh_rate=1, exporter_type=ExporterType.MQTT, priority=99)


# ---------------------------------------------------------------------------
# ExporterType Enum tests
# ---------------------------------------------------------------------------


def test_exporter_type_values() -> None:
    """ExporterType members must expose correct string values."""
    assert ExporterType.MQTT.value == "mqtt"
    assert ExporterType.VICTORIAMETRICS.value == "victoriametrics"


def test_exporter_type_is_str() -> None:
    """ExporterType inherits from str so it can be passed wherever a str is expected."""
    assert isinstance(ExporterType.MQTT, str)
    assert ExporterType.MQTT == "mqtt"


# ---------------------------------------------------------------------------
# MQTT subscriber integration test
# ---------------------------------------------------------------------------


class _MqttCollector:
    """Subscribes to MQTT_TOPIC and collects raw payloads in a list."""

    def __init__(self) -> None:
        self.payloads: list[bytes] = []
        self._ready = threading.Event()
        self._client = mqtt_client.Client(mqtt_client.CallbackAPIVersion.VERSION2)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:  # noqa: ANN001
        client.subscribe(MQTT_TOPIC)
        self._ready.set()

    def _on_message(self, client, userdata, msg) -> None:  # noqa: ANN001
        self.payloads.append(msg.payload)

    def start(self) -> None:
        """Connect and start the network loop in a background thread."""
        self._client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        self._client.loop_start()
        assert self._ready.wait(timeout=5), "MQTT subscriber did not connect within 5 s"

    def stop(self) -> None:
        """Disconnect and stop the network loop."""
        self._client.loop_stop()
        self._client.disconnect()


def test_mqtt_subscriber_receives_metrics() -> None:
    """Start PyMonitor, subscribe to MQTT, and assert at least one valid JSON payload arrives.

    The test uses the real Mosquitto broker running on localhost:1883.
    The monitoring thread is configured with a 1-second refresh rate so the
    payload arrives quickly.
    """
    collector = _MqttCollector()
    collector.start()

    monitor = PyMonitor()
    monitor.start(refresh_rate=1, exporter_type=ExporterType.MQTT, priority=5)

    try:
        # Wait up to 10 seconds for at least one message
        deadline = time.monotonic() + 10
        while not collector.payloads and time.monotonic() < deadline:
            time.sleep(0.2)

        assert collector.payloads, "No MQTT message received within 10 seconds"

        # Parse and validate the most recent payload
        raw = collector.payloads[-1]
        data = json.loads(raw)

        # All required top-level keys must be present
        missing = REQUIRED_METRIC_KEYS - data.keys()
        assert not missing, f"Missing metric keys in payload: {missing}"

        # Sanity-check a selection of values
        assert isinstance(data["cpu_usage"], float | int)
        assert 0.0 <= data["cpu_usage"] <= 100.0, "cpu_usage out of range"

        assert isinstance(data["ram_percent"], float | int)
        assert 0.0 <= data["ram_percent"] <= 100.0, "ram_percent out of range"

        assert isinstance(data["max_ram"], int)
        assert data["max_ram"] > 0, "max_ram must be positive"

        assert isinstance(data["cpu_brand"], str)
        assert data["cpu_brand"], "cpu_brand must not be empty"

        assert isinstance(data["per_core_usage"], list)
        assert all(0.0 <= u <= 100.0 for u in data["per_core_usage"]), "per_core_usage values out of range"

        assert isinstance(data["top_processes"], list)

        assert isinstance(data["network_interfaces"], list)

    finally:
        monitor.stop()
        collector.stop()


def test_context_manager() -> None:
    """Test that the Context Manager starts and stops the monitor."""
    with PyMonitor() as monitor:
        monitor.start(refresh_rate=60, exporter_type=ExporterType.MQTT, priority=5)
        assert monitor._monitor_handle is not None
    assert monitor._monitor_handle is None


def test_duration_argument() -> None:
    """Test that the duration argument automatically stops the thread without error."""
    monitor = PyMonitor()
    monitor.start(refresh_rate=1, exporter_type=ExporterType.MQTT, priority=5, duration=1)
    
    # Wait for slightly more than the duration
    time.sleep(1.5)
    
    # The rust thread should have exited without crashing.
    # Calling stop() to clean up the python handle explicitly.
    monitor.stop()
    assert monitor._monitor_handle is None
