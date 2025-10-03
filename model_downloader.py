import tkinter as tk
from tkinter import simpledialog, messagebox
from pathlib import Path
import urllib.request
import shutil
import threading

class DownloadModelDialog(simpledialog.Dialog):
    def __init__(self, parent, model_dir: Path):
        self.model_dir = model_dir
        self.active_downloads = {}  # filename -> {progress, thread, cancel_flag}
        super().__init__(parent, title="Download Model")


    def body(self, master):
        tk.Label(master, text="Model URL:").grid(row=0, column=0, sticky="w")
        self.url_entry = tk.Entry(master, width=60)
        self.url_entry.grid(row=0, column=1, padx=6, pady=4)

        # Browse Hugging Face button
        browse_btn = tk.Button(master, text="Browse Hugging Face...", command=self.open_hf_browser, bg="#e0e0e0", fg="#111", width=22)
        browse_btn.grid(row=1, column=0, columnspan=2, sticky="w", padx=(0, 0), pady=(2, 2))

        # Comprehensive caption/instruction at the bottom
        caption_text = (
            "Paste a direct download URL for a model file. "
            "\n\n"
            "Where to find models:\n"
            "- Hugging Face: https://huggingface.co (search for GGUF or compatible models)\n"
            "- Official model provider pages\n"
            "\n"
            "The URL should point directly to a downloadable file (e.g., .gguf, .bin).\n"
            "Example: https://huggingface.co/ORG/MODEL/resolve/main/model-file.gguf\n"
            "\n"
            "Downloaded files will be saved to your selected model directory and will appear in the model selection list."
        )
        caption = tk.Label(
            master,
            text=caption_text,
            justify="left",
            anchor="w",
            wraplength=440,
            fg="#fff",
            bg="#444",
            font=(None, 10, "italic")
        )
        caption.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 2))

        # Download cards frame (below caption)
        self.cards_frame = tk.Frame(master, bg="#222")
        self.cards_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        self.refresh_cards()
        return self.url_entry
    def open_hf_browser(self):
        # Popup window with embedded browser to Hugging Face
        try:
            from tkhtmlview import HtmlFrame
        except ImportError:
            messagebox.showerror("Missing Dependency", "tkhtmlview is required for the integrated browser. Please install it with 'pip install tkhtmlview'.")
            return
        popup = tk.Toplevel(self)
        popup.title("Hugging Face Model Catalogue")
        popup.geometry("1000x700")
        # Info label
        tk.Label(popup, text="Browse models. Right-click a download link and select 'Copy Link', then paste it in the URL field.", bg="#222", fg="#fff").pack(fill="x")
        # Embedded browser (read-only, not full browser)
        frame = HtmlFrame(popup, horizontal_scrollbar="auto", vertical_scrollbar="auto")
        frame.pack(fill="both", expand=True)
        frame.load_website("https://huggingface.co/models")

        # Comprehensive caption/instruction at the bottom
        caption_text = (
            "Paste a direct download URL for a model file. "
            "\n\n"
            "Where to find models:\n"
            "- Hugging Face: https://huggingface.co (search for GGUF or compatible models)\n"
            "- Official model provider pages\n"
            "\n"
            "The URL should point directly to a downloadable file (e.g., .gguf, .bin).\n"
            "Example: https://huggingface.co/ORG/MODEL/resolve/main/model-file.gguf\n"
            "\n"
            "Downloaded files will be saved to your selected model directory and will appear in the model selection list."
        )
        caption = tk.Label(
            master,
            text=caption_text,
            justify="left",
            anchor="w",
            wraplength=440,
            fg="#fff",
            bg="#444",
            font=(None, 10, "italic")
        )
        caption.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(16, 2))

        # Download cards frame (below caption)
        self.cards_frame = tk.Frame(master, bg="#222")
        self.cards_frame.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        self.refresh_cards()
        return self.url_entry

    def refresh_cards(self):
        # Clear previous cards
        for widget in self.cards_frame.winfo_children():
            widget.destroy()
        if not self.active_downloads:
            placeholder = tk.Label(
                self.cards_frame,
                text="No downloads in progress.",
                bg="#222",
                fg="#aaa",
                font=(None, 10, "italic")
            )
            placeholder.pack(fill="x", pady=12)
        else:
            row = 0
            for fname, info in self.active_downloads.items():
                card = tk.Frame(self.cards_frame, bg="#333", bd=2, relief="groove")
                card.grid(row=row, column=0, sticky="ew", pady=4, padx=2)
                # File name
                tk.Label(card, text=fname, bg="#333", fg="#fff", font=(None, 10, "bold")).pack(anchor="w", padx=8, pady=(4,0))
                bar_frame = tk.Frame(card, bg="#333")
                bar_frame.pack(fill="x", padx=8, pady=(2,6))
                # Percentage label
                percent_var = info.get('percent_var')
                if not percent_var:
                    percent_var = tk.StringVar(value="0%")
                    info['percent_var'] = percent_var
                percent_label = tk.Label(bar_frame, textvariable=percent_var, width=5, anchor="e", bg="#333", fg="#fff")
                percent_label.pack(side="left")
                # Progress bar
                progress_var = info.get('progress_var')
                if not progress_var:
                    progress_var = tk.DoubleVar(value=0)
                    info['progress_var'] = progress_var
                bar = tk.ttk.Progressbar(bar_frame, variable=progress_var, maximum=100, length=220)
                bar.pack(side="left", fill="x", expand=True, padx=(6,6))
                # Cancel button
                cancel_btn = tk.Button(bar_frame, text="Cancel", command=lambda f=fname: self.cancel_download(f), bg="#a33", fg="#fff")
                cancel_btn.pack(side="right", padx=(6,0))
                row += 1

    def apply(self):
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Model URL is required.")
            return
        filename = url.split("/")[-1]
        dest_path = self.model_dir / filename
        cancel_flag = threading.Event()
        info = {
            'progress_var': tk.DoubleVar(value=0),
            'percent_var': tk.StringVar(value="0%"),
            'cancel_flag': cancel_flag,
        }
        self.active_downloads[filename] = info
        self.refresh_cards()
        def download():
            try:
                with urllib.request.urlopen(url) as response, open(dest_path, 'wb') as out_file:
                    total = int(response.getheader('Content-Length', 0))
                    downloaded = 0
                    chunk = 8192
                    while True:
                        if cancel_flag.is_set():
                            break
                        data = response.read(chunk)
                        if not data:
                            break
                        out_file.write(data)
                        downloaded += len(data)
                        percent = int((downloaded / total) * 100) if total else 0
                        info['progress_var'].set(percent)
                        info['percent_var'].set(f"{percent}%")
                        self.cards_frame.after(50, self.refresh_cards)
                if not cancel_flag.is_set():
                    messagebox.showinfo("Success", f"Model downloaded to {dest_path}")
            except Exception as e:
                if not cancel_flag.is_set():
                    messagebox.showerror("Download Failed", str(e))
            finally:
                del self.active_downloads[filename]
                self.cards_frame.after(100, self.refresh_cards)
        t = threading.Thread(target=download, daemon=True)
        info['thread'] = t
        t.start()

    def cancel_download(self, filename):
        info = self.active_downloads.get(filename)
        if info:
            info['cancel_flag'].set()
            del self.active_downloads[filename]
            self.refresh_cards()
