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

use pyo3::prelude::*;
use sysinfo::{ProcessesToUpdate, System};
use std::sync::{Arc, atomic::{AtomicBool, Ordering}};
use pyo3_stub_gen::{define_stub_info_gatherer, derive::{gen_stub_pyclass, gen_stub_pyfunction, gen_stub_pymethods}};
use serde::Serialize;

mod exporter;

/// Holds the shared state to allow Python to stop the Rust background thread.
#[gen_stub_pyclass]
#[pyclass]
pub struct MonitorHandle {
    is_running: Arc<AtomicBool>,
    errors: Arc<std::sync::Mutex<Vec<String>>>,
}

#[gen_stub_pymethods]
#[pymethods]
impl MonitorHandle {
    /// Signals the background thread to safely terminate.
    fn stop(&self) {
        self.is_running.store(false, Ordering::Relaxed);
    }

    fn get_errors(&self) -> Vec<String> {
        let mut errs = self.errors.lock().unwrap();
        let result = errs.clone();
        errs.clear();
        result
    }
}

/// Grab usage metrics for specific processes by name.
#[gen_stub_pyfunction]
#[pyfunction]
fn get_process_metrics(name: &str) -> PyResult<Vec<(u32, f32, f32)>> {
    let mut sys = System::new_with_specifics(
        sysinfo::RefreshKind::nothing()
        .with_processes(sysinfo::ProcessRefreshKind::nothing().with_cpu().with_memory())
        .with_memory(sysinfo::MemoryRefreshKind::nothing().with_ram())
    );
    // Sleep is mandatory to establish a time delta for process CPU % calculations.
    std::thread::sleep(std::time::Duration::from_millis(200));
    sys.refresh_processes(ProcessesToUpdate::All, true);

    let mut results = Vec::new();
    let total_mem = sys.total_memory() as f32;
    for (pid, process) in sys.processes() {
        if process.name() == name {
            let mem_percent = (process.memory() as f32 / total_mem) * 100.0;
            results.push((pid.as_u32(), process.cpu_usage(), mem_percent));
        }
    }
    Ok(results)
}

#[gen_stub_pyclass]
#[pyclass(get_all)]
#[derive(Serialize)]
pub struct GlobalMetricsSnapshot {
    pub source: String,
    pub timestamp_ms: u64,
    pub units: std::collections::HashMap<String, String>,
    pub cpu_usage: f32,
    pub cpu_brand: String,
    pub ram_percent: f32,
    pub max_ram: u64,
    pub disk_percent: f32,
    pub available_disk: u64,
    pub boot_time: u64,
    pub os_name: String,
    pub os_version: String,
    pub kernel_version: String,
    pub hostname: String,
    pub core_count_physical: Option<usize>,
    pub core_count_logical: usize,
    pub cpu_temperature: Option<f32>,
    pub swap_total: u64,
    pub swap_used: u64,
    pub network_rx_bytes: u64,
    pub network_tx_bytes: u64,
    pub network_interfaces: Vec<(String, u64, u64, Vec<String>)>,
    pub per_core_usage: Vec<f32>,
    pub load_avg_1m: f64,
    pub load_avg_5m: f64,
    pub load_avg_15m: f64,
    pub users: Vec<(String, Vec<String>)>,
    pub top_processes: Vec<(String, u32, f32)>,
}

