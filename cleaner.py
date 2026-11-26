"""
Smart Windows Cleaner & Booster v1.2 (Minimal)
================================================
Установка:  pip install customtkinter psutil
Запуск:     python main.py
Сборка:     pyinstaller --onefile --windowed --name "SmartCleaner" main.py
"""

import os
import sys
import json
import time
import ctypes
import subprocess
import threading
from datetime import datetime

import psutil
import customtkinter as ctk
from tkinter import messagebox

try:
    import winreg
except ImportError:
    winreg = None


# =============================================================
#  МИНИМАЛИСТИЧНАЯ ПАЛИТРА
# =============================================================
BG         = "#0a0a0a"
CARD       = "#131316"
CARD_HOVER = "#1a1a1e"
BORDER     = "#1f1f23"
TEXT       = "#f4f4f5"
MUTED      = "#71717a"
ACCENT     = "#5b8def"
ACCENT_H   = "#4a7ae0"
GREEN      = "#4cb782"
GREEN_H    = "#3ea36d"
RED        = "#ef4444"
YELLOW     = "#eab308"

WINDOW_W, WINDOW_H = 1040, 700

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(sys.executable)
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))

DISABLED_FILE    = os.path.join(APP_DIR, "disabled_autostart.json")
CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0
PARTIAL_EXTS     = {".crdownload", ".part", ".tmp", ".download",
                    ".opdownload", ".partial"}
RUN_KEY          = r"Software\Microsoft\Windows\CurrentVersion\Run"


# =============================================================
#  УТИЛИТЫ
# =============================================================
def format_bytes(n):
    if n is None or n <= 0:
        return "0 Б"
    n = float(n)
    for unit in ["Б", "КБ", "МБ", "ГБ", "ТБ"]:
        if n < 1024.0:
            if unit == "Б":
                return f"{int(n)} Б"
            return f"{n:.1f} {unit}" if n >= 10 else f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.1f} ПБ"


def folder_size(path):
    if not path or not os.path.isdir(path):
        return 0
    total = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    total += entry.stat(follow_symlinks=False).st_size
                elif entry.is_dir(follow_symlinks=False):
                    total += folder_size(entry.path)
            except (PermissionError, OSError, FileNotFoundError):
                continue
    except (PermissionError, OSError):
        return 0
    return total


def delete_folder_contents(path):
    if not path or not os.path.isdir(path):
        return 0
    freed = 0
    try:
        for entry in os.scandir(path):
            try:
                if entry.is_file(follow_symlinks=False):
                    size = entry.stat(follow_symlinks=False).st_size
                    try:
                        os.unlink(entry.path)
                        freed += size
                    except (PermissionError, OSError):
                        pass
                elif entry.is_dir(follow_symlinks=False):
                    freed += delete_folder_contents(entry.path)
                    try:
                        os.rmdir(entry.path)
                    except (PermissionError, OSError):
                        pass
            except (PermissionError, OSError, FileNotFoundError):
                continue
    except (PermissionError, OSError):
        pass
    return freed


def scan_downloads_partial(path):
    if not path or not os.path.isdir(path):
        return 0
    total = 0
    try:
        for name in os.listdir(path):
            if os.path.splitext(name)[1].lower() in PARTIAL_EXTS:
                try:
                    full = os.path.join(path, name)
                    if os.path.isfile(full):
                        total += os.path.getsize(full)
                except (OSError, FileNotFoundError):
                    pass
    except (PermissionError, OSError):
        pass
    return total


def clean_downloads_partial(path):
    if not path or not os.path.isdir(path):
        return 0
    freed = 0
    try:
        for name in os.listdir(path):
            if os.path.splitext(name)[1].lower() in PARTIAL_EXTS:
                try:
                    full = os.path.join(path, name)
                    if os.path.isfile(full):
                        size = os.path.getsize(full)
                        os.unlink(full)
                        freed += size
                except (PermissionError, OSError, FileNotFoundError):
                    pass
    except (PermissionError, OSError):
        pass
    return freed


def empty_recycle_bin():
    try:
        flags = 0x00000001 | 0x00000002 | 0x00000004
        return ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags) == 0
    except Exception:
        return False


def recycle_bin_size():
    try:
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_ulong),
                        ("i64Size", ctypes.c_longlong),
                        ("i64NumItems", ctypes.c_longlong)]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        if ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info)) == 0:
            return int(info.i64Size)
    except Exception:
        pass
    return 0


def get_thumbcache_files():
    result = []
    base = os.path.join(os.environ.get("LOCALAPPDATA", ""),
                        "Microsoft", "Windows", "Explorer")
    if not os.path.isdir(base):
        return result
    try:
        for name in os.listdir(base):
            low = name.lower()
            if low.startswith("thumbcache_") and low.endswith(".db"):
                result.append(os.path.join(base, name))
    except (PermissionError, OSError):
        pass
    return result


