# 🖥️🩺 PyMonitor

> A highly optimized, cross-platform system resource monitor with a Rust core and a beautiful Python CLI.

PyMonitor pushes the performance-critical work (polling loops, hardware inspection, network sampling) into compiled **Rust** code via [PyO3](https://pyo3.rs/), while keeping the Python surface clean, ergonomic, and easy to extend.

---

## ✨ Features

- ⚡ **Near-zero CPU footprint** — all heavy lifting runs in compiled Rust via `sysinfo`
- 🖥️ **Rich terminal UI** — colour-coded panels with adaptive side-by-side layout
- 🌐 **Cross-platform** — Windows and Linux supported
- 🔌 **Extensible** — adding a new Rust metric takes fewer than 10 lines
- 🧪 **Tested** — pytest integration tests with full mock coverage
- 📡 **Background Exporters** — Start a zero-overhead Rust background thread to continuously export metrics to MQTT or VictoriaMetrics
- 🎛️ **Configurable Priorities** — Control the exporter thread priority dynamically (from 0 to 5) so it never impacts system performance

---

## 🚀 Quickstart

### Prerequisites

| Tool | Purpose |
|------|---------|
| [`rustup`](https://rustup.rs/) | Rust compiler toolchain |
| [`uv`](https://docs.astral.sh/uv/) | Python project & venv manager |

### Install & Build

```bash
# 1. Create virtual environment and compile the Rust extension in one step
uv pip install -e .

# 2. (Optional) install dev dependencies for tests and linting
uv pip install -e ".[dev]"
```

`uv` detects `maturin` as the build backend in `pyproject.toml`, compiles `src/lib.rs`, and links the resulting shared library into your local Python environment automatically.

### Start Dependencies

If you plan to use the background exporter for **MQTT** or **VictoriaMetrics**, ensure these services are running. You can quickly start them using `docker-compose` or `podman-compose` with the provided file (*it uses a persistent volume for VictoriaMetrics locally, which seamlessly acts as an ephemeral volume in CI*):

```bash
docker-compose up -d
# OR with podman
podman-compose up -d
```


### Run (CLI)

```bash
# Show a full system dashboard
uv run pymonitor global-metrics

# Monitor a specific process by name
uv run pymonitor process --name brave.exe
```

### Background Exporter (Python API)

> [!IMPORTANT]
> When using the MQTT exporter, ensure you have installed the optional dependency (`pip install pymonitor[mqtt]` or `uv pip install ".[mqtt]"`) and that your MQTT broker is up and running before starting the exporter.

You can run PyMonitor as a background thread in your own Python applications. It will automatically load your configuration from `~/.pymonitor/config.json`.

```python
from pymonitor.monitor import PyMonitor
import time

monitor = PyMonitor()

# Start background monitoring thread (priority 0 to 5)
monitor.start(refresh_rate=5, exporter_type="mqtt", priority=5)

# Do your other work while metrics are exported automatically in Rust
time.sleep(60)

monitor.stop()
```

---

## 🛠️ Development Workflow

### Run Tests & Linting

```bash
uv run pytest          # run all tests
uv run ruff format .   # auto-format
uv run ruff check .    # lint
```

### Rebuild After Rust Changes

Every time you modify `src/lib.rs` you need to recompile the extension and regenerate the Python stubs:

```bash
# 1. Recompile & reinstall the Rust extension into the active venv
uv pip install -e .

# 2. Regenerate Python type stubs (updates python/pymonitor/_rust_monitor.pyi)
cargo run --bin stub_gen
```

---

## 🔧 Adding a New Metric

Follow these steps to expose a new piece of system data end-to-end.

### Step 1 — Add the field to `GlobalMetricsSnapshot` in `src/lib.rs`

```rust
#[gen_stub_pyclass]
#[pyclass(get_all)]
pub struct GlobalMetricsSnapshot {
    // ... existing fields ...
    pub my_new_metric: f32,   // 👈 add your field here
}
```

### Step 2 — Populate the field inside `get_global_metrics()`

```rust
fn get_global_metrics() -> PyResult<GlobalMetricsSnapshot> {
    // ... existing logic ...

    let my_new_metric = sys.some_sysinfo_call();   // 👈 gather data

    Ok(GlobalMetricsSnapshot {
        // ... existing fields ...
        my_new_metric,   // 👈 include in the struct literal
    })
}
```

### Step 3 — Recompile and regenerate stubs

```bash
uv pip install -e .
cargo run --bin stub_gen
```

### Step 4 — Display it in `python/pymonitor/cli.py`

```python
# Inside global_metrics():
table.add_row("My New Metric:", f"{metrics.my_new_metric:.2f}")
```

### Step 5 — Update the mock in `tests/test_cli.py`

```python
mock_metrics.my_new_metric = 42.0
```

> [!IMPORTANT]
> Always run `cargo run --bin stub_gen` after every Rust change so that the `.pyi` stub file stays in sync with the compiled extension. Without this, IDEs and type checkers will show incorrect type information.

> [!NOTE]
> If you need a metric that `sysinfo` does not provide (e.g. GPU name), implement it as a plain Python helper function in `cli.py` using `subprocess` or the `platform` module — see `get_gpu_name()` for an example.

---

## 📟 CLI Commands

### `global-metrics`

Displays a full system snapshot dashboard. Panels are automatically placed side-by-side when the terminal is wide enough.

```bash
uv run pymonitor global-metrics
```

![global-metrics demo](docs/global-metrics.gif)

**Output panels:**

| Panel | Metric | Backend |
|-------|--------|---------|
| 🖥️ System Information | OS name & version | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | Kernel version | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | Hostname | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | CPU brand, cores & threads | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | GPU name | 🐍 Python (`wmic` / `lspci` subprocess) |
| 🖥️ System Information | Total RAM | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | Available disk space & % | 🦀 Rust (`sysinfo`) |
| 🖥️ System Information | Boot time & uptime | 🦀 Rust (`sysinfo`) |
| 👥 System Users | Real OS user accounts | 🦀 Rust (`sysinfo`) |
| 👥 System Users | Admin rights detection | 🐍 Python (group name filtering) |
| ⚡ System Instant Metrics | CPU usage % | 🦀 Rust (`sysinfo`) |
| ⚡ System Instant Metrics | CPU temperature | 🦀 Rust (`sysinfo` components) |
| ⚡ System Instant Metrics | Per-core CPU usage | 🦀 Rust (`sysinfo`) |
| ⚡ System Instant Metrics | Load average (1m / 5m / 15m) | 🦀 Rust (`sysinfo`) |
| ⚡ System Instant Metrics | RAM usage % | 🦀 Rust (`sysinfo`) |
| ⚡ System Instant Metrics | Swap usage % | 🦀 Rust (`sysinfo`) |
| 🏆 Top CPU Consumers | Top 4 processes by CPU | 🦀 Rust (`sysinfo`) |
| 🌐 Network Instant Metrics | Interface names | 🦀 Rust (`sysinfo`) |
| 🌐 Network Instant Metrics | Local IPv4 address | 🦀 Rust (`sysinfo`) |
| 🌐 Network Instant Metrics | Rx / Tx speed (MB/s) | 🦀 Rust (`sysinfo`) |

---

### `process`

Monitors all running instances of a named process and shows per-PID resource usage, sorted by CPU consumption.

```bash
uv run pymonitor process --name python
# or short form:
uv run pymonitor process -n chrome.exe
```

![process demo](docs/process.gif)

**Output table:**

| Column | Metric | Backend |
|--------|--------|---------|
| PID | Process identifier | 🦀 Rust (`sysinfo`) |
| CPU Usage (%) | Per-process CPU % | 🦀 Rust (`sysinfo`) |
| RAM Usage (%) | Per-process RAM % of total | 🦀 Rust (`sysinfo`) |

> [!NOTE]
> Rows are sorted **descending by CPU usage**. If multiple instances of the same process are running (e.g. browser tabs), you will see one row per PID.

---

## 🏗️ Architecture

```
pymonitor/
├── src/
│   ├── lib.rs                      # 🦀 Rust extension — sysinfo polling, PyO3 bindings, background thread
│   └── exporter/
│       ├── mod.rs                  # 🦀 Exporter trait + factory (create_exporter)
│       ├── mqtt.rs                 # 🦀 MQTT exporter (rumqttc, non-blocking channel)
│       └── victoria_metrics.rs    # 🦀 VictoriaMetrics exporter (ureq, non-blocking channel)
├── python/
│   └── pymonitor/
│       ├── _rust_monitor.pyi       # Auto-generated type stubs (do not edit manually)
│       ├── monitor.py              # Python wrapper — PyMonitor + ExporterType enum
│       └── cli.py                  # Typer CLI + Rich display logic
└── tests/
    ├── test_cli.py                 # Integration tests for all CLI commands
    └── test_monitor.py             # Integration tests: Rust backend + MQTT subscriber
```

### Data flow — background exporter

```
sysinfo (Rust crate)
    └─▶ get_global_metrics_internal()          [monitoring thread — priority-adjusted]
            └─▶ GlobalMetricsSnapshot (Serialize)
                    └─▶ serde_json::to_string()
                            └─▶ mpsc::Sender<String>   [non-blocking, exporter worker thread]
                                    └─▶ MqttExporter / VictoriaMetricsExporter
                                            └─▶ Broker / Database
```

### Backend legend

| Badge | Meaning |
|-------|---------|
| 🦀 Rust (`sysinfo`) | Data sourced directly from the `sysinfo` Rust crate via PyO3 |
| 🐍 Python | Data obtained through Python's `subprocess`, `platform`, or pure logic |

---

## 📡 Receiving Exported Data

### MQTT

PyMonitor publishes a **JSON object** (all fields of `GlobalMetricsSnapshot`) to a single topic every `refresh_rate` seconds.

| Item | Value |
|------|-------|
| **Broker address** | `~/.pymonitor/config.json` → `endpoints.mqtt` (e.g. `localhost:1883`) |
| **Topic** | `pymonitor/metrics` |
| **QoS** | 0 (At Most Once) |
| **Retain** | No |
| **Payload format** | UTF-8 JSON |

**Payload fields** (all in one JSON object on `pymonitor/metrics`):

| JSON key | Type | Description |
|----------|------|-------------|
| `cpu_usage` | `float` | Global CPU usage % |
| `cpu_brand` | `string` | CPU model name |
| `ram_percent` | `float` | RAM used % |
| `max_ram` | `int` | Total RAM in bytes |
| `disk_percent` | `float` | Disk free % |
| `available_disk` | `int` | Available disk in bytes |
| `boot_time` | `int` | Unix timestamp of last boot |
| `os_name` | `string` | OS name |
| `os_version` | `string` | OS version string |
| `kernel_version` | `string` | Kernel version |
| `hostname` | `string` | Machine hostname |
| `core_count_physical` | `int \| null` | Physical CPU core count |
| `core_count_logical` | `int` | Logical CPU thread count |
| `cpu_temperature` | `float \| null` | CPU temperature in °C (if available) |
| `swap_total` | `int` | Total swap in bytes |
| `swap_used` | `int` | Used swap in bytes |
| `network_rx_bytes` | `int` | Total bytes received (all interfaces) |
| `network_tx_bytes` | `int` | Total bytes transmitted (all interfaces) |
| `network_interfaces` | `array` | Per-interface `[name, rx, tx, [ips]]` |
| `per_core_usage` | `array[float]` | Per-logical-core usage % |
| `load_avg_1m` | `float` | 1-minute load average |
| `load_avg_5m` | `float` | 5-minute load average |
| `load_avg_15m` | `float` | 15-minute load average |
| `users` | `array` | `[username, [groups]]` pairs |
| `top_processes` | `array` | Top 4 CPU consumers — `[name, pid, cpu%]` |

**Example subscriber (Python):**

```python
import json
import paho.mqtt.client as mqtt

def on_message(client, userdata, msg):
    data = json.loads(msg.payload)
    print(f"CPU: {data['cpu_usage']:.1f}%  RAM: {data['ram_percent']:.1f}%")

client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_message = on_message
client.connect("localhost", 1883)
client.subscribe("pymonitor/metrics")
client.loop_forever()
```

---

### VictoriaMetrics

PyMonitor POSTs the same JSON snapshot to the VictoriaMetrics import endpoint.

| Item | Value |
|------|-------|
| **Endpoint** | `~/.pymonitor/config.json` → `endpoints.victoriametrics` (e.g. `http://localhost:8428/api/v1/import`) |
| **HTTP method** | `POST` |
| **Content-Type** | `application/json` |
| **Payload format** | JSON (same field list as the MQTT table above) |

> [!NOTE]
> Query stored metrics via MetricsQL or `/api/v1/query` using field names as metric names, e.g. `cpu_usage`, `ram_percent`.

---

## 📦 Dependencies

| Package | Role |
|---------|------|
| `sysinfo` (Rust) | Cross-platform hardware & OS metrics |
| `pyo3` | Rust ↔ Python FFI bridge |
| `pyo3-stub-gen` | Auto-generates `.pyi` type stubs from Rust code |
| `rumqttc` (Rust) | MQTT client for the background exporter |
| `ureq` (Rust) | HTTP client for the VictoriaMetrics exporter |
| `serde` / `serde_json` (Rust) | JSON serialization of `GlobalMetricsSnapshot` |
| `thread-priority` (Rust) | Cross-platform OS thread priority management |
| `typer` | CLI argument parsing |
| `rich` | Terminal formatting & colour output |

---

## 📄 License

See [`LICENSE`](LICENSE) for details.