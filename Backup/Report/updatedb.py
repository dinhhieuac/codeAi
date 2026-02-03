#!/usr/bin/env python3
"""
Script to run multiple update_db scripts simultaneously
- XAU_M1/update_db.py
- BTC_M1/update_db.py
- ETH_M1/update_db.py

Each script updates trade profits from MT5 history for their respective strategies.
"""

import sys
import os
import threading
import subprocess
from pathlib import Path

# Add parent directory to path to import update_db modules
project_root = Path(__file__).parent.parent

def run_xau_update():
    """Run XAU_M1 update_db.py using subprocess"""
    import subprocess
    try:
        xau_script = project_root / "XAU_M1" / "update_db.py"
        
        if not xau_script.exists():
            print(f"❌ Script not found: {xau_script}")
            return
        
        print("🚀 Starting XAU_M1 update_db...")
        # Run the script as a subprocess (it has its own while True loop)
        process = subprocess.Popen(
            [sys.executable, str(xau_script)],
            cwd=str(xau_script.parent)  # Set working directory to XAU_M1
        )
        
        # Wait for process to complete (it runs forever until Ctrl+C)
        process.wait()
    except KeyboardInterrupt:
        print("🛑 XAU_M1 update_db stopped")
        if 'process' in locals():
            process.terminate()
    except Exception as e:
        print(f"❌ Fatal error in XAU_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
        if 'process' in locals():
            process.terminate()

def run_btc_update():
    """Run BTC_M1 update_db.py using subprocess"""
    import subprocess
    try:
        btc_script = project_root / "BTC_M1" / "update_db.py"
        
        if not btc_script.exists():
            print(f"❌ Script not found: {btc_script}")
            return
        
        print("🚀 Starting BTC_M1 update_db...")
        # Run the script as a subprocess (it has its own while True loop)
        process = subprocess.Popen(
            [sys.executable, str(btc_script)],
            cwd=str(btc_script.parent)  # Set working directory to BTC_M1
        )
        
        # Wait for process to complete (it runs forever until Ctrl+C)
        process.wait()
    except KeyboardInterrupt:
        print("🛑 BTC_M1 update_db stopped")
        if 'process' in locals():
            process.terminate()
    except Exception as e:
        print(f"❌ Fatal error in BTC_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
        if 'process' in locals():
            process.terminate()

def run_eth_update():
    """Run ETH_M1 update_db.py using subprocess"""
    import subprocess
    try:
        eth_script = project_root / "ETH_M1" / "update_db.py"
        
        if not eth_script.exists():
            print(f"❌ Script not found: {eth_script}")
            return
        
        print("🚀 Starting ETH_M1 update_db...")
        # Run the script as a subprocess (it has its own while True loop)
        process = subprocess.Popen(
            [sys.executable, str(eth_script)],
            cwd=str(eth_script.parent)  # Set working directory to ETH_M1
        )
        
        # Wait for process to complete (it runs forever until Ctrl+C)
        process.wait()
    except KeyboardInterrupt:
        print("🛑 ETH_M1 update_db stopped")
        if 'process' in locals():
            process.terminate()
    except Exception as e:
        print(f"❌ Fatal error in ETH_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
        if 'process' in locals():
            process.terminate()

if __name__ == '__main__':
    print("=" * 60)
    print("🔄 MULTI-UPDATE_DB LAUNCHER")
    print("=" * 60)
    print()
    print("This script will run update_db.py for all trading pairs:")
    print("  • XAU_M1 (Gold)")
    print("  • BTC_M1 (Bitcoin)")
    print("  • ETH_M1 (Ethereum)")
    print()
    print("Each update script will:")
    print("  • Check MT5 for closed trades")
    print("  • Update profit in database")
    print("  • Run every 600 seconds (10 minutes)")
    print()
    print("Press Ctrl+C to stop all update scripts")
    print("=" * 60)
    print()
    
    # Create threads for each update script
    xau_thread = threading.Thread(target=run_xau_update, daemon=True)
    btc_thread = threading.Thread(target=run_btc_update, daemon=True)
    eth_thread = threading.Thread(target=run_eth_update, daemon=True)
    
    # Start all threads
    xau_thread.start()
    btc_thread.start()
    eth_thread.start()
    
    print("✅ All update scripts are starting...")
    print()
    
    try:
        # Keep main thread alive and monitor processes
        while True:
            xau_thread.join(timeout=1)
            btc_thread.join(timeout=1)
            eth_thread.join(timeout=1)
            if not xau_thread.is_alive() and not btc_thread.is_alive() and not eth_thread.is_alive():
                print("⚠️ All update scripts have stopped")
                break
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down update scripts...")
        # Note: Subprocesses will be terminated when threads exit
        print("✅ Update scripts stopped")
        sys.exit(0)

