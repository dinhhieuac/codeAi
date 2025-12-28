#!/usr/bin/env python3
"""
Script to run multiple dashboards simultaneously
- XAU_M1 Dashboard: http://127.0.0.1:5000
- BTC_M1 Dashboard: http://127.0.0.1:5001
- ETH_M1 Dashboard: http://127.0.0.1:5002
"""

import sys
import os
import threading
from pathlib import Path

# Add parent directory to path to import dashboard modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def run_xau_dashboard():
    """Run XAU_M1 dashboard on port 5000"""
    try:
        # Import XAU dashboard module
        xau_dashboard_path = project_root / "XAU_M1"
        sys.path.insert(0, str(xau_dashboard_path))
        import importlib.util
        spec = importlib.util.spec_from_file_location("xau_dashboard", xau_dashboard_path / "dashboard.py")
        xau_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xau_module)
        
        print("🚀 Starting XAU_M1 Dashboard on http://127.0.0.1:5000")
        xau_module.app.run(debug=False, port=5000, host='127.0.0.1', use_reloader=False)
    except Exception as e:
        print(f"❌ Error starting XAU_M1 Dashboard: {e}")
        import traceback
        traceback.print_exc()

def run_btc_dashboard():
    """Run BTC_M1 dashboard on port 5001"""
    try:
        # Import BTC dashboard module
        btc_dashboard_path = project_root / "BTC_M1"
        sys.path.insert(0, str(btc_dashboard_path))
        import importlib.util
        spec = importlib.util.spec_from_file_location("btc_dashboard", btc_dashboard_path / "dashboard.py")
        btc_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(btc_module)
        
        print("🚀 Starting BTC_M1 Dashboard on http://127.0.0.1:5001")
        btc_module.app.run(debug=False, port=5001, host='127.0.0.1', use_reloader=False)
    except Exception as e:
        print(f"❌ Error starting BTC_M1 Dashboard: {e}")
        import traceback
        traceback.print_exc()

def run_eth_dashboard():
    """Run ETH_M1 dashboard on port 5002"""
    try:
        # Import ETH dashboard module
        eth_dashboard_path = project_root / "ETH_M1"
        sys.path.insert(0, str(eth_dashboard_path))
        import importlib.util
        spec = importlib.util.spec_from_file_location("eth_dashboard", eth_dashboard_path / "dashboard.py")
        eth_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eth_module)
        
        print("🚀 Starting ETH_M1 Dashboard on http://127.0.0.1:5002")
        eth_module.app.run(debug=False, port=5002, host='127.0.0.1', use_reloader=False)
    except Exception as e:
        print(f"❌ Error starting ETH_M1 Dashboard: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    print("=" * 60)
    print("📊 MULTI-DASHBOARD LAUNCHER")
    print("=" * 60)
    print()
    
    # Create threads for each dashboard
    xau_thread = threading.Thread(target=run_xau_dashboard, daemon=True)
    btc_thread = threading.Thread(target=run_btc_dashboard, daemon=True)
    eth_thread = threading.Thread(target=run_eth_dashboard, daemon=True)
    
    # Start all threads
    xau_thread.start()
    btc_thread.start()
    eth_thread.start()
    
    print()
    print("✅ All dashboards are starting...")
    print()
    print("📍 XAU_M1 Dashboard: http://127.0.0.1:5000")
    print("📍 BTC_M1 Dashboard: http://127.0.0.1:5001")
    print("📍 ETH_M1 Dashboard: http://127.0.0.1:5002")
    print()
    print("Press Ctrl+C to stop all dashboards")
    print("=" * 60)
    print()
    
    try:
        # Keep main thread alive
        while True:
            xau_thread.join(timeout=1)
            btc_thread.join(timeout=1)
            eth_thread.join(timeout=1)
            if not xau_thread.is_alive() and not btc_thread.is_alive() and not eth_thread.is_alive():
                print("⚠️ All dashboards have stopped")
                break
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down dashboards...")
        print("✅ Dashboards stopped")
        sys.exit(0)

