"""JARVIS Deep System Diagnostics module.

Uses psutil to gather and report deep system metrics.
"""
from __future__ import annotations

import datetime
import logging
import platform
import socket

import psutil

from shared.schemas import CommandResult, Severity

logger = logging.getLogger(__name__)

def _human_size(nbytes: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(nbytes) < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024
    return f"{nbytes:.1f} PB"

def system_scan(query: str) -> CommandResult:
    """Comprehensive system report."""
    try:
        # CPU
        cpu_phys = psutil.cpu_count(logical=False)
        cpu_log = psutil.cpu_count(logical=True)
        cpu_freq = psutil.cpu_freq()
        cpu_pct = psutil.cpu_percent(interval=0.5)
        
        # RAM
        mem = psutil.virtual_memory()
        
        # Disk
        disk = psutil.disk_usage('/')
        
        # Network
        net = psutil.net_io_counters()
        
        # Uptime
        boot = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot
        
        # Health Score
        score = 100
        if cpu_pct > 80:
            score -= 20
        if mem.percent > 85:
            score -= 20
        if disk.percent > 90:
            score -= 15
        score = max(0, score)
        
        report = (
            f"--- SYSTEM SCAN REPORT (Health: {score}/100) ---\n"
            f"OS: {platform.system()} {platform.release()}\n"
            f"Uptime: {str(uptime).split('.')[0]}\n\n"
            f"CPU: {cpu_pct}% ({cpu_phys} Cores / {cpu_log} Threads"
        )
        if cpu_freq:
            report += f" @ {cpu_freq.current:.0f}MHz)"
        else:
            report += ")"
            
        report += (
            f"\nRAM: {mem.percent}% used ({_human_size(mem.used)} / {_human_size(mem.total)})\n"
            f"System Drive: {disk.percent}% used ({_human_size(disk.used)} / {_human_size(disk.total)})\n"
            f"Network: {(_human_size(net.bytes_sent))} TX / {(_human_size(net.bytes_recv))} RX"
        )
        
        severity = Severity.SUCCESS if score > 80 else (Severity.WARNING if score > 50 else Severity.ERROR)
        
        return CommandResult(text=report, severity=severity, source="diagnostics")
        
    except Exception as exc:
        logger.error("System scan failed: %s", exc)
        return CommandResult(
            text=f"Diagnostics failed: {exc}", 
            severity=Severity.ERROR, 
            source="diagnostics"
        )

def top_processes(query: str) -> CommandResult:
    """Top 10 processes by CPU usage."""
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
            try:
                # Need to call cpu_percent twice to get meaningful metric
                p.info['cpu_percent'] = p.cpu_percent(interval=0.01)
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
                
        # Sort by CPU desc
        procs.sort(key=lambda p: p['cpu_percent'], reverse=True)
        
        report = "--- TOP 10 PROCESSES ---\n"
        report += f"{'PID':<8} | {'CPU%':<6} | {'RAM%':<6} | {'NAME'}\n"
        report += "-" * 40 + "\n"
        
        for p in procs[:10]:
            report += f"{p['pid']:<8} | {p['cpu_percent']:<6.1f} | {p['memory_percent'] or 0:<6.1f} | {p['name']}\n"
            
        return CommandResult(text=report.strip(), source="diagnostics")
        
    except Exception as exc:
        logger.error("Top processes failed: %s", exc)
        return CommandResult(
            text=f"Failed to fetch processes: {exc}", 
            severity=Severity.ERROR, 
            source="diagnostics"
        )

def network_check(query: str) -> CommandResult:
    """Network interface summary."""
    try:
        report = "--- NETWORK DIAGNOSTICS ---\n"
        
        # Test DNS resolution
        try:
            socket.gethostbyname('google.com')
            report += "Internet Connection: ONLINE\n\n"
        except socket.error:
            report += "Internet Connection: OFFLINE (DNS failed)\n\n"
            
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        io = psutil.net_io_counters(pernic=True)
        
        for nic_name, nic_addrs in addrs.items():
            if nic_name in stats and stats[nic_name].isup:
                ip4 = next((a.address for a in nic_addrs if a.family == socket.AF_INET), "No IP")
                report += f"Interface: {nic_name} ({ip4})\n"
                if nic_name in io:
                    report += f"  TX: {_human_size(io[nic_name].bytes_sent)} | RX: {_human_size(io[nic_name].bytes_recv)}\n"
                    
        return CommandResult(text=report.strip(), source="diagnostics")
        
    except Exception as exc:
        logger.error("Network check failed: %s", exc)
        return CommandResult(
            text=f"Failed to check network: {exc}", 
            severity=Severity.ERROR, 
            source="diagnostics"
        )
