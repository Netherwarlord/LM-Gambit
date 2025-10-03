from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Dict, List, Tuple
from tkinter import filedialog, messagebox, scrolledtext, ttk
import tkinter as tk

CORE_DIR = Path(__file__).resolve().parent / ".core"
if str(CORE_DIR) not in sys.path:
    sys.path.insert(0, str(CORE_DIR))

from config import RESULTS_DIR, TESTS_DIR  # type: ignore  # noqa: E402
from providers import (  # type: ignore  # noqa: E402
    LocalEngineProvider,
    ProviderError,
    get_provider,
    list_provider_names,
)
from reporting import TemplateNotFoundError  # type: ignore  # noqa: E402
from runner import TestRunError, run_suite  # type: ignore  # noqa: E402
from settings import get_local_model_paths, set_local_model_paths  # type: ignore  # noqa: E402


def open_path(path: Path) -> None:
    if sys.platform.startswith("darwin"):
        subprocess.run(["open", str(path)], check=False)
    elif os.name == "nt":  # Windows
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.run(["xdg-open", str(path)], check=False)


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM Automated Test Console")
        self.geometry("880x620")
        self.minsize(760, 520)

        self.provider_names = list_provider_names()
        # Always default to Local Engine if available
        default_provider = LocalEngineProvider.name if LocalEngineProvider.name in self.provider_names else (self.provider_names[0] if self.provider_names else "")
        self.provider_var = tk.StringVar(value=default_provider)
        self.model_var = tk.StringVar()
        self.temperature_var = tk.DoubleVar(value=0.1)
        self.status_var = tk.StringVar(value="Idle")

        self.available_models: List[Tuple[str, str]] = []  # (id, display name)
        self.running = False

        self._build_ui()
        self._build_menu()
        if self.provider_var.get():
            self.fetch_models_async()

    def _build_ui(self) -> None:
        padding = {"padx": 12, "pady": 8}

        header = ttk.Label(self, text="Automated Diagnostic Test Runner", font=("Helvetica", 18, "bold"))
        header.pack(anchor="w", **padding)

        form_frame = ttk.Frame(self)
        form_frame.pack(fill="x", **padding)

        ttk.Label(form_frame, text="Provider:").grid(row=0, column=0, sticky="w")
        self.provider_combo = ttk.Combobox(
            form_frame,
            textvariable=self.provider_var,
            values=self.provider_names,
            state="readonly",
        )
        self.provider_combo.grid(row=0, column=1, sticky="ew", padx=(6, 18))
        self.provider_combo.bind("<<ComboboxSelected>>", lambda event: self.fetch_models_async())

        ttk.Label(form_frame, text="Model:").grid(row=0, column=2, sticky="w")
        self.model_combo = ttk.Combobox(form_frame, textvariable=self.model_var, state="readonly")
        self.model_combo.grid(row=0, column=3, sticky="ew", padx=(6, 18))

        ttk.Label(form_frame, text="Temperature:").grid(row=0, column=4, sticky="w")
        self.temperature_spin = ttk.Spinbox(
            form_frame,
            textvariable=self.temperature_var,
            from_=0.0,
            to=1.0,
            increment=0.05,
            width=6,
        )
        self.temperature_spin.grid(row=0, column=5, sticky="w")

        form_frame.columnconfigure(1, weight=1)
        form_frame.columnconfigure(3, weight=1)

        button_frame = ttk.Frame(self)
        button_frame.pack(fill="x", **padding)

        self.run_button = ttk.Button(button_frame, text="Run Tests", command=self.start_run)
        self.run_button.pack(side="left")

        ttk.Button(button_frame, text="Refresh Models", command=self.fetch_models_async).pack(side="left", padx=(12, 0))
        ttk.Button(button_frame, text="Edit Tests", command=lambda: open_path(TESTS_DIR)).pack(side="left", padx=(12, 0))
        ttk.Button(button_frame, text="Open Results", command=lambda: open_path(RESULTS_DIR)).pack(side="left", padx=(12, 0))
        ttk.Button(button_frame, text="View Latest Report", command=self.open_latest_report).pack(side="left", padx=(12, 0))

        ttk.Label(self, textvariable=self.status_var).pack(anchor="w", **padding)

        self.log = scrolledtext.ScrolledText(self, wrap="word", height=22)
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.log.configure(state="disabled")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self)
        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="Configure Model Paths…", command=self.configure_model_paths)
        menubar.add_cascade(label="Settings", menu=settings_menu)
        self.config(menu=menubar)
        self._settings_menu = settings_menu

    def fetch_models_async(self) -> None:
        if self.running:
            return

        provider_name = self.provider_var.get()
        if not provider_name:
            return

        self._set_status(f"Fetching models for {provider_name}…")
        self.model_combo.configure(values=())
        self.model_var.set("")

        thread = threading.Thread(target=self._fetch_models, daemon=True)
        thread.start()

    def _fetch_models(self) -> None:
        provider_name = self.provider_var.get()
        try:
            provider = get_provider(provider_name, **self._provider_kwargs(provider_name))
            models = provider.list_models()
        except ProviderError as exc:
            message = str(exc)
            self.after(0, lambda m=message: self._on_model_fetch_error(m))
            return

        model_pairs = [(model.id, model.display_name) for model in models]
        self.after(0, lambda: self._on_models_loaded(model_pairs))

    def _on_model_fetch_error(self, message: str) -> None:
        self._set_status("Model fetch failed")
        messagebox.showerror("Model Load Error", message)

    def _on_models_loaded(self, model_pairs: List[Tuple[str, str]]) -> None:
        self.available_models = model_pairs
        options = [display for _, display in model_pairs]
        self.model_combo.configure(values=options)
        if options:
            self.model_var.set(options[0])
            self._set_status(f"Loaded {len(options)} models.")
        else:
            self.model_var.set("")
            self._set_status("No models found.")

    def start_run(self) -> None:
        if self.running:
            return

        provider_name = self.provider_var.get()
        model_display = self.model_var.get()

        if not provider_name:
            messagebox.showwarning("Missing Provider", "Please select a provider before running tests.")
            return

        if not model_display:
            messagebox.showwarning("Missing Model", "Please select a model before running tests.")
            return

        model_id = self._model_id_for_display(model_display)
        if not model_id:
            messagebox.showerror("Model Error", "Unable to resolve the selected model.")
            return

        temperature = float(self.temperature_var.get())
        self.running = True
        self._set_status("Running tests…")
        self._append_log(f"Starting run with provider '{provider_name}' and model '{model_display}'.")
        self._toggle_controls(state="disabled")

        thread = threading.Thread(
            target=self._run_tests_thread,
            args=(provider_name, model_id, temperature),
            daemon=True,
        )
        thread.start()

    def _run_tests_thread(self, provider_name: str, model_id: str, temperature: float) -> None:
        start_time = time.time()

        def progress_callback(index: int, total: int, prompt: Dict[str, str], result: Dict[str, object]) -> None:
            status = "FAILED" if "error" in result else "DONE"
            title = prompt.get("title", f"Test {index}")
            filename = prompt.get("filename", f"test{index}")
            message = f"[{index}/{total}] {title} ({filename}) -> {status}"
            self.after(0, lambda: self._append_log(message))

        try:
            report_path = run_suite(
                provider_name=provider_name,
                model_id=model_id,
                temperature=temperature,
                progress_callback=progress_callback,
            )
        except (TestRunError, TemplateNotFoundError) as exc:
            message = str(exc)
            self.after(0, lambda m=message: self._handle_run_error(m))
            return

        elapsed = time.time() - start_time
        self.after(0, lambda: self._handle_run_success(report_path, elapsed))

    def _handle_run_error(self, message: str) -> None:
        self.running = False
        self._toggle_controls(state="normal")
        self._set_status("Run failed")
        self._append_log(f"Error: {message}")
        messagebox.showerror("Run Failed", message)

    def _handle_run_success(self, report_path: Path, elapsed: float) -> None:
        self.running = False
        self._toggle_controls(state="normal")
        self._set_status("Run complete")
        self._append_log(f"Run complete in {elapsed:.2f}s. Report saved to {report_path.name}.")
        messagebox.showinfo("Run Complete", f"Report saved to {report_path}")

    def _toggle_controls(self, *, state: str) -> None:
        widgets = [
            self.run_button,
            self.provider_combo,
            self.model_combo,
            self.temperature_spin,
        ]
        for widget in widgets:
            widget.configure(state=state)

    def _append_log(self, message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{timestamp}] {message}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, message: str) -> None:
        self.status_var.set(message)

    def _model_id_for_display(self, display_name: str) -> str | None:
        for model_id, display in self.available_models:
            if display == display_name:
                return model_id
        return None

    def _provider_kwargs(self, provider_name: str) -> Dict[str, object]:
        if provider_name == LocalEngineProvider.name:
            custom_paths = [Path(p).expanduser() for p in get_local_model_paths()]
            return {"search_paths": [path for path in custom_paths if path]}
        return {}

    def configure_model_paths(self) -> None:
        dialog = tk.Toplevel(self)
        dialog.title("Configure Model Paths")
        dialog.geometry("520x320")
        dialog.transient(self)
        dialog.grab_set()

        paths: List[str] = get_local_model_paths()

        listbox = tk.Listbox(dialog, selectmode=tk.SINGLE, width=60, height=10)
        for entry in paths:
            listbox.insert("end", entry)
        listbox.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        button_frame = ttk.Frame(dialog)
        button_frame.pack(fill="x", padx=12, pady=6)

        def add_path() -> None:
            selection = filedialog.askdirectory(parent=dialog)
            if selection and selection not in paths:
                paths.append(selection)
                listbox.insert("end", selection)

        def remove_path() -> None:
            selection = listbox.curselection()
            if not selection:
                return
            index = selection[0]
            listbox.delete(index)
            paths.pop(index)

        ttk.Button(button_frame, text="Add…", command=add_path).pack(side="left")
        ttk.Button(button_frame, text="Remove", command=remove_path).pack(side="left", padx=(8, 0))

        action_frame = ttk.Frame(dialog)
        action_frame.pack(fill="x", padx=12, pady=(0, 12))

        def on_save() -> None:
            normalized = [str(Path(p).expanduser()) for p in paths]
            set_local_model_paths(normalized)
            dialog.grab_release()
            dialog.destroy()
            if self.provider_var.get() == LocalEngineProvider.name:
                self.fetch_models_async()

        def on_cancel() -> None:
            dialog.grab_release()
            dialog.destroy()

        dialog.protocol("WM_DELETE_WINDOW", on_cancel)

        ttk.Button(action_frame, text="Save", command=on_save).pack(side="right", padx=(8, 0))
        ttk.Button(action_frame, text="Cancel", command=on_cancel).pack(side="right")

    def open_latest_report(self) -> None:
        if not RESULTS_DIR.exists():
            messagebox.showinfo("No Reports", "The results directory does not exist yet.")
            return

        reports = list(RESULTS_DIR.glob("*.md"))
        if not reports:
            messagebox.showinfo("No Reports", "No markdown reports found yet.")
            return

        latest_report = max(reports, key=lambda p: p.stat().st_mtime)
        open_path(latest_report)
        self._append_log(f"Opened latest report: {latest_report.name}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
