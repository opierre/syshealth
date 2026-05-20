// Copyright 2026 Pierre OLIVIER
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

use crate::GlobalMetricsSnapshot;
use crate::exporter::Exporter;
use std::sync::{Arc, Mutex, mpsc};
use std::thread;

pub struct VictoriaMetricsExporter {
    sender: mpsc::Sender<String>,
}

impl VictoriaMetricsExporter {
    pub fn new(endpoint: &str, errors: Arc<Mutex<Vec<String>>>) -> Result<Self, String> {
        let (tx, rx) = mpsc::channel::<String>();
        let endpoint = endpoint.to_string();

        thread::spawn(move || {
            while let Ok(msg) = rx.recv() {
                match ureq::post(&endpoint)
                    .header("Content-Type", "application/json")
                    .send(&msg)
                {
                    Ok(response) => {
                        let status: u16 = response.status().into();
                        if status >= 400 {
                            let text = response.into_body().read_to_string().unwrap_or_default();
                            let mut errs = errors.lock().unwrap();
                            if errs.len() < 100 {
                                errs.push(format!("VictoriaMetrics server error {} : {}", status, text));
                            }
                        }
                    }
                    Err(e) => {
                        let mut errs = errors.lock().unwrap();
                        if errs.len() < 100 {
                            errs.push(format!("VictoriaMetrics transport error: {}", e));
                        }
                    }
                }
            }
        });

        Ok(Self { sender: tx })
    }
}

impl Exporter for VictoriaMetricsExporter {
    fn export(&mut self, metrics: &GlobalMetricsSnapshot) -> Result<(), String> {
        let mut payload = String::new();

        let mut add_metric = |name: &str, unit: &str, value: f64| {
            let line = serde_json::json!({
                "metric": {
                    "__name__": name,
                    "source": metrics.source,
                    "hostname": metrics.hostname,
                    "unit": unit
                },
                "values": [value],
                "timestamps": [metrics.timestamp_ms]
            });
            payload.push_str(&line.to_string());
            payload.push('\n');
        };

        let get_unit = |key: &str| -> &str {
            metrics.units.get(key).map(|s| s.as_str()).unwrap_or("unknown")
        };

        add_metric("cpu_usage", get_unit("cpu_usage"), metrics.cpu_usage as f64);
        add_metric("ram_percent", get_unit("ram_percent"), metrics.ram_percent as f64);
        add_metric("disk_percent", get_unit("disk_percent"), metrics.disk_percent as f64);
        add_metric("available_disk", get_unit("available_disk"), metrics.available_disk as f64);
        add_metric("boot_time", get_unit("boot_time"), metrics.boot_time as f64);
        add_metric("swap_used", get_unit("swap_used"), metrics.swap_used as f64);
        add_metric("swap_total", get_unit("swap_total"), metrics.swap_total as f64);
        add_metric("network_rx_bytes", get_unit("network_rx_bytes"), metrics.network_rx_bytes as f64);
        add_metric("network_tx_bytes", get_unit("network_tx_bytes"), metrics.network_tx_bytes as f64);
        add_metric("load_avg_1m", get_unit("load_avg"), metrics.load_avg_1m);
        add_metric("load_avg_5m", get_unit("load_avg"), metrics.load_avg_5m);
        add_metric("load_avg_15m", get_unit("load_avg"), metrics.load_avg_15m);

        if let Some(temp) = metrics.cpu_temperature {
            add_metric("cpu_temperature", get_unit("cpu_temperature"), temp as f64);
        }

        let per_core_unit = get_unit("per_core_usage");
        for (core_idx, usage) in metrics.per_core_usage.iter().enumerate() {
            let line = serde_json::json!({
                "metric": {
                    "__name__": "per_core_usage",
                    "source": metrics.source,
                    "hostname": metrics.hostname,
                    "unit": per_core_unit,
                    "core": core_idx.to_string()
                },
                "values": [*usage as f64],
                "timestamps": [metrics.timestamp_ms]
            });
            payload.push_str(&line.to_string());
            payload.push('\n');
        }

        let rx_unit = get_unit("network_rx_bytes");
        let tx_unit = get_unit("network_tx_bytes");
        for net in &metrics.network_interfaces {
            let line_rx = serde_json::json!({
                "metric": {
                    "__name__": "network_rx_bytes_interface",
                    "source": metrics.source,
                    "hostname": metrics.hostname,
                    "unit": rx_unit,
                    "interface": net.0
                },
                "values": [net.1 as f64],
                "timestamps": [metrics.timestamp_ms]
            });
            payload.push_str(&line_rx.to_string());
            payload.push('\n');

            let line_tx = serde_json::json!({
                "metric": {
                    "__name__": "network_tx_bytes_interface",
                    "source": metrics.source,
                    "hostname": metrics.hostname,
                    "unit": tx_unit,
                    "interface": net.0
                },
                "values": [net.2 as f64],
                "timestamps": [metrics.timestamp_ms]
            });
            payload.push_str(&line_tx.to_string());
            payload.push('\n');
        }

        let cpu_unit = get_unit("cpu_usage");
        for top in &metrics.top_processes {
            let line = serde_json::json!({
                "metric": {
                    "__name__": "top_processes_cpu",
                    "source": metrics.source,
                    "hostname": metrics.hostname,
                    "unit": cpu_unit,
                    "process_name": top.0,
                    "pid": top.1.to_string()
                },
                "values": [top.2 as f64],
                "timestamps": [metrics.timestamp_ms]
            });
            payload.push_str(&line.to_string());
            payload.push('\n');
        }

        self.sender.send(payload).map_err(|e| e.to_string())?;
        Ok(())
    }
}
