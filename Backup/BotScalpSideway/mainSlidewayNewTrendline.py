"""
Main file để chạy tất cả các bot Slideway New Trendline
Chạy nhiều bot cùng lúc với các config khác nhau

Usage:
    python mainSlidewayNewTrendline.py
"""

import subprocess
import time
import sys
import os

def main():
    # Get the directory where mainSlidewayNewTrendline.py is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # List of config files to run
    configs = [
        os.path.join(base_dir, "configs", "slideway_newtrendline_eur.json"),   # EURUSD
        os.path.join(base_dir, "configs", "slideway_newtrendline_xau.json"),  # XAUUSD
        os.path.join(base_dir, "configs", "slideway_newtrendline_btc.json"),   # BTCUSD
    ]
    
    # Bot script path
    bot_script = os.path.join(base_dir, "slideway_newtrendline.py")
    
    processes = []
    
    print("="*80)
    print("🚀 Starting Slideway New Trendline Bots...")
    print("="*80)
    print(f"📂 Execution Directory: {base_dir}")
    print(f"🤖 Bot Script: {bot_script}")
    print(f"📋 Config Files: {len(configs)}")
    print("="*80)
    print()
    
    # Check if bot script exists
    if not os.path.exists(bot_script):
        print(f"❌ Bot script not found: {bot_script}")
        sys.exit(1)
    
    try:
        for i, config in enumerate(configs, 1):
            # Check if config file exists
            if not os.path.exists(config):
                print(f"⚠️ Config file not found: {config}")
                print(f"   Skipping...")
                continue
            
            config_name = os.path.basename(config)
            print(f"   [{i}/{len(configs)}] ▶️ Launching bot với config: {config_name}")
            
            # Launch as a separate process
            # use sys.executable to ensure we use the same python interpreter
            p = subprocess.Popen([sys.executable, bot_script, config])
            processes.append({
                'process': p,
                'config': config_name,
                'script': bot_script
            })
            
            # Add small delay between launches to avoid init conflicts
            time.sleep(2)
        
        if len(processes) == 0:
            print("❌ No valid config files found. Exiting...")
            sys.exit(1)
        
        print()
        print("="*80)
        print(f"✅ {len(processes)} bot(s) đang chạy!")
        print("="*80)
        print("📊 Danh sách bots đang chạy:")
        for i, proc_info in enumerate(processes, 1):
            print(f"   {i}. {proc_info['config']} (PID: {proc_info['process'].pid})")
        print()
        print("⚠️  Nhấn Ctrl+C để dừng tất cả bots.")
        print("="*80)
        print()
        
        # Keep main process alive to monitor
        while True:
            time.sleep(5)  # Check every 5 seconds
            # Check if any process has died
            for i, proc_info in enumerate(processes):
                p = proc_info['process']
                if p.poll() is not None:
                    config_name = proc_info['config']
                    return_code = p.returncode
                    print(f"⚠️ [{time.strftime('%Y-%m-%d %H:%M:%S')}] Bot '{config_name}' đã dừng (Exit Code: {return_code})")
                    
    except KeyboardInterrupt:
        print()
        print("="*80)
        print("🛑 Đang dừng tất cả bots...")
        print("="*80)
        
        for proc_info in processes:
            p = proc_info['process']
            config_name = proc_info['config']
            try:
                if p.poll() is None:  # Process is still running
                    print(f"   ⏹️  Dừng bot: {config_name} (PID: {p.pid})")
                    p.terminate()
                    # Wait a bit for graceful shutdown
                    try:
                        p.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        print(f"   ⚠️  Force killing bot: {config_name}")
                        p.kill()
            except Exception as e:
                print(f"   ❌ Lỗi khi dừng bot {config_name}: {e}")
        
        print()
        print("✅ Tất cả processes đã được dừng.")
        print("="*80)
        
    except Exception as e:
        print(f"\n❌ Lỗi không mong muốn: {e}")
        import traceback
        traceback.print_exc()
        
        # Try to cleanup
        print("\n🛑 Đang dừng tất cả bots...")
        for proc_info in processes:
            try:
                proc_info['process'].terminate()
            except:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
