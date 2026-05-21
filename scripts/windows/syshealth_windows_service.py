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

import sys

import servicemanager
import win32event
import win32service
import win32serviceutil
from syshealth.monitor import ExporterType, SysHealth


class SysHealthService(win32serviceutil.ServiceFramework):
    """SysHealth Windows Service Implementation."""

    _svc_name_ = "SysHealth"
    _svc_display_name_ = "SysHealth Background Service"
    _svc_description_ = "Continuously monitors system metrics and exports them using SysHealth."

    def __init__(self, args):
        """Init Service."""
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        self.monitor = SysHealth()
        
        self.refresh_rate = 5
        self.priority = 5
        self.exporter = "victoriametrics"
        
        # Parse arguments passed from Service Control Manager
        # args[0] is service name
        if len(args) > 1:
            try:
                self.refresh_rate = int(args[1])
            except ValueError:
                pass
        if len(args) > 2:
            try:
                self.priority = int(args[2])
            except ValueError:
                pass
        if len(args) > 3:
            self.exporter = args[3]

    def SvcStop(self):
        """Service Stop Request."""
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        """Service Run Request."""
        servicemanager.LogMsg(
            servicemanager.EVENTLOG_INFORMATION_TYPE, 
            servicemanager.PYS_SERVICE_STARTED, 
            (self._svc_name_, f"Refresh: {self.refresh_rate}s, Priority: {self.priority}, Exporter: {self.exporter}")
        )
        self.main()

    def main(self):
        """Main function called when service starts."""
        try:
            exporter_enum = ExporterType(self.exporter)
        except ValueError:
            exporter_enum = ExporterType.VICTORIAMETRICS

        self.monitor.start(
            refresh_rate=self.refresh_rate, 
            exporter_type=exporter_enum, 
            priority=self.priority
        )
        # Block indefinitely until stop event is received (0 CPU usage)
        win32event.WaitForSingleObject(self.hWaitStop, win32event.INFINITE)
        self.monitor.stop()


if __name__ == "__main__":
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(SysHealthService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(SysHealthService)
