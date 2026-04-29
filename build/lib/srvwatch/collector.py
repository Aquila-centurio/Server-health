"""Remote host data collection via SSH.

Strategy:
  1. Try python3 inline script — returns clean JSON, precise CPU delta
  2. Fallback to pure bash — parses /proc/* with awk/grep, works on any Linux
"""

import subprocess
import json
from dataclasses import dataclass, field
from typing import Optional


# ── Remote Python script ─────────────────────────────────────────────────────

PYTHON_SCRIPT = r"""
import json, time

def read(path):
    try:
        return open(path).read()
    except Exception:
        return ""

def cpu_percent():
    def stat():
        parts = open("/proc/stat").readline().split()
        idle = int(parts[4])
        total = sum(int(x) for x in parts[1:])
        return idle, total
    i1, t1 = stat()
    time.sleep(0.5)
    i2, t2 = stat()
    dt = t2 - t1
    return round((1 - (i2 - i1) / dt) * 100, 1) if dt else 0.0

def mem():
    d = {}
    for line in read("/proc/meminfo").splitlines():
        p = line.split()
        if len(p) >= 2:
            d[p[0].rstrip(":")] = int(p[1])
    total = d.get("MemTotal", 0) * 1024
    used  = (d.get("MemTotal", 0) - d.get("MemAvailable", 0)) * 1024
    return total, used

def disk():
    import shutil
    s = shutil.disk_usage("/")
    return s.total, s.used

def load_avg():
    parts = open("/proc/loadavg").read().split()
    return [float(parts[0]), float(parts[1]), float(parts[2])]

def uptime():
    secs = float(open("/proc/uptime").read().split()[0])
    d = int(secs // 86400); h = int((secs % 86400) // 3600); m = int((secs % 3600) // 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)

def os_info():
    info = {}
    for line in read("/etc/os-release").splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            info[k.strip()] = v.strip().strip('"')
    return info.get("PRETTY_NAME") or info.get("NAME", "Linux")

import platform
mt, mu = mem(); dt, du = disk()
print(json.dumps({
    "cpu": cpu_percent(), "mem_total": mt, "mem_used": mu,
    "disk_total": dt, "disk_used": du, "load_avg": load_avg(),
    "uptime": uptime(), "os": os_info(), "kernel": platform.release(),
    "collector": "python3",
}))
"""


# ── Remote bash script ───────────────────────────────────────────────────────
# Pure POSIX sh + awk/grep — no Python required.
# CPU delta: two reads of /proc/stat with a sleep 1 in between.

BASH_SCRIPT = r"""
set -e

# ── CPU delta ──────────────────────────────────────────────────────────────
read_cpu() {
    awk 'NR==1{print $2+$3+$4+$5+$6+$7+$8, $5}' /proc/stat
}
read1=$(read_cpu); sleep 1; read2=$(read_cpu)
cpu_total1=$(echo $read1 | awk '{print $1}')
cpu_idle1=$(echo  $read1 | awk '{print $2}')
cpu_total2=$(echo $read2 | awk '{print $1}')
cpu_idle2=$(echo  $read2 | awk '{print $2}')
cpu=$(awk "BEGIN{dt=$cpu_total2-$cpu_total1; di=$cpu_idle2-$cpu_idle1; \
           if(dt>0) printf \"%.1f\", (1-di/dt)*100; else print \"0.0\"}")

# ── Memory (kB → bytes) ───────────────────────────────────────────────────
mem_total_kb=$(awk '/^MemTotal:/{print $2}' /proc/meminfo)
mem_avail_kb=$(awk '/^MemAvailable:/{print $2}' /proc/meminfo)
mem_total=$((mem_total_kb * 1024))
mem_used=$(( (mem_total_kb - mem_avail_kb) * 1024 ))

# ── Disk / ────────────────────────────────────────────────────────────────
disk_line=$(df -B1 / | awk 'NR==2{print $2, $3}')
disk_total=$(echo $disk_line | awk '{print $1}')
disk_used=$(echo  $disk_line | awk '{print $2}')

# ── Load average ──────────────────────────────────────────────────────────
la=$(awk '{print $1, $2, $3}' /proc/loadavg)
la1=$(echo $la | awk '{print $1}')
la5=$(echo $la | awk '{print $2}')
la15=$(echo $la | awk '{print $3}')

# ── Uptime ────────────────────────────────────────────────────────────────
up_secs=$(awk '{printf "%d", $1}' /proc/uptime)
up_d=$((up_secs / 86400))
up_h=$(( (up_secs % 86400) / 3600 ))
up_m=$(( (up_secs % 3600) / 60 ))
uptime_str=""
[ $up_d -gt 0 ] && uptime_str="${up_d}d "
[ $up_h -gt 0 ] && uptime_str="${uptime_str}${up_h}h "
uptime_str="${uptime_str}${up_m}m"

# ── OS info ───────────────────────────────────────────────────────────────
os_name=$(grep -m1 '^PRETTY_NAME=' /etc/os-release 2>/dev/null \
          | sed 's/PRETTY_NAME=//;s/"//g')
[ -z "$os_name" ] && os_name=$(grep -m1 '^NAME=' /etc/os-release 2>/dev/null \
          | sed 's/NAME=//;s/"//g')
[ -z "$os_name" ] && os_name="Linux"

# ── Kernel ────────────────────────────────────────────────────────────────
kernel=$(uname -r)

# ── Output JSON ───────────────────────────────────────────────────────────
cat <<EOF
{"cpu":$cpu,"mem_total":$mem_total,"mem_used":$mem_used,"disk_total":$disk_total,"disk_used":$disk_used,"load_avg":[$la1,$la5,$la15],"uptime":"$uptime_str","os":"$os_name","kernel":"$kernel","collector":"bash"}
EOF
"""


