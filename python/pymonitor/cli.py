"""CLI for PyMonitor."""

import os
import platform
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from pymonitor.monitor import PyMonitor
from rich.align import Align
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from typer import Option, Typer, confirm

app = Typer(help="PyMonitor CLI for tracking system constants.", add_completion=True)
console = Console()

MONITOR = PyMonitor()


def _print_adjacent(left, right) -> None:
    """Render two Rich renderables side-by-side if the terminal is wide enough.

    Measures the natural (minimum) width of each renderable and compares the
    sum to the current console width. If there is enough room the two items
    are placed in a borderless grid table; otherwise they are stacked.
    """
    from rich.measure import Measurement

    opts = console.options
    left_w = Measurement.get(console, opts, left).maximum
    right_w = Measurement.get(console, opts, right).maximum
    gap = 1  # one-space padding between columns
    if left_w + right_w + gap <= console.width:
        grid = Table.grid(expand=False, padding=(0, gap, 0, 0))
        grid.add_column()
        grid.add_column()
        grid.add_row(left, right)
        console.print(grid)
    else:
        console.print(left)
        console.print(right)


@app.command()
def process(
    name: str = Option(..., "--name", "-n", help="Name of the process to monitor"),
):
    """Fetch and display metrics for a specific process."""
    start_time = time.perf_counter()
    metrics = MONITOR.get_process_metrics(name)
    elapsed = time.perf_counter() - start_time

    if not metrics:
        console.print(f"[bold red]No processes found with name:[/bold red] '{name}'")
        return

    table = Table(
        title=f"Process Metrics: {name} [dim]({elapsed:.3f}s)[/dim]",
        show_header=True,
        header_style="bold magenta",
        title_justify="center",
    )
    table.add_column("PID", style="cyan", justify="center")
    table.add_column("CPU Usage (%)", style="green", justify="right")
    table.add_column("RAM Usage (%)", style="yellow", justify="right")

    for pid, cpu, mem in sorted(metrics, key=lambda x: x[1], reverse=True):
        table.add_row(str(pid), f"{cpu:.2f}%", f"{mem:.2f}%")

    console.print(table)


def get_gpu_name() -> str:
    """Fetch GPU name via wmic on Windows or lspci on Linux."""
    try:
        if platform.system() == "Windows":
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.check_output(
                ["wmic", "path", "win32_VideoController", "get", "name"], text=True, creationflags=creation_flags
            )
            lines = [line.strip() for line in result.split("\n") if line.strip()]
            if len(lines) > 1:
                return lines[1]
        elif platform.system() == "Linux":
            result = subprocess.check_output(["lspci"], text=True)
            for line in result.split("\n"):
                if "VGA compatible controller" in line or "3D controller" in line:
                    parts = line.split(": ", 1)
                    if len(parts) > 1:
                        return parts[1].strip()
    except Exception:
        pass
    return "Unknown"


