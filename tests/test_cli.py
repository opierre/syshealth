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


from datetime import datetime
from unittest.mock import MagicMock

import pytest
from syshealth.cli import app
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture
def mock_monitor(mocker):
    """Fixture to mock the SysHealth instance used by the CLI."""
    monitor_mock = mocker.patch("syshealth.cli.MONITOR")
    return monitor_mock


def test_process_command(mock_monitor):
    """Test the process CLI command with an existing process name."""
    mock_monitor.get_process_metrics.return_value = [(1234, 5.2, 15.6)]
    result = runner.invoke(app, ["process", "--name", "testproc"])
    assert result.exit_code == 0
    assert "Process Metrics: testproc" in result.stdout
    assert "1234" in result.stdout
    assert "5.20%" in result.stdout
    assert "15.60%" in result.stdout


def test_process_command_not_found(mock_monitor):
    """Test the process CLI command when no matching processes are found."""
    mock_monitor.get_process_metrics.return_value = []
    result = runner.invoke(app, ["process", "--name", "unknown"])
    assert result.exit_code == 0
    assert "No processes found" in result.stdout
    assert "unknown" in result.stdout


def test_global_metrics_command(mock_monitor):
    """Test the global-metrics CLI command."""
    mock_metrics = MagicMock()
    mock_metrics.cpu_usage = 15.5
    mock_metrics.cpu_brand = "Fake CPU"
    mock_metrics.ram_percent = 45.2
    mock_metrics.max_ram = 32 * 1024**3
    mock_metrics.disk_percent = 50.0
    mock_metrics.available_disk = 12 * 1024**3
    mock_metrics.boot_time = 1600000000
    mock_metrics.os_name = "FakeOS"
    mock_metrics.os_version = "1.0"
    mock_metrics.kernel_version = "0.1"
    mock_metrics.hostname = "fakepc"
    mock_metrics.core_count_physical = 4
    mock_metrics.core_count_logical = 8
    mock_metrics.cpu_temperature = 55.5
    mock_metrics.swap_total = 10000
    mock_metrics.swap_used = 5000
    mock_metrics.network_rx_bytes = 1024**2
    mock_metrics.network_tx_bytes = 1024**2
    mock_metrics.network_interfaces = [("eth0", 1024**2, 1024**2, ["192.168.1.10"]), ("wlan0", 0, 0, [])]
    mock_metrics.per_core_usage = [10.0, 20.0, 30.0]
    mock_metrics.load_avg_1m = 1.0
    mock_metrics.load_avg_5m = 2.0
    mock_metrics.load_avg_15m = 3.0
    mock_metrics.users = [
        ("admin", ["Users", "Administrators"]),
        ("user1", ["Users"]),
        ("WDAGUtilityAccount", []),  # system account — should be filtered out
    ]
    mock_metrics.top_processes = [("python", 1234, 10.5), ("rust", 5678, 5.2)]

    mock_monitor.get_global_metrics.return_value = mock_metrics
    
    result = runner.invoke(app, ["global-metrics"])
    assert result.exit_code == 0
    assert "System Information" in result.stdout
    assert "System Instant Metrics" in result.stdout
    assert "Top CPU Consumers" in result.stdout
    assert "Network Instant Metrics" in result.stdout
    assert "System Users" in result.stdout
    assert "eth0" in result.stdout
    assert "192.168.1.10" in result.stdout
    assert "admin" in result.stdout
    assert "python" in result.stdout
    assert "15.50%" in result.stdout
    assert "Fake CPU" in result.stdout
    assert "45.20%" in result.stdout
    assert "32.00 GB" in result.stdout
    assert "12.00 GB" in result.stdout
    assert "50.00%" in result.stdout
    assert "FakeOS" in result.stdout
    assert "10% 20% 30%" in result.stdout
    expected_time = datetime.fromtimestamp(1600000000).strftime("%Y-%m-%d %H:%M:%S")
    assert expected_time in result.stdout
