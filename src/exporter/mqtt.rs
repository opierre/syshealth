use crate::GlobalMetricsSnapshot;
use crate::exporter::Exporter;
use rumqttc::{Client, MqttOptions, QoS};
use std::sync::mpsc;
use std::thread;
use std::time::Duration;

use std::sync::{Arc, Mutex};

pub struct MqttExporter {
    sender: mpsc::Sender<String>,
}

impl MqttExporter {
    pub fn new(endpoint: &str, _errors: Arc<Mutex<Vec<String>>>) -> Result<Self, String> {
        // Parse "host:port" — fall back to default port 1883 if absent.
        let (host, port) = match endpoint.rsplit_once(':') {
            Some((h, p)) => {
                let port: u16 = p.parse().map_err(|_| format!("Invalid MQTT port in endpoint: {}", endpoint))?;
                (h.to_string(), port)
            }
            None => (endpoint.to_string(), 1883u16),
        };

        let (tx, rx) = mpsc::channel::<String>();

        let mut mqttoptions = MqttOptions::new("pymonitor", host, port);
        mqttoptions.set_keep_alive(Duration::from_secs(5));

        let (client, mut connection) = Client::new(mqttoptions, 64);

        let connection_errors = _errors.clone();
        // Event-loop thread: must run continuously so the broker receives ACKs
        // and the internal send queue is flushed.
        thread::spawn(move || {
            for event in connection.iter() {
                if let Err(e) = event {
                    let mut errs = connection_errors.lock().unwrap();
                    if errs.len() < 100 {
                        errs.push(format!("MQTT connection error: {}", e));
                    }
                }
            }
        });

        let publish_errors = _errors.clone();
        // Publisher thread: blocks on the channel; each received JSON string is
        // published without blocking the metric-gathering thread.
        thread::spawn(move || {
            while let Ok(msg) = rx.recv() {
                if let Err(e) = client.publish("pymonitor/metrics", QoS::AtMostOnce, false, msg.into_bytes()) {
                    let mut errs = publish_errors.lock().unwrap();
                    if errs.len() < 100 {
                        errs.push(format!("MQTT publish error: {}", e));
                    }
                }
            }
        });

        Ok(Self { sender: tx })
    }
}

impl Exporter for MqttExporter {
    fn export(&mut self, metrics: &GlobalMetricsSnapshot) -> Result<(), String> {
        let json = serde_json::to_string(metrics).map_err(|e| e.to_string())?;
        self.sender.send(json).map_err(|e| e.to_string())?;
        Ok(())
    }
}
