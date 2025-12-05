import tkinter as tk
from tkinter import messagebox
import subprocess
import threading
import sys
import os
import signal
import webbrowser
import time

# --- CONFIGURATION ---
PYTHON_CMD = "python"
APP_SCRIPT = "app.py"
# Tumhara permanent domain
PERMANENT_URL = "https://app.bhaijiproducts.online" 

class FactoryLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title("PVC Factory Control Panel (Live Domain)")
        self.root.geometry("550x300")
        self.root.configure(bg="#f0f2f5")
        
        # Variables
        self.server_process = None
        self.is_running = False

        # --- UI Elements ---
        self.header = tk.Label(root, text="少 PVC PRO System (Live Domain)", font=("Arial", 16, "bold"), bg="#f0f2f5", fg="#333")
        self.header.pack(pady=10)

        self.status_label = tk.Label(root, text="Status: STOPPED 閥", font=("Arial", 14), bg="#f0f2f5", fg="red")
        self.status_label.pack(pady=5)

        self.url_label = tk.Label(root, text=f"倹 Admin Link: {PERMANENT_URL}/admin", font=("Consolas", 12), bg="#e1e4e8", padx=10, pady=5, fg="#2563eb", cursor="hand2")
        self.url_label.pack(pady=10, fill="x", padx=30)
        self.url_label.bind("<Button-1>", lambda e: self.open_link(f"{PERMANENT_URL}/admin"))

        self.btn_start = tk.Button(root, text="START PYTHON SERVER", command=self.start_system, font=("Arial", 12, "bold"), bg="#10b981", fg="white", width=30, height=2)
        self.btn_start.pack(pady=10)

        self.btn_stop = tk.Button(root, text="STOP SERVER", command=self.stop_system, font=("Arial", 12, "bold"), bg="#ef4444", fg="white", width=30, height=2, state="disabled")
        self.btn_stop.pack(pady=5)

        tk.Label(root, text="Tunnel (Cloudflare) is running automatically as a Windows Service.", font=("Arial", 9), bg="#f0f2f5", fg="#64748b").pack(pady=10)

        # Handle window close
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_link(self, url):
        """Opens the permanent URL in the default web browser."""
        if self.is_running:
            webbrowser.open_new(url)
        else:
            messagebox.showwarning("System Offline", "Please start the Python Server first.")

    def start_system(self):
        if self.is_running: return
        
        self.status_label.config(text="Status: STARTING PYTHON... 泯", fg="orange")
        self.btn_start.config(state="disabled")
        
        # Start Flask Server (app.py)
        try:
            # We use subprocess.DETACHED_PROCESS to run it in the background
            self.server_process = subprocess.Popen(
                [PYTHON_CMD, APP_SCRIPT],
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NO_WINDOW
            )
            # Give server a moment to boot
            time.sleep(2) 
        except Exception as e:
            messagebox.showerror("Error", f"Failed to start app.py: {e}\nCheck if Python is in your system PATH.")
            self.stop_system()
            return

        self.is_running = True
        self.btn_stop.config(state="normal")
        self.status_label.config(text="Status: RUNNING 泙 (Open Link Above)", fg="green")
        self.btn_start.config(text="SERVER IS ACTIVE", bg="#059669")
        
        # Open browser automatically after starting server
        self.open_link(f"{PERMANENT_URL}/admin")


    def stop_system(self):
        if not self.is_running: return
        
        # Killing the Python process safely (using its PID)
        try:
            # Note: Since we used DETACHED_PROCESS, we need taskkill
            subprocess.call(['taskkill', '/F', '/T', '/PID', str(self.server_process.pid)], creationflags=subprocess.CREATE_NO_WINDOW)
            
        except Exception as e:
            # Handle if process already died
            print(f"Error stopping process: {e}")
            pass
        
        self.server_process = None

        self.is_running = False
        self.btn_start.config(state="normal", text="START PYTHON SERVER", bg="#10b981")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="Status: STOPPED 閥", fg="red")

    def on_close(self):
        if self.is_running:
            if messagebox.askokcancel("Quit", "Server is running. Do you want to stop it and exit?"):
                self.stop_system()
                self.root.destroy()
        else:
            self.root.destroy()

if __name__ == "__main__":
    root = tk.Tk()
    app = FactoryLauncher(root)
    root.mainloop()