@app.command()
def global_metrics():
    """Fetch and display global CPU, RAM, and boot time."""
    start_time = time.perf_counter()
    metrics = MONITOR.get_global_metrics()
    elapsed = time.perf_counter() - start_time

    # Fetch GPU
    gpu_brand = get_gpu_name()

    # Format into GB
    max_ram_gb = metrics.max_ram / (1024**3)
    available_disk_gb = metrics.available_disk / (1024**3)

    # Format boot time
    boot_time_dt = datetime.fromtimestamp(metrics.boot_time).strftime("%Y-%m-%d %H:%M:%S")
    uptime = timedelta(seconds=int(time.time() - metrics.boot_time))
    boot_time_display = f"{boot_time_dt} ({uptime} uptime)"

    sys_info_table = Table(show_header=False, box=None)
    sys_info_table.add_column("Property", style="cyan", justify="right")
    sys_info_table.add_column("Value", style="yellow", justify="left")

    sys_info_table.add_row("OS:", f"{metrics.os_name} {metrics.os_version} (Kernel: {metrics.kernel_version})")
    sys_info_table.add_row("Hostname:", metrics.hostname)

    physical_cores = metrics.core_count_physical if metrics.core_count_physical else "?"
    sys_info_table.add_row(
        "CPU:", f"{metrics.cpu_brand} ({physical_cores} Cores / {metrics.core_count_logical} Threads)"
    )
    sys_info_table.add_row("GPU:", gpu_brand)
    sys_info_table.add_row("Total RAM:", f"{max_ram_gb:.2f} GB")
    sys_info_table.add_row("Available Disk:", f"{available_disk_gb:.2f} GB ({metrics.disk_percent:.2f}%)")
    sys_info_table.add_row("Boot Time:", boot_time_display)

    # Build System Users panel
    ADMIN_GROUPS = {"administrators", "administrateurs", "admins", "sudo", "wheel"}
    USER_GROUPS = {"users", "utilisateurs"}
    real_users = []
    for username, groups in metrics.users:
        groups_lower = {g.lower() for g in groups}
        if groups_lower & USER_GROUPS:
            is_admin = bool(groups_lower & ADMIN_GROUPS)
            real_users.append((username, is_admin))

    user_table = Table(show_header=True, header_style="bold cyan", box=None)
    user_table.add_column("User", style="yellow", justify="left")
    user_table.add_column("Admin", style="green", justify="center")
    for username, is_admin in real_users:
        user_table.add_row(username, "[bold red]Yes[/bold red]" if is_admin else "No")
    if not real_users:
        user_table.add_row("No user accounts found", "-")

    _print_adjacent(
        Panel(
            Align.center(sys_info_table),
            title=f"System Information [dim]({elapsed:.3f}s)[/dim]",
            expand=False,
            border_style="blue",
        ),
        Panel(
            Align.center(user_table),
            title="System Users",
            expand=False,
            border_style="blue",
        ),
    )

    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="cyan", justify="right")
    table.add_column("Value", style="green", justify="left")

    table.add_row("CPU Usage:", f"{metrics.cpu_usage:.2f}%")
    if metrics.cpu_temperature is not None:
        table.add_row("CPU Temp:", f"{metrics.cpu_temperature:.1f} °C")

    per_core_strs = [f"{u:.0f}%" for u in metrics.per_core_usage]
    if per_core_strs:
        table.add_row("Per-Core Usage:", " ".join(per_core_strs))

    table.add_row("Load Avg:", f"{metrics.load_avg_1m:.2f}, {metrics.load_avg_5m:.2f}, {metrics.load_avg_15m:.2f}")
    table.add_row("RAM Usage:", f"{metrics.ram_percent:.2f}%")

    if metrics.swap_total > 0:
        swap_pct = (metrics.swap_used / metrics.swap_total) * 100.0
        table.add_row("Swap Usage:", f"{swap_pct:.2f}%")
    else:
        table.add_row("Swap Usage:", "0.00% (No Swap)")

    instant_panel = Panel(Align.center(table), title="System Instant Metrics", expand=False, border_style="blue")

    # Top CPU Consumers
    top_proc_table = Table(show_header=True, header_style="bold cyan", box=None)
    top_proc_table.add_column("PID", style="cyan", justify="center")
    top_proc_table.add_column("Process Name", style="yellow", justify="left")
    top_proc_table.add_column("CPU Usage", style="green", justify="right")

    for proc_name, pid, cpu_usage in metrics.top_processes:
        top_proc_table.add_row(str(pid), proc_name, f"{cpu_usage:.2f}%")

    top_proc_panel = Panel(Align.center(top_proc_table), title="Top CPU Consumers", expand=False, border_style="blue")

    _print_adjacent(instant_panel, top_proc_panel)

    # Network Instant Metrics Table
    net_table = Table(show_header=True, header_style="bold cyan", box=None)
    net_table.add_column("Interface", style="cyan", justify="left")
    net_table.add_column("IPv4", style="yellow", justify="left")
    net_table.add_column("Rx (MB/s)", style="green", justify="right")
    net_table.add_column("Tx (MB/s)", style="green", justify="right")

    for iface_name, rx_bytes, tx_bytes, ips in metrics.network_interfaces:
        rx_mbps = (rx_bytes / (1024**2)) * 5
        tx_mbps = (tx_bytes / (1024**2)) * 5
        # Filter to IPv4 only (simple check: no colons means it's not IPv6)
        ipv4_list = [ip for ip in ips if ":" not in ip]
        ip_str = ", ".join(ipv4_list) if ipv4_list else "-"
        net_table.add_row(iface_name, ip_str, f"{rx_mbps:.2f}", f"{tx_mbps:.2f}")

    if not metrics.network_interfaces:
        net_table.add_row("No interfaces found", "-", "-", "-")

    console.print(Panel(Align.center(net_table), title="Network Instant Metrics", expand=False, border_style="blue"))


