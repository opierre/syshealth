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
"""Service runner."""

import argparse
import signal
import threading

from syshealth.monitor import SysHealth


def main():
    """Main entrypoint."""
    parser = argparse.ArgumentParser(description="SysHealth background service runner")
    parser.add_argument("--refresh-rate", type=int, default=5, help="Refresh rate in seconds")
    parser.add_argument("--priority", type=int, default=5, help="Thread priority (0-5)")
    parser.add_argument(
        "--exporter", type=str, default="victoriametrics", help="Exporter type (mqtt or victoriametrics)"
    )
    args = parser.parse_args()

    stop_event = threading.Event()

    def handler(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    with SysHealth() as monitor:
        # Start without duration to run infinitely
        monitor.start(refresh_rate=args.refresh_rate, exporter_type=args.exporter, priority=args.priority)
        # Block with 0 CPU usage until a signal is received
        stop_event.wait()


if __name__ == "__main__":
    main()
