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
from pathlib import Path

# Add parent directory to path to import update_db modules
project_root = Path(__file__).parent.parent

def run_xau_update():
    """Run XAU_M1 update_db.py in a loop"""
    import time
    try:
        # Save current directory
        original_dir = os.getcwd()
        xau_dir = project_root / "XAU_M1"
        
        # Change to XAU_M1 directory to ensure correct imports and DB paths
        os.chdir(str(xau_dir))
        sys.path.insert(0, str(xau_dir))
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("xau_update_db", xau_dir / "update_db.py")
        xau_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(xau_module)
        
        print("🚀 Starting XAU_M1 update_db...")
        # Run in loop like the original script
        while True:
            try:
                xau_module.main()
                print("⏳ XAU_M1: Sleeping for 600 seconds...")
                time.sleep(600)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Error in XAU_M1 update_db loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    except KeyboardInterrupt:
        print("🛑 XAU_M1 update_db stopped")
    except Exception as e:
        print(f"❌ Fatal error in XAU_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original directory
        try:
            os.chdir(original_dir)
        except:
            pass

def run_btc_update():
    """Run BTC_M1 update_db.py in a loop"""
    import time
    try:
        # Save current directory
        original_dir = os.getcwd()
        btc_dir = project_root / "BTC_M1"
        
        # Change to BTC_M1 directory to ensure correct imports and DB paths
        os.chdir(str(btc_dir))
        sys.path.insert(0, str(btc_dir))
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("btc_update_db", btc_dir / "update_db.py")
        btc_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(btc_module)
        
        print("🚀 Starting BTC_M1 update_db...")
        # Run in loop like the original script
        while True:
            try:
                btc_module.main()
                print("⏳ BTC_M1: Sleeping for 600 seconds...")
                time.sleep(600)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Error in BTC_M1 update_db loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    except KeyboardInterrupt:
        print("🛑 BTC_M1 update_db stopped")
    except Exception as e:
        print(f"❌ Fatal error in BTC_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original directory
        try:
            os.chdir(original_dir)
        except:
            pass

def run_eth_update():
    """Run ETH_M1 update_db.py in a loop"""
    import time
    try:
        # Save current directory
        original_dir = os.getcwd()
        eth_dir = project_root / "ETH_M1"
        
        # Change to ETH_M1 directory to ensure correct imports and DB paths
        os.chdir(str(eth_dir))
        sys.path.insert(0, str(eth_dir))
        
        import importlib.util
        spec = importlib.util.spec_from_file_location("eth_update_db", eth_dir / "update_db.py")
        eth_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(eth_module)
        
        print("🚀 Starting ETH_M1 update_db...")
        # Run in loop like the original script
        while True:
            try:
                eth_module.main()
                print("⏳ ETH_M1: Sleeping for 600 seconds...")
                time.sleep(600)
            except KeyboardInterrupt:
                raise
            except Exception as e:
                print(f"❌ Error in ETH_M1 update_db loop: {e}")
                time.sleep(60)  # Wait 1 minute before retrying
    except KeyboardInterrupt:
        print("🛑 ETH_M1 update_db stopped")
    except Exception as e:
        print(f"❌ Fatal error in ETH_M1 update_db: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Restore original directory
        try:
            os.chdir(original_dir)
        except:
            pass

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
        # Keep main thread alive
        while True:
            xau_thread.join(timeout=1)
            btc_thread.join(timeout=1)
            eth_thread.join(timeout=1)
            if not xau_thread.is_alive() and not btc_thread.is_alive() and not eth_thread.is_alive():
                print("⚠️ All update scripts have stopped")
                break
    except KeyboardInterrupt:
        print("\n\n🛑 Shutting down update scripts...")
        print("✅ Update scripts stopped")
        sys.exit(0)