def thumbcache_size():
    total = 0
    for f in get_thumbcache_files():
        try:
            total += os.path.getsize(f)
        except OSError:
            pass
    return total


def delete_thumbcache():
    freed = 0
    for f in get_thumbcache_files():
        try:
            size = os.path.getsize(f)
            os.unlink(f)
            freed += size
        except (PermissionError, OSError):
            pass
    return freed


def run_hidden(cmd, timeout=10):
    try:
        return subprocess.run(cmd, capture_output=True, text=True,
                              timeout=timeout, creationflags=CREATE_NO_WINDOW)
    except Exception:
        return None


def query_nvidia():
    r = run_hidden([
        "nvidia-smi",
        "--query-gpu=name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ], timeout=4)
    if not r or r.returncode != 0 or not r.stdout.strip():
        return None
    try:
        parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")]
        if len(parts) < 4:
            return None
        return {"name": parts[0], "used": float(parts[1]),
                "total": float(parts[2]), "util": float(parts[3])}
    except (ValueError, IndexError):
        return None


def kill_ollama_processes():
    killed = []
    targets = {"ollama.exe", "ollama app.exe", "ollama_llama_server.exe"}
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            if (proc.info.get("name") or "").lower() in targets:
                proc.terminate()
                killed.append(proc.info["name"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed:
        time.sleep(0.6)
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                if (proc.info.get("name") or "").lower() in targets and proc.is_running():
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return killed


def set_high_performance_power_plan():
    r = run_hidden(["powercfg", "/setactive", "SCHEME_MAX"])
    if r is None:
        return False, "Не удалось запустить powercfg."
    if r.returncode == 0:
        return True, "Схема «Высокая производительность» активирована."
    return False, (r.stderr or r.stdout or "powercfg вернул ошибку.").strip()


def get_disk_usage():
    try:
        u = psutil.disk_usage("C:\\" if os.name == "nt" else "/")
        return u.used, u.total, u.percent
    except Exception:
        return 0, 0, 0


# =============================================================
#  РЕЕСТР
# =============================================================
def read_autostart_entries():
    entries = []
    if winreg is None:
        return entries
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ)
    except OSError:
        return entries
    try:
        i = 0
        while True:
            try:
                name, value, _ = winreg.EnumValue(key, i)
                entries.append({"name": name, "command": str(value)})
                i += 1
            except OSError:
                break
    finally:
        try:
            winreg.CloseKey(key)
        except OSError:
            pass
    return entries


def delete_autostart_value(name):
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.DeleteValue(key, name)
            return True
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def write_autostart_value(name, command):
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, command)
            return True
        finally:
            winreg.CloseKey(key)
    except OSError:
        return False


def load_disabled():
    if not os.path.exists(DISABLED_FILE):
        return {}
    try:
        with open(DISABLED_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_disabled(data):
    try:
        with open(DISABLED_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def extract_app_name(command):
    if not command:
        return ""
    cmd = command.strip()
    exe = ""
    if cmd.startswith('"'):
        end = cmd.find('"', 1)
        if end > 0:
            exe = cmd[1:end]
    if not exe:
        parts = cmd.split()
        if parts:
            exe = parts[0].strip('"')
    if not exe:
        return ""
    return os.path.splitext(os.path.basename(exe))[0]


def app_icon(name, command):
    c = (str(name) + " " + str(command)).lower()
    if "chrome" in c:                              return "🌐"
    if "firefox" in c:                             return "🦊"
    if "msedge" in c or "edge" in c:               return "🌊"
    if "opera" in c:                               return "🎭"
    if "brave" in c:                               return "🦁"
    if "yandex" in c:                              return "🟡"
    if "steam" in c:                               return "🎮"
    if "epic" in c:                                return "🎯"
    if "discord" in c:                             return "💬"
    if "telegram" in c:                            return "✈️"
    if "whatsapp" in c:                            return "💚"
    if "skype" in c:                               return "📞"
    if "zoom" in c:                                return "📹"
    if "teams" in c:                               return "👥"
    if "slack" in c:                               return "💼"
    if "spotify" in c:                             return "🎵"
    if "dropbox" in c:                             return "📦"
    if "onedrive" in c:                            return "☁️"
    if "googledrive" in c or "gdrive" in c:        return "📁"
    if "nvidia" in c:                              return "🎨"
    if "amd" in c:                                 return "🔴"
    if "intel" in c:                               return "🔵"
    if "update" in c:                              return "🔄"
    if "defender" in c or "security" in c:         return "🛡️"
    if "obs" in c:                                 return "🎥"
    if "vlc" in c:                                 return "🎬"
    if "code" in c or "vscode" in c:               return "💻"
    if "python" in c:                              return "🐍"
    if "java" in c:                                return "☕"
    if "git" in c:                                 return "🌿"
    if "notion" in c:                              return "📓"
    if "todoist" in c:                             return "✅"
    if ".exe" in c:                                return "⚙️"
    return "📦"


# =============================================================
#  ОСНОВНОЕ ПРИЛОЖЕНИЕ
# =============================================================
class SmartCleaner(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("dark")

        self.title("Smart Cleaner")
        self.geometry(f"{WINDOW_W}x{WINDOW_H}")
        self.minsize(960, 620)
        self.configure(fg_color=BG)

        self.update_idletasks()
        x = (self.winfo_screenwidth()  - WINDOW_W) // 2
        y = (self.winfo_screenheight() - WINDOW_H) // 2
        self.geometry(f"{WINDOW_W}x{WINDOW_H}+{x}+{y}")

        self.scanning      = False
        self.cleaning      = False
        self.freeing       = False
        self.monitor_run   = True
        self.scan_targets  = []
        self.scan_results  = {}
        self.target_widgets = {}

        psutil.cpu_percent(interval=None)

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self._init_scan_targets()
        self._build_sidebar()
        self._build_content()
        self._build_clean_tab()
        self._build_boost_tab()
        self._build_autostart_tab()
        self.show_tab("clean")
        self._start_monitor()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------------------------------------------------
    def _init_scan_targets(self):
        localapp   = os.environ.get("LOCALAPPDATA", "")
        systemroot = os.environ.get("SystemRoot", r"C:\Windows")
        temp       = os.environ.get("TEMP", "")
        downloads  = os.path.join(os.path.expanduser("~"), "Downloads")

        targets = []

        temp_paths = []
        if temp: temp_paths.append(temp)
        wt = os.path.join(systemroot, "Temp")
        if wt not in temp_paths:
            temp_paths.append(wt)
        targets.append({"id": "temp", "name": "Временные файлы Windows",
                        "type": "folders", "paths": temp_paths, "enabled": True})

        for bid, bname, base in [
            ("chrome", "Chrome", os.path.join(localapp, "Google", "Chrome", "User Data")),
            ("edge",   "Edge",   os.path.join(localapp, "Microsoft", "Edge", "User Data")),
            ("yandex", "Яндекс", os.path.join(localapp, "Yandex", "YandexBrowser", "User Data")),
            ("brave",  "Brave",  os.path.join(localapp, "BraveSoftware", "Brave-Browser", "User Data")),
        ]:
            paths = []
            for profile in ("Default", "Profile 1", "Profile 2", "Profile 3"):
                for sub in ("Cache", "Code Cache", "GPUCache"):
                    p = os.path.join(base, profile, sub)
                    if os.path.isdir(p):
                        paths.append(p)
            if paths:
                targets.append({"id": bid, "name": f"Кэш {bname}",
                                "type": "folders", "paths": paths, "enabled": True})

        pip_cache = os.path.join(localapp, "pip", "Cache")
        if os.path.isdir(pip_cache):
            targets.append({"id": "pip", "name": "Кэш pip",
                            "type": "folders", "paths": [pip_cache], "enabled": True})

        if os.path.isdir(downloads):
            targets.append({"id": "downloads",
                            "name": "Загрузки (незавершённые)",
                            "type": "downloads_partial",
                            "paths": [downloads], "enabled": True})

        targets.append({"id": "thumbs",  "name": "Кэш эскизов",
                        "type": "thumbcache", "paths": [], "enabled": True})
        targets.append({"id": "recycle", "name": "Корзина",
                        "type": "recyclebin", "paths": [], "enabled": True})

        self.scan_targets = targets

    # ---------------------------------------------------------
    def _build_sidebar(self):
        sb = ctk.CTkFrame(self, fg_color=BG, corner_radius=0, width=210)
        sb.grid(row=0, column=0, sticky="nsw")
        sb.grid_propagate(False)

        logo = ctk.CTkFrame(sb, fg_color="transparent")
        logo.pack(fill="x", padx=20, pady=(24, 28))
        ctk.CTkLabel(logo, text="⚡  Smart",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color=TEXT).pack(anchor="w")

        self.nav_buttons = {}
        for key, icon, label in [
            ("clean",     "◐", "Очистка"),
            ("boost",     "◑", "Ускорение"),
            ("autostart", "◒", "Автозагрузка"),
        ]:
            btn = ctk.CTkButton(
                sb, text=f"  {icon}   {label}", anchor="w",
                fg_color="transparent", hover_color=CARD,
                text_color=MUTED, font=ctk.CTkFont(size=13),
                height=36, corner_radius=6,
                command=lambda k=key: self.show_tab(k),
            )
            btn.pack(fill="x", padx=10, pady=1)
            self.nav_buttons[key] = btn

        ctk.CTkLabel(sb, text="v1.2",
                     font=ctk.CTkFont(size=10),
                     text_color=BORDER).pack(side="bottom", pady=14)

    # ---------------------------------------------------------
    def _build_content(self):
        self.content = ctk.CTkFrame(self, fg_color=BG, corner_radius=0)
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)

        self.tabs = {}
        for key in ("clean", "boost", "autostart"):
            f = ctk.CTkFrame(self.content, fg_color=BG, corner_radius=0)
            f.grid(row=0, column=0, sticky="nsew")
            f.grid_remove()
            self.tabs[key] = f

    def show_tab(self, key):
        for k, frame in self.tabs.items():
            frame.grid() if k == key else frame.grid_remove()
        for k, btn in self.nav_buttons.items():
            btn.configure(
                fg_color=CARD if k == key else "transparent",
                text_color=TEXT if k == key else MUTED,
            )
        if key == "autostart":
            self.refresh_autostart()

    # =========================================================
    #  ОЧИСТКА
    # =========================================================
    def _build_clean_tab(self):
        frame = self.tabs["clean"]

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 20))
        ctk.CTkLabel(header, text="Очистка",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(header, text="Сколько освободится при очистке",
                     font=ctk.CTkFont(size=12),
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))

        # --- Диск ---
        disk_row = ctk.CTkFrame(frame, fg_color="transparent")
        disk_row.pack(fill="x", padx=28, pady=(0, 14))
        ctk.CTkLabel(disk_row, text="💾",
                     font=ctk.CTkFont(size=14)).pack(side="left")
        self.disk_label = ctk.CTkLabel(
            disk_row, text="...",
            font=ctk.CTkFont(size=12),
            text_color=MUTED,
        )
        self.disk_label.pack(side="left", padx=(8, 0))
        self.disk_bar = ctk.CTkProgressBar(
            disk_row, height=4, corner_radius=2,
            width=140, progress_color=MUTED, fg_color=BORDER,
        )
        self.disk_bar.pack(side="right", pady=2)
        self.disk_bar.set(0)

        # --- Кнопки ---
        controls = ctk.CTkFrame(frame, fg_color="transparent")
        controls.pack(fill="x", padx=28, pady=(0, 12))

        self.scan_btn = ctk.CTkButton(
            controls, text="Сканировать", command=self.scan_all,
            fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=34, width=130, corner_radius=6,
        )
        self.scan_btn.pack(side="left")

        self.clean_btn = ctk.CTkButton(
            controls, text="Очистить", command=self.clean_selected,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=34, width=130, corner_radius=6,
        )
        self.clean_btn.pack(side="left", padx=8)

        self.total_size_lbl = ctk.CTkLabel(
            controls, text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color=ACCENT,
        )
        self.total_size_lbl.pack(side="right")

        # --- Список ---
        self.targets_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        self.targets_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 8))

        for t in self.scan_targets:
            self._build_target_card(t)

        # --- Лог ---
        log_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        log_wrap.pack(fill="x", padx=28, pady=(0, 20))
        ctk.CTkLabel(log_wrap, text="ЖУРНАЛ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=MUTED).pack(anchor="w", pady=(0, 4))
        self.log_box = ctk.CTkTextbox(
            log_wrap, height=76, fg_color=CARD, text_color=MUTED,
            corner_radius=6, border_width=0,
            font=ctk.CTkFont(family="Consolas", size=10), wrap="word",
        )
        self.log_box.pack(fill="x")
        self.log_box.configure(state="disabled")

    def _build_target_card(self, target):
        card = ctk.CTkFrame(self.targets_scroll, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", pady=3)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=12)

        # Левая часть: имя + строка «освободит»
        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(left, text=target["name"],
                     font=ctk.CTkFont(size=13, weight="bold"),
                     text_color=TEXT, anchor="w").pack(anchor="w")

        info_row = ctk.CTkFrame(left, fg_color="transparent")
        info_row.pack(anchor="w", pady=(2, 0))
        self.target_widgets[target["id"]] = {
            "size_label": ctk.CTkLabel(
                info_row, text="—  освободит",
                font=ctk.CTkFont(size=11), text_color=MUTED),
            "var": None,
        }
        self.target_widgets[target["id"]]["size_label"].pack(side="left")

        # Правая часть: switch
        var = ctk.BooleanVar(value=target["enabled"])
        self.target_widgets[target["id"]]["var"] = var
        sw = ctk.CTkSwitch(
            inner, text="", variable=var, width=38,
            progress_color=ACCENT, button_color=TEXT,
            button_hover_color=TEXT, fg_color=BORDER,
            command=lambda tid=target["id"], v=var: self._toggle_target(tid, v),
        )
        sw.pack(side="right")

    def _toggle_target(self, tid, var):
        for t in self.scan_targets:
            if t["id"] == tid:
                t["enabled"] = bool(var.get())
                break

    def log(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{stamp}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def log_clear(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def scan_all(self):
        if self.scanning or self.cleaning:
            return
        if not any(t["enabled"] for t in self.scan_targets):
            messagebox.showinfo("Сканирование", "Не выбрано ни одной категории.")
            return

        self.scanning = True
        self.scan_btn.configure(state="disabled", text="...")
        self.clean_btn.configure(state="disabled")
        self.log_clear()
        self.log("Сканирование...")
        for t in self.scan_targets:
            self.target_widgets[t["id"]]["size_label"].configure(
                text="—  освободит", text_color=MUTED)
        self.total_size_lbl.configure(text="")

        def worker():
            total = 0
            results = {}
            for t in self.scan_targets:
                if not t["enabled"]:
                    results[t["id"]] = 0
                    continue
                size = 0
                try:
                    if t["type"] == "folders":
                        for p in t["paths"]:
                            size += folder_size(p)
                    elif t["type"] == "downloads_partial":
                        for p in t["paths"]:
                            size += scan_downloads_partial(p)
                    elif t["type"] == "thumbcache":
                        size = thumbcache_size()
                    elif t["type"] == "recyclebin":
                        size = recycle_bin_size()
                except Exception:
                    size = 0
                results[t["id"]] = size
                total += size
                self.after(0, lambda tid=t["id"], s=size:
                           self.target_widgets[tid]["size_label"].configure(
                               text=f"{format_bytes(s)}  освободит",
                               text_color=ACCENT if s > 0 else MUTED))
            self.after(0, lambda: self._scan_done(results, total))

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, results, total):
        self.scanning = False
        self.scan_results = results
        self.scan_btn.configure(state="normal", text="Сканировать")
        self.clean_btn.configure(state="normal")
        self.total_size_lbl.configure(text=f"Итого: {format_bytes(total)}")
        self.log(f"Готово. Всего: {format_bytes(total)}")

    def clean_selected(self):
        if self.cleaning or self.scanning:
            return
        selected = [t for t in self.scan_targets if t["enabled"]]
        if not selected:
            messagebox.showinfo("Очистка", "Не выбрано ни одной категории.")
            return
        if not messagebox.askyesno(
            "Подтверждение",
            f"Очистить {len(selected)} категорий?\nДействие необратимо.",
        ):
            return

        self.cleaning = True
        self.clean_btn.configure(state="disabled", text="...")
        self.scan_btn.configure(state="disabled")
        self.log_clear()
        self.log("Очистка...")

        def worker():
            total = 0
            for t in selected:
                size = 0
                try:
                    if t["type"] == "folders":
                        for p in t["paths"]:
                            size += delete_folder_contents(p)
                    elif t["type"] == "downloads_partial":
                        for p in t["paths"]:
                            size += clean_downloads_partial(p)
                    elif t["type"] == "thumbcache":
                        size = delete_thumbcache()
                    elif t["type"] == "recyclebin":
                        sz = recycle_bin_size()
                        if empty_recycle_bin():
                            size = sz
                except Exception as e:
                    self.after(0, lambda n=t["name"], err=str(e):
                               self.log(f"⚠ {n}: {err}"))
                    continue
                total += size
                self.after(0, lambda tid=t["id"]:
                           self.target_widgets[tid]["size_label"].configure(
                               text="0 Б  освободит", text_color=MUTED))
                self.after(0, lambda n=t["name"], s=size:
                           self.log(f"• {n}: {format_bytes(s)}"))
            self.after(0, lambda: self._clean_done(total))

        threading.Thread(target=worker, daemon=True).start()

    def _clean_done(self, freed):
        self.cleaning = False
        self.clean_btn.configure(state="normal", text="Очистить")
        self.scan_btn.configure(state="normal")
        self.total_size_lbl.configure(text=f"Освобождено: {format_bytes(freed)}")
        self.log(f"Готово. Освобождено: {format_bytes(freed)}")

    # =========================================================
    #  УСКОРЕНИЕ
    # =========================================================
    def _build_boost_tab(self):
        frame = self.tabs["boost"]

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 20))
        ctk.CTkLabel(header, text="Ускорение",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(header, text="Нагрузка в реальном времени",
                     font=ctk.CTkFont(size=12),
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(0, 14))
        for i in range(3):
            row.grid_columnconfigure(i, weight=1, uniform="s")

        # CPU
        c1 = self._stat_card(row, "CPU", "🖥")
        c1.grid(row=0, column=0, padx=(0, 4), sticky="nsew")
        self.cpu_pct = ctk.CTkLabel(c1, text="0%",
                                    font=ctk.CTkFont(size=22, weight="bold"),
                                    text_color=TEXT)
        self.cpu_pct.pack(anchor="w", padx=14, pady=(0, 6))
        self.cpu_bar = ctk.CTkProgressBar(c1, height=4, corner_radius=2,
                                          progress_color=ACCENT, fg_color=BORDER)
        self.cpu_bar.pack(fill="x", padx=14, pady=(0, 8))
        self.cpu_bar.set(0)
        self.cpu_sub = ctk.CTkLabel(c1, text="—",
                                    font=ctk.CTkFont(size=10), text_color=MUTED)
        self.cpu_sub.pack(anchor="w", padx=14, pady=(0, 12))

        # RAM
        c2 = self._stat_card(row, "ОЗУ", "💾")
        c2.grid(row=0, column=1, padx=4, sticky="nsew")
        self.ram_pct = ctk.CTkLabel(c2, text="0%",
                                    font=ctk.CTkFont(size=22, weight="bold"),
                                    text_color=TEXT)
        self.ram_pct.pack(anchor="w", padx=14, pady=(0, 6))
        self.ram_bar = ctk.CTkProgressBar(c2, height=4, corner_radius=2,
                                          progress_color=GREEN, fg_color=BORDER)
        self.ram_bar.pack(fill="x", padx=14, pady=(0, 8))
        self.ram_bar.set(0)
        self.ram_sub = ctk.CTkLabel(c2, text="—",
                                    font=ctk.CTkFont(size=10), text_color=MUTED)
        self.ram_sub.pack(anchor="w", padx=14, pady=(0, 12))

        # GPU
        c3 = self._stat_card(row, "GPU", "🎮")
        c3.grid(row=0, column=2, padx=(4, 0), sticky="nsew")
        self.gpu_pct = ctk.CTkLabel(c3, text="—",
                                    font=ctk.CTkFont(size=22, weight="bold"),
                                    text_color=TEXT)
        self.gpu_pct.pack(anchor="w", padx=14, pady=(0, 6))
        self.gpu_bar = ctk.CTkProgressBar(c3, height=4, corner_radius=2,
                                          progress_color=YELLOW, fg_color=BORDER)
        self.gpu_bar.pack(fill="x", padx=14, pady=(0, 8))
        self.gpu_bar.set(0)
        self.gpu_sub = ctk.CTkLabel(c3, text="поиск...",
                                    font=ctk.CTkFont(size=10), text_color=MUTED)
        self.gpu_sub.pack(anchor="w", padx=14, pady=(0, 12))

        # Кнопки
        actions = ctk.CTkFrame(frame, fg_color="transparent")
        actions.pack(fill="x", padx=28, pady=(0, 14))
        actions.grid_columnconfigure(0, weight=1)
        actions.grid_columnconfigure(1, weight=1)

        self.free_btn = ctk.CTkButton(
            actions, text="Освободить память (Ollama)",
            command=self.free_memory,
            fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=40, corner_radius=6,
        )
        self.free_btn.grid(row=0, column=0, padx=(0, 4), sticky="ew")

        self.game_btn = ctk.CTkButton(
            actions, text="Игровой режим",
            command=self.enable_game_mode,
            fg_color=ACCENT, hover_color=ACCENT_H, text_color="#ffffff",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=40, corner_radius=6,
        )
        self.game_btn.grid(row=0, column=1, padx=(4, 0), sticky="ew")

        # Лог
        log_wrap = ctk.CTkFrame(frame, fg_color="transparent")
        log_wrap.pack(fill="both", expand=True, padx=28, pady=(0, 20))
        ctk.CTkLabel(log_wrap, text="ЖУРНАЛ",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=MUTED).pack(anchor="w", pady=(0, 4))
        self.boost_log = ctk.CTkTextbox(
            log_wrap, fg_color=CARD, text_color=MUTED,
            corner_radius=6, border_width=0,
            font=ctk.CTkFont(family="Consolas", size=10), wrap="word",
        )
        self.boost_log.pack(fill="both", expand=True)
        self.boost_log.configure(state="disabled")

    def _stat_card(self, parent, title, icon):
        card = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=8)
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 4))
        ctk.CTkLabel(top, text=icon,
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkLabel(top, text=title,
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=MUTED).pack(side="left", padx=(6, 0))
        return card

    def boost_log_write(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.boost_log.configure(state="normal")
        self.boost_log.insert("end", f"[{stamp}] {msg}\n")
        self.boost_log.see("end")
        self.boost_log.configure(state="disabled")

    def _start_monitor(self):
        def loop():
            while self.monitor_run:
                try:
                    cpu = psutil.cpu_percent(interval=None)
                    vm  = psutil.virtual_memory()
                    nv  = query_nvidia()
                    du  = get_disk_usage()
                    self.after(0, lambda: self._update_monitor(cpu, vm, nv, du))
                except Exception:
                    pass
                time.sleep(1.0)
        threading.Thread(target=loop, daemon=True).start()

    def _update_monitor(self, cpu, vm, nv, du):
        self.cpu_pct.configure(text=f"{cpu:.0f}%")
        self.cpu_bar.set(max(0.0, min(1.0, cpu / 100.0)))
        try:
            self.cpu_sub.configure(text=f"{psutil.cpu_count(logical=True)} потоков")
        except Exception:
            pass

        self.ram_pct.configure(text=f"{vm.percent:.0f}%")
        self.ram_bar.set(max(0.0, min(1.0, vm.percent / 100.0)))
        self.ram_sub.configure(
            text=f"{vm.used/(1024**3):.1f} / {vm.total/(1024**3):.1f} ГБ")

        if nv and nv.get("total", 0) > 0:
            pct = nv["used"] / nv["total"] * 100.0
            self.gpu_pct.configure(text=f"{pct:.0f}%")
            self.gpu_bar.set(max(0.0, min(1.0, pct / 100.0)))
            self.gpu_sub.configure(
                text=f"{nv['used']/1024:.1f} / {nv['total']/1024:.1f} ГБ")
        else:
            self.gpu_pct.configure(text="—")
            self.gpu_bar.set(0)
            self.gpu_sub.configure(text="нет NVIDIA")

        used, total, percent = du
        if total > 0:
            self.disk_label.configure(
                text=f"C:  {used/(1024**3):.0f} из {total/(1024**3):.0f} ГБ "
                     f"({percent:.0f}%)")
            self.disk_bar.set(max(0.0, min(1.0, percent / 100.0)))
        else:
            self.disk_label.configure(text="C:  —")
            self.disk_bar.set(0)

    def free_memory(self):
        if self.freeing:
            return
        self.freeing = True
        self.free_btn.configure(state="disabled", text="Освобождаю...")
        self.boost_log_write("Завершаю Ollama...")

        def worker():
            killed = kill_ollama_processes()
            self.after(0, lambda: self._free_done(killed))
        threading.Thread(target=worker, daemon=True).start()

    def _free_done(self, killed):
        self.freeing = False
        self.free_btn.configure(state="normal",
                                text="Освободить память (Ollama)")
        if killed:
            self.boost_log_write(
                f"Завершено: {len(killed)} ({', '.join(sorted(set(killed)))})")
            messagebox.showinfo("Готово",
                                f"Завершено процессов: {len(killed)}")
        else:
            self.boost_log_write("Ollama не запущена.")
            messagebox.showinfo("Готово", "Активных процессов Ollama не найдено.")

    def enable_game_mode(self):
        self.game_btn.configure(state="disabled", text="...")
        self.boost_log_write("Активирую High Performance...")

        def worker():
            ok, msg = set_high_performance_power_plan()
            self.after(0, lambda: self._game_done(ok, msg))
        threading.Thread(target=worker, daemon=True).start()

    def _game_done(self, ok, msg):
        self.game_btn.configure(state="normal", text="Игровой режим")
        self.boost_log_write(("✓ " if ok else "⚠ ") + msg)
        (messagebox.showinfo if ok else messagebox.showerror)("Игровой режим", msg)

    # =========================================================
    #  АВТОЗАГРУЗКА
    # =========================================================
    def _build_autostart_tab(self):
        frame = self.tabs["autostart"]

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.pack(fill="x", padx=28, pady=(28, 20))
        ctk.CTkLabel(header, text="Автозагрузка",
                     font=ctk.CTkFont(size=20, weight="bold"),
                     text_color=TEXT).pack(anchor="w")
        ctk.CTkLabel(header, text="HKCU\\...\\CurrentVersion\\Run",
                     font=ctk.CTkFont(family="Consolas", size=11),
                     text_color=MUTED).pack(anchor="w", pady=(2, 0))

        controls = ctk.CTkFrame(frame, fg_color="transparent")
        controls.pack(fill="x", padx=28, pady=(0, 12))

        ctk.CTkButton(
            controls, text="Обновить", command=self.refresh_autostart,
            fg_color=CARD, hover_color=CARD_HOVER, text_color=TEXT,
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32, width=110, corner_radius=6,
        ).pack(side="left")

        self.autostart_count = ctk.CTkLabel(
            controls, text="", font=ctk.CTkFont(size=11), text_color=MUTED)
        self.autostart_count.pack(side="right")

        self.autostart_scroll = ctk.CTkScrollableFrame(
            frame, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=MUTED,
        )
        self.autostart_scroll.pack(fill="both", expand=True, padx=24, pady=(0, 20))

    def refresh_autostart(self):
        for w in self.autostart_scroll.winfo_children():
            w.destroy()
        entries  = read_autostart_entries()
        disabled = load_disabled()
        self.autostart_count.configure(
            text=f"активно: {len(entries)}   ·   отключено: {len(disabled)}")
        if not entries and not disabled:
            ctk.CTkLabel(self.autostart_scroll,
                         text="Записей не найдено",
                         font=ctk.CTkFont(size=12),
                         text_color=MUTED).pack(pady=40)
            return
        for e in entries:
            self._add_autostart_row(e["name"], e["command"], True)
        for name, cmd in disabled.items():
            self._add_autostart_row(name, cmd, False)

    def _add_autostart_row(self, name, command, enabled):
        card = ctk.CTkFrame(self.autostart_scroll, fg_color=CARD, corner_radius=8)
        card.pack(fill="x", pady=3)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        left = ctk.CTkFrame(inner, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)

        title_row = ctk.CTkFrame(left, fg_color="transparent")
        title_row.pack(anchor="w")

        icon = app_icon(name, command)
        friendly = extract_app_name(command) or name
        ctk.CTkLabel(title_row, text=icon,
                     font=ctk.CTkFont(size=13)).pack(side="left")
        ctk.CTkLabel(title_row, text="  " + friendly,
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=TEXT if enabled else MUTED).pack(side="left")
        ctk.CTkLabel(title_row,
                     text="   ●" if enabled else "   ○",
                     font=ctk.CTkFont(size=10),
                     text_color=GREEN if enabled else BORDER).pack(side="left")

        ctk.CTkLabel(left, text=name,
                     font=ctk.CTkFont(family="Consolas", size=9),
                     text_color=MUTED, anchor="w").pack(anchor="w", pady=(2, 0))

        btns = ctk.CTkFrame(inner, fg_color="transparent")
        btns.pack(side="right")

        if enabled:
            ctk.CTkButton(
                btns, text="Откл", width=64, height=28,
                fg_color="transparent", hover_color=CARD_HOVER,
                text_color=YELLOW, font=ctk.CTkFont(size=11), corner_radius=5,
                command=lambda n=name, c=command: self.disable_autostart(n, c),
            ).pack(side="left", padx=3)
        else:
            ctk.CTkButton(
                btns, text="Вкл", width=64, height=28,
                fg_color="transparent", hover_color=CARD_HOVER,
                text_color=GREEN, font=ctk.CTkFont(size=11), corner_radius=5,
                command=lambda n=name, c=command: self.enable_autostart(n, c),
            ).pack(side="left", padx=3)

        ctk.CTkButton(
            btns, text="Удал", width=64, height=28,
            fg_color="transparent", hover_color="#3d1515",
            text_color=RED, font=ctk.CTkFont(size=11), corner_radius=5,
            command=lambda n=name: self.remove_autostart(n),
        ).pack(side="left", padx=3)

    def disable_autostart(self, name, command):
        if not messagebox.askyesno("Отключить", f"Убрать из автозагрузки?\n\n{name}"):
            return
        if not delete_autostart_value(name):
            messagebox.showerror("Ошибка", "Не удалось удалить запись из реестра.")
            return
        d = load_disabled(); d[name] = command; save_disabled(d)
        self.refresh_autostart()

    def enable_autostart(self, name, command):
        if not write_autostart_value(name, command):
            messagebox.showerror("Ошибка", "Не удалось записать в реестр.")
            return
        d = load_disabled()
        if name in d:
            del d[name]; save_disabled(d)
        self.refresh_autostart()

    def remove_autostart(self, name):
        if not messagebox.askyesno("Удалить", f"Удалить навсегда?\n\n{name}"):
            return
        delete_autostart_value(name)
        d = load_disabled()
        if name in d:
            del d[name]; save_disabled(d)
        self.refresh_autostart()

    # ---------------------------------------------------------
    def _on_close(self):
        self.monitor_run = False
        try:
            self.destroy()
        except Exception:
            pass


# =============================================================
def main():
    try:
        SmartCleaner().mainloop()
    except Exception as e:
        try:
            messagebox.showerror("Критическая ошибка", str(e))
        except Exception:
            print("Fatal:", e)
            sys.exit(1)


if __name__ == "__main__":
    main()