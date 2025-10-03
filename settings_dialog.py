import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '.core'))
from settings import load_settings, save_settings
from config import DEFAULT_TEMPERATURE, DEFAULT_PROVIDER_NAME
from providers import list_provider_names

class SettingsDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("500x400")
        self.transient(parent)
        self.grab_set()
        self.settings = load_settings()

        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # General tab
        general_frame = ttk.Frame(notebook)
        notebook.add(general_frame, text="General")

        ttk.Label(general_frame, text="Default Provider:").grid(row=0, column=0, sticky="w", pady=6)
        self.provider_var = tk.StringVar(value=self.settings.get("default_provider", DEFAULT_PROVIDER_NAME))
        self.provider_combo = ttk.Combobox(general_frame, textvariable=self.provider_var, values=list_provider_names(), state="readonly", width=32)
        self.provider_combo.grid(row=0, column=1, sticky="ew", padx=8)

        ttk.Label(general_frame, text="Default Temperature:").grid(row=1, column=0, sticky="w", pady=6)
        self.temp_var = tk.DoubleVar(value=self.settings.get("default_temperature", DEFAULT_TEMPERATURE))
        self.temp_entry = ttk.Entry(general_frame, textvariable=self.temp_var, width=8)
        self.temp_entry.grid(row=1, column=1, sticky="w", padx=8)

        # Model paths tab
        paths_frame = ttk.Frame(notebook)
        notebook.add(paths_frame, text="Model Paths")
        # Model paths now as list of dicts: {"nickname": str, "path": str}
        self.paths = self.settings.get("local_model_paths", [])
        if self.paths and isinstance(self.paths[0], str):
            # Migrate from old format
            self.paths = [{"nickname": os.path.basename(p.rstrip("/")), "path": p} for p in self.paths]
        self.paths_list = tk.Listbox(paths_frame, selectmode=tk.SINGLE, width=60, height=8)
        self.paths_list.pack(fill="x", padx=8, pady=(8,4))
        self.refresh_paths_list()

        btn_frame = ttk.Frame(paths_frame)
        btn_frame.pack(fill="x", padx=8, pady=4)
        ttk.Button(btn_frame, text="Add Path", command=self.add_path).pack(side="left")
        ttk.Button(btn_frame, text="Edit Selected", command=self.edit_path).pack(side="left", padx=(8,0))
        ttk.Button(btn_frame, text="Remove Selected", command=self.remove_path).pack(side="left", padx=(8,0))

        # Key/legend for nicknames
        key_frame = ttk.Frame(paths_frame)
        key_frame.pack(fill="x", padx=8, pady=(8, 4))
        key_text = (
            "Nickname: A short label for this model path. "
            "You can use nicknames to quickly identify or group model folders. "
            "For example, use 'Main', 'Backup', or 'Experimental'. "
            "Nicknames are for your reference only and do not affect model loading."
        )
        ttk.Label(key_frame, text=key_text, wraplength=420, foreground="#878787").pack(anchor="w")

    def refresh_paths_list(self):
        self.paths_list.delete(0, "end")
        for entry in self.paths:
            display = f"{entry.get('nickname','')} — {entry.get('path','')}"
            self.paths_list.insert("end", display)

    def add_path(self):
        self.edit_path(new=True)

    def edit_path(self, new=False):
        idx = None
        if not new:
            sel = self.paths_list.curselection()
            if not sel:
                return
            idx = sel[0]
            entry = self.paths[idx]
        else:
            entry = {"nickname": "", "path": ""}
        popup = tk.Toplevel(self)
        popup.title("Edit Model Path")
        popup.geometry("400x140")
        tk.Label(popup, text="Nickname:").pack(anchor="w", padx=12, pady=(12,0))
        nick_var = tk.StringVar(value=entry.get("nickname", ""))
        nick_entry = ttk.Entry(popup, textvariable=nick_var, width=40)
        nick_entry.pack(fill="x", padx=12)
        tk.Label(popup, text="Path:").pack(anchor="w", padx=12, pady=(8,0))
        path_var = tk.StringVar(value=entry.get("path", ""))
        path_entry = ttk.Entry(popup, textvariable=path_var, width=40)
        path_entry.pack(fill="x", padx=12)
        def save_edit():
            new_entry = {"nickname": nick_var.get().strip(), "path": path_var.get().strip()}
            if not new_entry["path"]:
                messagebox.showerror("Error", "Path cannot be empty.", parent=popup)
                return
            if new:
                self.paths.append(new_entry)
            else:
                self.paths[idx] = new_entry
            self.refresh_paths_list()
            popup.destroy()
        btns = ttk.Frame(popup)
        btns.pack(fill="x", pady=10)
        ttk.Button(btns, text="Save", command=save_edit).pack(side="right", padx=12)
        ttk.Button(btns, text="Cancel", command=popup.destroy).pack(side="right")

        # Save/Cancel
        save_btn = ttk.Button(self, text="Save", command=self.save)
        save_btn.pack(side="right", padx=10, pady=10)
        cancel_btn = ttk.Button(self, text="Cancel", command=self.destroy)
        cancel_btn.pack(side="right", pady=10)

    def add_path(self):
        selection = filedialog.askdirectory(parent=self)
        if selection and selection not in self.paths_list.get(0, "end"):
            self.paths_list.insert("end", selection)

    def remove_path(self):
        sel = self.paths_list.curselection()
        if sel:
            idx = sel[0]
            del self.paths[idx]
            self.refresh_paths_list()

    def save(self):
        self.settings["default_provider"] = self.provider_var.get().strip()
        self.settings["default_temperature"] = self.temp_var.get()
        self.settings["local_model_paths"] = self.paths
        save_settings(self.settings)
        messagebox.showinfo("Settings", "Settings saved.")
        self.destroy()