# ── Dispatcher: try python3, fallback to bash ────────────────────────────────

DISPATCH_SCRIPT = r"""
if command -v python3 >/dev/null 2>&1; then
    python3 - <<'PYEOF'
""" + PYTHON_SCRIPT + r"""
PYEOF
else
    bash -s <<'BASHEOF'
""" + BASH_SCRIPT + r"""
BASHEOF
fi
"""


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class HostMetrics:
    cpu: float = 0.0
    mem_total: int = 0
    mem_used: int = 0
    disk_total: int = 0
    disk_used: int = 0
    load_avg: list = field(default_factory=lambda: [0.0, 0.0, 0.0])
    uptime: str = "unknown"
    os: str = "Linux"
    kernel: str = "unknown"
    collector: str = "unknown"   # "python3" or "bash"
    error: Optional[str] = None

    @property
    def mem_percent(self) -> float:
        return (self.mem_used / self.mem_total * 100) if self.mem_total else 0.0

    @property
    def disk_percent(self) -> float:
        return (self.disk_used / self.disk_total * 100) if self.disk_total else 0.0


# ── SSH collection ───────────────────────────────────────────────────────────
def collect_local() -> HostMetrics:
    """Collect metrics from local machine directly, no SSH."""
    import platform, time

    def read(path):
        try:
            return open(path).read()
        except Exception:
            return ""

    def cpu_percent():
        def stat():
            parts = open("/proc/stat").readline().split()
            idle = int(parts[4])
            total = sum(int(x) for x in parts[1:])
            return idle, total
        i1, t1 = stat(); time.sleep(0.5); i2, t2 = stat()
        dt = t2 - t1
        return round((1 - (i2 - i1) / dt) * 100, 1) if dt else 0.0

    def mem():
        d = {}
        for line in read("/proc/meminfo").splitlines():
            p = line.split()
            if len(p) >= 2:
                d[p[0].rstrip(":")] = int(p[1])
        total = d.get("MemTotal", 0) * 1024
        used = (d.get("MemTotal", 0) - d.get("MemAvailable", 0)) * 1024
        return total, used

    def disk():
        import shutil
        s = shutil.disk_usage("/")
        return s.total, s.used

    def uptime():
        secs = float(open("/proc/uptime").read().split()[0])
        d = int(secs // 86400); h = int((secs % 86400) // 3600); m = int((secs % 3600) // 60)
        parts = []
        if d: parts.append(f"{d}d")
        if h: parts.append(f"{h}h")
        parts.append(f"{m}m")
        return " ".join(parts)

    def os_info():
        info = {}
        for line in read("/etc/os-release").splitlines():
            if "=" in line:
                k, _, v = line.partition("=")
                info[k.strip()] = v.strip().strip('"')
        return info.get("PRETTY_NAME") or info.get("NAME", "Linux")

    la = open("/proc/loadavg").read().split()
    mt, mu = mem(); dt, du = disk()

    return HostMetrics(
        cpu=cpu_percent(),
        mem_total=mt, mem_used=mu,
        disk_total=dt, disk_used=du,
        load_avg=[float(la[0]), float(la[1]), float(la[2])],
        uptime=uptime(),
        os=os_info(),
        kernel=platform.release(),
        collector="local",
    )
    
    
def collect(
    
    
    host: str,
    user: Optional[str] = None,
    port: int = 22,
    timeout: int = 15,
) -> HostMetrics:
    """Collect metrics from a remote host via SSH.

    Tries python3 first; falls back to pure bash automatically.
    """
    
    if host in ("localhost", "127.0.0.1", "::1"):
        return collect_local()
    
    target = f"{user}@{host}" if user else host

    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        "-p", str(port),
        target,
        "bash -s",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=DISPATCH_SCRIPT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        if result.returncode != 0:
            lines = result.stderr.strip().splitlines()
            msg = lines[-1] if lines else f"SSH exited with code {result.returncode}"
            return HostMetrics(error=msg)

        # Find the JSON line (skip any ssh banners / warnings)
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.startswith("{"):
                data = json.loads(line)
                return HostMetrics(**data)

        return HostMetrics(error="No JSON received from host")

    except subprocess.TimeoutExpired:
        return HostMetrics(error=f"Timed out after {timeout}s")
    except FileNotFoundError:
        return HostMetrics(error="'ssh' not found in PATH")
    except json.JSONDecodeError as e:
        return HostMetrics(error=f"JSON parse error: {e}")
    except Exception as e:
        return HostMetrics(error=str(e))