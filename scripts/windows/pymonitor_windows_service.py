import sys

import servicemanager
import win32event
import win32service
import win32serviceutil
from pymonitor.monitor import ExporterType, PyMonitor


class PyMonitorService(win32serviceutil.ServiceFramework):
    """PyMonitor Windows Service Implementation."""

    _svc_name_ = "PyMonitor"
    _svc_display_name_ = "PyMonitor Background Service"
    _svc_description_ = "Continuously monitors system metrics and exports them using PyMonitor."

    def __init__(self, args):
        """Init Service."""
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.monitor = PyMonitor()

    def SvcStop(self):
        """Service Stop Request."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        """Service Run Request."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE, servicemanager.PYS_SERVICE_STARTED, (self._svc_name_, "")
        )
        self.main()

    def main(self):
        """Main function called when service starts."""
        self.monitor.start(refresh_rate=5, exporter_type=ExporterType.VICTORIAMETRICS, priority=5)
        # Block indefinitely until stop event is received (0 CPU usage)
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        self.monitor.stop()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PyMonitorService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PyMonitorService)
