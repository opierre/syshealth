import argparse
import signal
import threading

from pymonitor.monitor import PyMonitor


def main():
    parser = argparse.ArgumentParser(description="PyMonitor background service runner")
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

    with PyMonitor() as monitor:
        # Start without duration to run infinitely
        monitor.start(refresh_rate=args.refresh_rate, exporter_type=args.exporter, priority=args.priority)
        # Block with 0 CPU usage until a signal is received
        stop_event.wait()


if __name__ == "__main__":
    main()
