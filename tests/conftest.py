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
from pathlib import Path
import socket
import subprocess
import time

import pytest


def is_port_open(port: int, host: str = "localhost") -> bool:
    """Check if a port is open."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sck:
        sck.settimeout(0.5)
        return sck.connect_ex((host, port)) == 0


@pytest.fixture(scope="session", autouse=True)
def ensure_docker_compose_running():
    """Ensure that the required docker services are running before tests start."""
    broker_port = 1883
    victoriametrics_port = 8428

    if not is_port_open(broker_port) or not is_port_open(victoriametrics_port):
        compose_file = Path(__file__).parent / "docker-compose.yml"
        
        # Attempt to use 'docker compose' (V2), fallback to 'docker-compose' (V1)
        try:
            subprocess.run(["docker", "compose", "-f", compose_file, "up", "-d"], check=True)
        except Exception:
            subprocess.run(["docker-compose", "-f", compose_file, "up", "-d"], check=True)

        # Wait for services to become available
        max_retries = 30
        for _ in range(max_retries):
            if is_port_open(broker_port) and is_port_open(victoriametrics_port):
                break
            time.sleep(1)
        else:
            raise RuntimeError("Failed to start docker-compose services (broker or victoriametrics).")
