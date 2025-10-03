import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

class PlaygroundDialog(tk.Toplevel):
    def __init__(self, parent, send_callback):
        super().__init__(parent)
        self.title("Prompt Playground")
        self.geometry("700x600")
        self.transient(parent)
        self.grab_set()
        self.send_callback = send_callback

        ttk.Label(self, text="Prompt:").pack(anchor="w", padx=10, pady=(10,0))
        self.prompt_text = scrolledtext.ScrolledText(self, height=8, wrap="word")
        self.prompt_text.pack(fill="x", padx=10, pady=(0,10))

        ttk.Button(self, text="Send", command=self.send_prompt).pack(pady=(0,10))

        ttk.Label(self, text="Response:").pack(anchor="w", padx=10)
        self.response_text = scrolledtext.ScrolledText(self, height=18, wrap="word")
        self.response_text.pack(fill="both", expand=True, padx=10, pady=(0,10))
        self.response_text.configure(state="disabled")

    def send_prompt(self):
        prompt = self.prompt_text.get("1.0", "end-1c").strip()
        if not prompt:
            messagebox.showwarning("Prompt Required", "Please enter a prompt.")
            return
        self.response_text.configure(state="normal")
        self.response_text.delete("1.0", "end")
        self.response_text.insert("1.0", "Running...")
        self.response_text.update()
        try:
            response = self.send_callback(prompt)
        except Exception as e:
            response = f"Error: {e}"
        self.response_text.delete("1.0", "end")
        self.response_text.insert("1.0", response)
        self.response_text.configure(state="disabled")
