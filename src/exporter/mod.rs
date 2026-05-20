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

pub mod mqtt;
pub mod victoria_metrics;

use crate::GlobalMetricsSnapshot;
use mqtt::MqttExporter;
use victoria_metrics::VictoriaMetricsExporter;

use std::sync::{Arc, Mutex};

pub trait Exporter: Send {
    fn export(&mut self, metrics: &GlobalMetricsSnapshot) -> Result<(), String>;
}

pub fn create_exporter(exporter_type: &str, endpoint: &str, errors: Arc<Mutex<Vec<String>>>) -> Result<Box<dyn Exporter>, String> {
    match exporter_type {
        "mqtt" => {
            let exporter = MqttExporter::new(endpoint, errors)?;
            Ok(Box::new(exporter))
        }
        "victoriametrics" => {
            let exporter = VictoriaMetricsExporter::new(endpoint, errors)?;
            Ok(Box::new(exporter))
        }
        _ => Err(format!("Unknown exporter type: {}", exporter_type)),
    }
}