@app.command()
def install_service():
    """Install PyMonitor as a background service for the current OS."""
    sys_name = platform.system()

    if sys_name == "Windows":
        import ctypes

        try:
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        except Exception:
            is_admin = False
    elif sys_name == "Linux":
        is_admin = os.getuid() == 0
    else:
        console.print(f"[bold red]Unsupported OS for service installation: {sys_name}[/bold red]")
        return

    if not is_admin:
        console.print("[bold red] ❌ Error: Administrator / Root privileges required to install services.[/bold red]")
        console.print("[yellow]Please restart your terminal as Administrator (Windows) or use sudo (Linux).[/yellow]")
        return

    repo_root = Path(__file__).resolve().parent.parent.parent

    # Check if service already exists
    service_exists = False
    if sys_name == "Windows":
        # sc query returns 0 if service exists, 1060 if it does not exist
        result = subprocess.run(["sc", "query", "PyMonitor"], capture_output=True)
        service_exists = result.returncode == 0
    elif sys_name == "Linux":
        target_service = Path("/etc/systemd/system/pymonitor.service")
        service_exists = target_service.exists()

    if service_exists:
        console.print("[yellow]PyMonitor service is already installed on this system.[/yellow]")
        delete_it = confirm("Do you want to stop and delete the current service to install the new one?")
        if not delete_it:
            console.print("[red]Aborting installation.[/red]")
            return

        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
            t = prog.add_task("[cyan]Stopping and removing existing service...", total=None)
            try:
                if sys_name == "Windows":
                    subprocess.run(["sc", "stop", "PyMonitor"], capture_output=True)
                    time.sleep(2)  # Give it time to stop
                    subprocess.run(["sc", "delete", "PyMonitor"], capture_output=True)
                elif sys_name == "Linux":
                    subprocess.run(["systemctl", "stop", "pymonitor.service"], capture_output=True)
                    subprocess.run(["systemctl", "disable", "pymonitor.service"], capture_output=True)
                    if target_service.exists():
                        target_service.unlink()
                    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
                prog.update(t, description="[bold green]✔ Existing service removed![/bold green]")
            except Exception as e:
                prog.update(t, description=f"[bold red] ❌ Failed to remove existing service: {e}[/bold red]")
                return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"[cyan]Installing PyMonitor background service for {sys_name}...", total=None)

        try:
            if sys_name == "Windows":
                windows_script = repo_root / "scripts" / "windows" / "pymonitor_windows_service.py"
                if not windows_script.exists():
                    raise FileNotFoundError(f"Service script not found at {windows_script}")

                # Install service using pywin32
                subprocess.run(
                    [sys.executable, str(windows_script), "--startup", "auto", "install"],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            elif sys_name == "Linux":
                linux_script = repo_root / "scripts" / "linux" / "pymonitor.service"
                if not linux_script.exists():
                    raise FileNotFoundError(f"Service unit file not found at {linux_script}")

                target_service = Path("/etc/systemd/system/pymonitor.service")
                shutil.copy(linux_script, target_service)

                subprocess.run(["systemctl", "daemon-reload"], check=True, capture_output=True)
                subprocess.run(["systemctl", "enable", "pymonitor.service"], check=True, capture_output=True)

            progress.update(task, description=f"[bold green]✔ Successfully installed {sys_name} service![/bold green]")
        except Exception as e:
            progress.update(task, description=f"[bold red] ❌ Failed to install service: {e}[/bold red]")
            return

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as prog:
        task = prog.add_task("[cyan]Starting service...", total=None)
        try:
            if sys_name == "Windows":
                subprocess.run(["sc", "start", "PyMonitor"], check=True, capture_output=True)
            elif sys_name == "Linux":
                subprocess.run(["systemctl", "start", "pymonitor"], check=True, capture_output=True)

            time.sleep(1)  # Give it a moment to start

            # Verify it's running
            is_running = False
            if sys_name == "Windows":
                res = subprocess.run(["sc", "query", "PyMonitor"], capture_output=True, text=True)
                is_running = "RUNNING" in res.stdout
            elif sys_name == "Linux":
                res = subprocess.run(["systemctl", "is-active", "pymonitor"], capture_output=True, text=True)
                is_running = res.stdout.strip() == "active"

            if is_running:
                prog.update(task, description="[bold green]✔ Service is now running in the background![/bold green]")
            else:
                prog.update(
                    task,
                    description="[bold red] ❌ Service failed to start or immediately exited. Check logs.[/bold red]",
                )
        except subprocess.CalledProcessError as exc:
            err_msg = exc.stderr.decode("utf-8", errors="ignore") if exc.stderr else str(exc)
            prog.update(task, description=f"[bold red] ❌ Failed to start service: {err_msg}[/bold red]")


if __name__ == "__main__":
    app()