fn get_global_metrics_internal(sys: &mut System, networks: &mut sysinfo::Networks, components: &mut sysinfo::Components, disks: &mut sysinfo::Disks) -> GlobalMetricsSnapshot {
    sys.refresh_cpu_usage();

    // Sleep is mandatory to establish a time delta for process CPU % calculations.
    std::thread::sleep(std::time::Duration::from_millis(200));
    sys.refresh_cpu_usage();
    sys.refresh_processes(ProcessesToUpdate::All, true);
    networks.refresh(true);

    let ram_percent = (sys.used_memory() as f32 / sys.total_memory() as f32) * 100.0;
    let cpu_brand = sys.cpus().first().map(|cpu| cpu.brand().to_string()).unwrap_or_else(|| "Unknown".to_string());

    disks.refresh(true);
    let mut available_disk_bytes = 0;
    let mut total_disk_bytes = 0;
    for disk in disks.list() {
        available_disk_bytes += disk.available_space();
        total_disk_bytes += disk.total_space();
    }

    let disk_percent = if total_disk_bytes > 0 {
        (available_disk_bytes as f32 / total_disk_bytes as f32) * 100.0
    } else {
        0.0
    };

    let os_name = System::name().unwrap_or_else(|| "Unknown".to_string());
    let os_version = System::os_version().unwrap_or_else(|| "Unknown".to_string());
    let kernel_version = System::kernel_version().unwrap_or_else(|| "Unknown".to_string());
    let hostname = System::host_name().unwrap_or_else(|| "Unknown".to_string());
    
    let core_count_physical = sysinfo::System::physical_core_count();
    let core_count_logical = sys.cpus().len();

    let mut cpu_temperature: Option<f32> = None;
    components.refresh(true);
    for component in components.list() {
        let label = component.label().to_lowercase();
        if label.contains("cpu") || label.contains("core") || label.contains("tctl") {
            cpu_temperature = component.temperature();
            break;
        }
    }

    let swap_total = sys.total_swap();
    let swap_used = sys.used_swap();

    let mut network_rx_bytes = 0;
    let mut network_tx_bytes = 0;
    let mut network_interfaces = Vec::new();
    
    for (interface_name, data) in networks.iter() {
        network_rx_bytes += data.received();
        network_tx_bytes += data.transmitted();
        
        let mut ips = Vec::new();
        for ip_net in data.ip_networks() {
            ips.push(format!("{}", ip_net.addr));
        }
        
        network_interfaces.push((interface_name.to_string(), data.received(), data.transmitted(), ips));
    }

    let per_core_usage: Vec<f32> = sys.cpus().iter().map(|c| c.cpu_usage()).collect();

    let load_avg = System::load_average();

    // Users — include group names so Python can filter system accounts and detect admin rights
    let sys_users = sysinfo::Users::new_with_refreshed_list();
    let mut users = Vec::new();
    for user in sys_users.list() {
        let group_names: Vec<String> = user.groups().iter().map(|g| g.name().to_string()).collect();
        users.push((user.name().to_string(), group_names));
    }

    // Top processes
    let mut processes_vec: Vec<_> = sys.processes().values().collect();
    processes_vec.sort_by(|a, b| b.cpu_usage().partial_cmp(&a.cpu_usage()).unwrap_or(std::cmp::Ordering::Equal));
    
    let mut top_processes = Vec::new();
    for process in processes_vec.iter().take(4) {
        top_processes.push((process.name().to_string_lossy().into_owned(), process.pid().as_u32(), process.cpu_usage()));
    }

    let mut units = std::collections::HashMap::new();
    units.insert("cpu_usage".to_string(), "percent".to_string());
    units.insert("ram_percent".to_string(), "percent".to_string());
    units.insert("max_ram".to_string(), "bytes".to_string());
    units.insert("disk_percent".to_string(), "percent".to_string());
    units.insert("available_disk".to_string(), "bytes".to_string());
    units.insert("boot_time".to_string(), "seconds".to_string());
    units.insert("swap_total".to_string(), "bytes".to_string());
    units.insert("swap_used".to_string(), "bytes".to_string());
    units.insert("network_rx_bytes".to_string(), "bytes".to_string());
    units.insert("network_tx_bytes".to_string(), "bytes".to_string());
    units.insert("cpu_temperature".to_string(), "celsius".to_string());
    units.insert("per_core_usage".to_string(), "percent".to_string());
    units.insert("load_avg".to_string(), "load".to_string());

    GlobalMetricsSnapshot {
        source: "syshealth".to_string(),
        timestamp_ms: std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_millis() as u64,
        units,
        cpu_usage: sys.global_cpu_usage(),
        cpu_brand,
        ram_percent,
        max_ram: sys.total_memory(),
        disk_percent,
        available_disk: available_disk_bytes,
        boot_time: System::boot_time(),
        os_name,
        os_version,
        kernel_version,
        hostname,
        core_count_physical,
        core_count_logical,
        cpu_temperature,
        swap_total,
        swap_used,
        network_rx_bytes,
        network_tx_bytes,
        network_interfaces,
        per_core_usage,
        load_avg_1m: load_avg.one,
        load_avg_5m: load_avg.five,
        load_avg_15m: load_avg.fifteen,
        users,
        top_processes,
    }
}

