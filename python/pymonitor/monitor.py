"""A lightweight monitor for computer constants."""

import json
from enum import Enum
from pathlib import Path

from . import _rust_monitor


class ExporterType(str, Enum):
    """Supported backend exporter types."""

    MQTT = "mqtt"
    VICTORIAMETRICS = "victoriametrics"


class PyMonitor:
    """A lightweight monitor for computer constants.

    This class provides a Python interface to the Rust-based
    system monitoring tools. It should allow for background polling
    and pushing data directly to a database.
    """

    def __init__(self):
        """Initialize PyMonitor instance."""
        self._monitor_handle: _rust_monitor.MonitorHandle | None = None

    def __enter__(self) -> "PyMonitor":
        """Context manager entry point."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit point."""
        self.stop()

    def _get_endpoint(self, exporter_type: str) -> str:
        """Retrieves the endpoint URL for the given exporter type from the config.

        Args:
            exporter_type: type of exporter to use.
        """
        config_dir = Path.home() / ".pymonitor"
        config_file = config_dir / "config.json"

        # Create default config if it doesn't exist
        if not config_file.exists():
            config_dir.mkdir(parents=True, exist_ok=True)
            default_config = {
                "endpoints": {"mqtt": "localhost:1883", "victoriametrics": "http://localhost:8428/api/v1/import"}
            }
            with open(config_file, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            return default_config["endpoints"].get(exporter_type, "")

        with open(config_file, "r", encoding="utf-8") as f:
            try:
                config = json.load(f)
                return config.get("endpoints", {}).get(exporter_type, "")
            except json.JSONDecodeError:
                return ""

    def start(
        self,
        refresh_rate: int = 5,
        exporter_type: ExporterType = ExporterType.MQTT,
        priority: int = 5,
        duration: int | None = None,
    ) -> None:
        """Starts the background Rust monitoring thread.

        Args:
            refresh_rate: polling interval in seconds. Defaults to 5.
            exporter_type: type of exporter to use. Defaults to ExporterType.MQTT.
            priority: thread priority from 0 (highest) to 5 (lowest). Defaults to 5.
            duration: optional amount of time in seconds to run before automatically stopping.

        Raises:
            RuntimeError: if the monitor is already actively running.
            ValueError:
                * if no endpoint has been found for selected exporter type.
                * if priority is not in range(6).
            ImportError: if paho-mqtt has not been installed and exporter_type == ExporterType.MQTT.
            ConnectionError: if VictoriaMetrics database is not reachable and exporter_type == ExporterType.VICTORIAMETRICS.
        """
        if self._monitor_handle is not None:
            raise RuntimeError("Monitor is already running.")

        endpoint = self._get_endpoint(exporter_type.value)
        if not endpoint:
            raise ValueError(f"No endpoint found for exporter type: {exporter_type.value}")

        if not (0 <= priority <= 5):
            raise ValueError("Priority must be between 0 and 5.")

        if exporter_type == ExporterType.MQTT:
            try:
                import paho.mqtt.client as mqtt
            except ImportError as exc:
                raise ImportError(
                    "The paho-mqtt library is required for the MQTT exporter. "
                    "Install it with `pip install pymonitor[mqtt]`."
                ) from exc

            host, port_str = endpoint.split(":") if ":" in endpoint else (endpoint, "1883")
            port = int(port_str)
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
            try:
                client.connect(host, port, keepalive=5)
                client.disconnect()
            except Exception as e:
                raise ConnectionError(
                    f"Failed to connect to MQTT broker at {endpoint}. Ensure the MQTT broker is up and running."
                ) from e
        elif exporter_type == ExporterType.VICTORIAMETRICS:
            import urllib.request
            from urllib.parse import urlparse

            try:
                parsed_url = urlparse(endpoint)
                health_url = f"{parsed_url.scheme}://{parsed_url.netloc}/health"
                urllib.request.urlopen(health_url, timeout=5)
            except Exception as exc:
                raise ConnectionError(
                    f"Failed to connect to VictoriaMetrics at {endpoint}. Ensure the VictoriaMetrics database "
                    "is up and running."
                ) from exc

        # Start monitoring thread
        self._monitor_handle = _rust_monitor.start_monitoring(
            exporter_type.value, endpoint, refresh_rate, priority, duration
        )

    def stop(self) -> None:
        """Stops the background Rust monitoring thread."""
        if self._monitor_handle is not None:
            self._monitor_handle.stop()
            self._monitor_handle = None

    @staticmethod
    def get_process_metrics(name: str) -> list[tuple[int, float, float]]:
        """Retrieves resource usage for specific processes by name.

        Args:
            name: The exact name of the process.

        Returns:
            A list of tuples containing (pid, cpu_percent, ram_percent).
        """
        return _rust_monitor.get_process_metrics(name)

    @staticmethod
    def get_global_metrics() -> _rust_monitor.GlobalMetricsSnapshot:
        """Retrieves an immediate snapshot of the system's global resource usage.

        Returns:
            A GlobalMetricsSnapshot object containing detailed system metrics.
        """
        return _rust_monitor.get_global_metrics()
