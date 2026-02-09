import subprocess
import time
import sys
import os

def main():
    # Get the directory where main.py is located
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # List of strategy scripts to run
    scripts = [
        os.path.join(base_dir, "strategy_1_trend_ha.py"),
        os.path.join(base_dir, "strategy_2_ema_atr.py"),
        os.path.join(base_dir, "strategy_3_pa_volume.py"),
        os.path.join(base_dir, "strategy_4_ut_bot.py"),
        os.path.join(base_dir, "strategy_5_filter_first.py")
    ]

    processes = []
    
    print("🚀 Starting all 5 XAU_M1 Bots...")
    print(f"📂 Execution Directory: {base_dir}")

    try:
        for script in scripts:
            print(f"   ▶️ Launching {script}...")
            # Launch as a separate process
            # use sys.executable to ensure we use the same python interpreter
            p = subprocess.Popen([sys.executable, script])
            processes.append(p)
            time.sleep(2) # Add small delay between launches to avoid init conflicts

        print("\n✅ All bots are running!")
        print("Press Ctrl+C to stop all bots.\n")

        # Keep main process alive to monitor
        while True:
            time.sleep(1)
            # Check if any process has died
            for i, p in enumerate(processes):
                if p.poll() is not None:
                    print(f"⚠️ Process {scripts[i]} ended unexpected (Code: {p.returncode})")
                    # Optional: Restart logic could go here
                    
    except KeyboardInterrupt:
        print("\n🛑 Stopping all bots...")
        for p in processes:
            p.terminate()
        print("✅ All processes terminated.")

if __name__ == "__main__":
    main()
