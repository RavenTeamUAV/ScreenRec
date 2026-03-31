import tkinter as tk
from tkinter import messagebox
import cv2
import numpy as np
import pygetwindow as gw
from PIL import ImageGrab
import threading
from datetime import datetime
from pynput import keyboard
import socket
import sys
import os

_lock_socket = None

def acquire_single_instance_lock():
    global _lock_socket
    _lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        _lock_socket.bind(('127.0.0.1', 47892))
    except OSError:
        messagebox.showerror("ScreenRec", "Програма вже запущена!")
        sys.exit(0)

class ScreenRecorder:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Rec")

        # Іконка вікна
        try:
            icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icon.ico")
            self.root.iconbitmap(icon_path)
        except Exception:
            pass
        
        # Параметри вікна
        self.root.attributes('-topmost', True)
        self.root.overrideredirect(True)
        
        # Початкові розміри
        self.normal_width = 100
        self.normal_height = 40
        self.dot_size = 15
        
        screen_width = self.root.winfo_screenwidth()
        self.x = int(screen_width/2 - self.normal_width/2)
        self.y = 0
        
        self.root.geometry(f"{self.normal_width}x{self.normal_height}+{self.x}+{self.y}")

        self.is_recording = False
        self.out = None
        self.blink_state = True
        self.target_win = None
        
        # Кнопка
        self.btn = tk.Button(self.root, text="REC (F9)", bg="red", fg="white", 
                             command=self.toggle_recording, font=("Segoe UI", 10, "bold"))
        self.btn.pack(fill=tk.BOTH, expand=True)

        # Глобальна гаряча клавіша
        hotkey = keyboard.GlobalHotKeys({'<f9>': self.toggle_recording})
        hotkey.start()

    def toggle_recording(self):
        if not self.is_recording:
            self.root.after(0, self.start_recording)
        else:
            self.root.after(0, self.stop_recording)

    def start_recording(self):
        if self.is_recording: return

        # Шукаємо вікно OmniViewerHD
        wins = gw.getWindowsWithTitle('OmniViewerHD')
        if not wins:
            messagebox.showerror("ScreenRec", "Вікно OmniViewerHD не знайдено!\nЗапустіть програму і спробуйте ще раз.")
            return
        self.target_win = wins[0]

        self.is_recording = True

        # Згортаємо у точку
        self.root.geometry(f"{self.dot_size}x{self.dot_size}+{self.x}+{self.y}")
        self.btn.config(text="", bg="green")

        # Налаштування файлу — розмір під вікно OmniViewerHD
        save_dir = os.path.join(os.path.expanduser("~"), "Desktop", "ScreenRec")
        os.makedirs(save_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = os.path.join(save_dir, f"record_{timestamp}.mp4")
        win_size = (self.target_win.width, self.target_win.height)
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self.out = cv2.VideoWriter(filename, fourcc, 20.0, win_size)

        # Запуск фонових процесів
        threading.Thread(target=self.record_loop, daemon=True).start()
        self.blink()
        print(f"Запис почато: {filename}")

    def blink(self):
        if self.is_recording:
            color = "#00FF00" if self.blink_state else "#006400" # Яскраво-зелений / Темно-зелений
            self.btn.config(bg=color)
            self.blink_state = not self.blink_state
            self.root.after(1000, self.blink)

    def record_loop(self):
        while self.is_recording:
            try:
                bbox = (
                    self.target_win.left,
                    self.target_win.top,
                    self.target_win.right,
                    self.target_win.bottom,
                )
                img = ImageGrab.grab(bbox=bbox)
            except Exception:
                break
            frame = np.array(img.convert('RGB'))
            frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
            if self.out:
                self.out.write(frame)
        
        if self.out:
            self.out.release()
            self.out = None

    def stop_recording(self):
        if not self.is_recording: return
        self.is_recording = False
        
        # Повертаємо нормальний розмір вікна
        self.root.geometry(f"{self.normal_width}x{self.normal_height}+{self.x}+{self.y}")
        self.btn.config(bg="red", text="REC (F9)")
        print("Запис зупинено та збережено.")

    def move_window(self, event):
        # Оновлюємо координати при перетягуванні
        self.x = event.x_root
        self.y = event.y_root
        self.root.geometry(f"+{self.x}+{self.y}")

    def run(self):
        self.root.bind('<B3-Motion>', self.move_window)
        self.root.mainloop()

if __name__ == "__main__":
    acquire_single_instance_lock()
    app = ScreenRecorder()
    app.run()