/// Grab a single snapshot of the current global CPU, RAM usage percentage, available disk space in bytes, and boot time.
#[gen_stub_pyfunction]
#[pyfunction]
fn get_global_metrics() -> PyResult<GlobalMetricsSnapshot> {
    let mut sys = System::new_with_specifics(
        sysinfo::RefreshKind::nothing()
        .with_cpu(sysinfo::CpuRefreshKind::nothing().with_cpu_usage())
        .with_memory(sysinfo::MemoryRefreshKind::nothing().with_ram().with_swap())
        .with_processes(sysinfo::ProcessRefreshKind::nothing().with_cpu())
    );
    let mut networks = sysinfo::Networks::new_with_refreshed_list();
    let mut components = sysinfo::Components::new_with_refreshed_list();
    let mut disks = sysinfo::Disks::new_with_refreshed_list();

    Ok(get_global_metrics_internal(&mut sys, &mut networks, &mut components, &mut disks))
}

#[gen_stub_pyfunction]
#[pyfunction]
fn start_monitoring(exporter_type: String, endpoint: String, refresh_rate: u64, priority: u8, duration: Option<u64>) -> PyResult<MonitorHandle> {
    let is_running = Arc::new(AtomicBool::new(true));
    let is_running_clone = is_running.clone();

    let errors = Arc::new(std::sync::Mutex::new(Vec::new()));
    let errors_clone = errors.clone();

    std::thread::spawn(move || {
        use thread_priority::*;
        // Map 0 (highest) to 5 (lowest) to thread priority
        // OS priority: Windows has 7 levels, Linux has 40
        // Use cross-platform thread_priority crate
        let thread_prio = match priority {
            0 => ThreadPriority::Max,
            1 => ThreadPriority::Crossplatform(ThreadPriorityValue::try_from(75).unwrap_or(ThreadPriorityValue::default())),
            2 => ThreadPriority::Crossplatform(ThreadPriorityValue::try_from(50).unwrap_or(ThreadPriorityValue::default())),
            3 => ThreadPriority::Crossplatform(ThreadPriorityValue::try_from(25).unwrap_or(ThreadPriorityValue::default())),
            4 => ThreadPriority::Crossplatform(ThreadPriorityValue::try_from(10).unwrap_or(ThreadPriorityValue::default())),
            _ => ThreadPriority::Min,
        };
        let _ = set_current_thread_priority(thread_prio);

        let mut sys = System::new_with_specifics(
            sysinfo::RefreshKind::nothing()
            .with_cpu(sysinfo::CpuRefreshKind::nothing().with_cpu_usage())
            .with_memory(sysinfo::MemoryRefreshKind::nothing().with_ram().with_swap())
            .with_processes(sysinfo::ProcessRefreshKind::nothing().with_cpu())
        );
        let mut networks = sysinfo::Networks::new_with_refreshed_list();
        let mut components = sysinfo::Components::new_with_refreshed_list();
        let mut disks = sysinfo::Disks::new_with_refreshed_list();

        let mut exporter = match exporter::create_exporter(&exporter_type, &endpoint, errors_clone.clone()) {
            Ok(e) => e,
            Err(e) => {
                eprintln!("Failed to create exporter: {}", e);
                return;
            }
        };

        let start_time = std::time::Instant::now();
        while is_running_clone.load(Ordering::Relaxed) {
            if let Some(d) = duration {
                if start_time.elapsed().as_secs() >= d {
                    break;
                }
            }
            let metrics = get_global_metrics_internal(&mut sys, &mut networks, &mut components, &mut disks);
            if let Err(e) = exporter.export(&metrics) {
                let mut errs = errors_clone.lock().unwrap();
                if errs.len() < 100 {
                    errs.push(format!("Failed to export metrics: {}", e));
                }
            }
            std::thread::sleep(std::time::Duration::from_secs(refresh_rate));
        }
    });

    Ok(MonitorHandle { is_running, errors })
}

/// The Rust module definition exported to Python.
#[pymodule]
fn _rust_monitor(_py: Python, module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_class::<MonitorHandle>()?;
    module.add_class::<GlobalMetricsSnapshot>()?;
    module.add_function(wrap_pyfunction!(get_process_metrics, module)?)?;
    module.add_function(wrap_pyfunction!(get_global_metrics, module)?)?;
    module.add_function(wrap_pyfunction!(start_monitoring, module)?)?;
    Ok(())
}

define_stub_info_gatherer!(stub_info);