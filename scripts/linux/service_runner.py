import signal
import sys
import threading

from pymonitor.monitor import PyMonitor


def main():
    stop_event = threading.Event()

    def handler(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGTERM, handler)
    signal.signal(signal.SIGINT, handler)

    with PyMonitor() as monitor:
        # Start without duration to run infinitely
        monitor.start(refresh_rate=5, exporter_type="mqtt", priority=5)
        # Block with 0 CPU usage until a signal is received
        stop_event.wait()


if __name__ == "__main__":
    main()
