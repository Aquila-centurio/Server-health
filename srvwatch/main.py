"""srvwatch — remote server health monitor."""

from __future__ import annotations

import argparse
import sys
import time

from rich.live import Live
from rich.text import Text

from .collector import collect
from .display import build_layout, make_live
from .history import History


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="srvwatch",
        description="Real-time terminal health dashboard for a remote server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  srvwatch 192.168.1.10
  srvwatch myserver.example.com -u root -p 2222
  srvwatch 10.0.0.5 -i 5
        """,
    )
    parser.add_argument("host", help="Remote host IP or hostname")
    parser.add_argument("-u", "--user", default="root", help="SSH username (default: root)")
    parser.add_argument("-p", "--port", type=int, default=22, help="SSH port (default: 22)")
    parser.add_argument("-i", "--interval", type=int, default=3, help="Refresh interval in seconds (default: 3)")
    parser.add_argument("-n", "--count", type=int, default=0, help="Number of samples then exit (0 = run forever)")
    return parser.parse_args()


def run() -> None:
    args = parse_args()
    hist = History(maxlen=60)
    sample = 0

    with make_live() as live:
        live.update(Text(f"  Connecting to {args.host}...", style="dim"))
        try:
            while True:
                metrics = collect(
                    host=args.host,
                    user=args.user,
                    port=args.port,
                )

                if not metrics.error:
                    hist.push(metrics.cpu, metrics.mem_percent, metrics.disk_percent)

                layout = build_layout(args.host, metrics, hist, args.interval)
                live.update(layout)

                sample += 1
                if args.count and sample >= args.count:
                    break

                time.sleep(args.interval)

        except KeyboardInterrupt:
            pass


def main() -> None:
    try:
        run()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()