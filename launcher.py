import tkinter as tk
from tkinter import messagebox
import subprocess
import os
import time
import sys
import urllib.request
import urllib.error

# --- CONFIGURATION ---
APP_SCRIPT = "app.py"
GENERATE_PAGE_URL = "http://localhost:5000/generate" 

# Cloudflare command (Agar use kar rahe ho to)
CLOUDFLARE_CMD = ["cloudflared", "tunnel", "run", "gen-tunnel"] 

class FactoryLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("Touch Kiosk Boot")
        self.root.geometry("400x250")
        
        self.app_process = None
        self.tunnel_process = None
        self.is_running = False

        # Status Label
        self.status_label = tk.Label(root, text="Booting Factory System...", font=("Arial", 16, "bold"), fg="orange")
        self.status_label.pack(pady=40)
        
        tk.Label(root, text="(Touch Optimized)", font=("Arial", 10), fg="grey").pack()

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        # --- AUTO-START SEQUENCE ---
        # 1. Wait 10s for Wi-Fi/System (Pi needs this)
        self.count_down(10)

    def count_down(self, seconds):
        if seconds > 0:
            self.status_label.config(text=f"Waiting for System: {seconds}s 📡")
            self.root.after(1000, lambda: self.count_down(seconds - 1))
        else:
            self.start_system()

    def start_system(self):
        if self.is_running: return
        
        try:
            # 1. Start Python App FIRST
            self.status_label.config(text="Starting Server... 🚀", fg="blue")
            self.root.update()
            
            # Force Working Directory
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self.app_process = subprocess.Popen([sys.executable, APP_SCRIPT], cwd=script_dir)
            
            # 2. Check Readiness
            self.check_app_readiness(retries=30)

        except Exception as e:
            self.status_label.config(text=f"Error: {e}", fg="red")

    def check_app_readiness(self, retries):
        """Pings localhost to check if server is running"""
        try:
            with urllib.request.urlopen("http://localhost:5000", timeout=1) as response:
                if response.status == 200:
                    self.launch_kiosk_browser()
                    self.launch_tunnel()
                    return
        except (urllib.error.URLError, ConnectionRefusedError):
            pass

        if retries > 0:
            self.status_label.config(text=f"Loading Server... ({retries})")
            self.root.after(1000, lambda: self.check_app_readiness(retries - 1))
        else:
            self.status_label.config(text="Server Failed ❌", fg="red")

    def launch_kiosk_browser(self):
        """
        Opens Chromium with TOUCHSCREEN optimized settings.
        """
        self.status_label.config(text="Launching Touch Interface... 👆", fg="green")
        self.root.update()
        
        try:
            # --- TOUCHSCREEN OPTIMIZED FLAGS ---
            cmd = [
                "chromium",
                "--kiosk",                       # Full Screen (No Address Bar)
                "--noerrdialogs",                # No Error Popups
                "--disable-infobars",            # No "Chrome is controlled..." bar
                "--check-for-update-interval=31536000", # No Updates
                
                # TOUCH SPECIFIC SETTINGS:
                "--overscroll-history-navigation=0", # IMPORTANT: Disable 'Swipe to Back'
                "--disable-pinch",                   # IMPORTANT: Disable 'Pinch to Zoom'
                "--touch-events=enabled",            # Force Touch Support
                "--disable-features=Translate",      # Disable Translate Popup
                
                GENERATE_PAGE_URL
            ]
            
            subprocess.Popen(cmd)
            
            # Hide Launcher Window
            self.root.iconify() 
            
        except Exception as e:
            messagebox.showerror("Browser Error", f"Chromium nahi mila: {e}")

    def launch_tunnel(self):
        try:
            self.tunnel_process = subprocess.Popen(CLOUDFLARE_CMD, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass

    def on_close(self):
        if self.app_process: self.app_process.terminate()
        if self.tunnel_process: self.tunnel_process.terminate()
        self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FactoryLauncher(root)
    root.mainloop()
