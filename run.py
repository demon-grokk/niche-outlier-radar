#!/usr/bin/env python3
"""Launcher for Niche Outlier Radar."""
import sys
import argparse
import uvicorn
from radar.db import init_db
from radar.seed_channels import seed_default_channels
from radar.scheduler import start_async_sync

def main():
    parser = argparse.ArgumentParser(description="Niche Outlier Radar")
    parser.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="Host address (default: 0.0.0.0)")
    parser.add_argument("--sync", action="store_true", help="Trigger background sync on launch")
    parser.add_argument("--init-only", action="store_true", help="Initialize database, seed channel catalog, and exit")
    args = parser.parse_args()

    print("=" * 60)
    print("📡 Initializing Niche Outlier Radar...")
    init_db()
    seeded = seed_default_channels()
    if seeded > 0:
        print(f"✅ Seeded {seeded} high-signal AI/Tech channels into catalog.")
    
    if args.init_only:
        print("✅ Database initialized successfully. Exiting (--init-only).")
        print("=" * 60)
        return
    
    if args.sync:
        print("⚡ Launching initial background sync...")
        start_async_sync()

    print(f"🚀 Outlier Radar running at http://localhost:{args.port}")
    print("=" * 60)

    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=True)

if __name__ == "__main__":
    main()
