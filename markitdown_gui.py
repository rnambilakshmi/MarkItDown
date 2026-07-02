#!/usr/bin/env python3
"""
MarkItDown GUI — minimalist drag-and-drop converter.

Wraps the `markitdown` CLI (installed via pipx) in a small desktop app.
Drag files onto the window (or click to browse) and each one is converted
to a .md file using `markitdown <file> -o <output>.md`.

ONE-TIME SETUP (drag-and-drop support):
    pip install tkinterdnd2 --break-system-packages
    (inside a virtualenv, drop the --break-system-packages flag)

    If this package is missing the app still runs, but you'll need to use
    the "Browse Files..." button instead of dragging files in.

RUN:
    python3 markitdown_gui.py
    (or double-click "Run MarkItDown GUI.command" next to this file)

WHERE FILES ARE SAVED:
    By default, each converted file is saved as <original-name>.md in the
    SAME FOLDER as the original file. You can switch to a custom output
    folder from within the app. The active save location is always shown
    at the top of the window, and the full path of each converted file is
    shown in the log after conversion.
"""

import os
import sys
import shutil
import subprocess
import threading
import queue
import time
from pathlib import Path

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    HAS_DND = True
except ImportError:
    HAS_DND = False

APP_TITLE = "MarkItDown Converter"

# Where pipx / common installers typically put the markitdown executable,
# checked in order if it isn't already on PATH.
CANDIDATE_PATHS = [
    str(Path.home() / ".local" / "bin" / "markitdown"),
    str(Path.home() / ".local" / "pipx" / "venvs" / "markitdown" / "bin" / "markitdown"),
    "/opt/homebrew/bin/markitdown",
    "/usr/local/bin/markitdown",
]


def find_markitdown():
    """Locate the markitdown executable, or return None if not found."""
    which = shutil.which("markitdown")
    if which:
        return which
    for p in CANDIDATE_PATHS:
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def parse_dnd_paths(data):
    """
    tkinterdnd2 hands back a single string where paths containing spaces
    are wrapped in {curly braces} and other paths are separated by spaces.
    This turns that string into a clean list of paths.
    """
    paths = []
    buf = ""
    in_brace = False
    for ch in data:
        if ch == "{":
            in_brace = True
            buf = ""
        elif ch == "}":
            in_brace = False
            paths.append(buf)
            buf = ""
        elif ch == " " and not in_brace:
            if buf:
                paths.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        paths.append(buf)
    return paths


def reveal_in_file_manager(path):
    """Open the OS file manager and highlight/open the given folder."""
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", path], check=False)
        elif sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", path], check=False)
    except Exception:
        pass


class MarkItDownGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_TITLE)
        self.root.geometry("520x460")
        self.root.minsize(440, 380)

        self.markitdown_path = find_markitdown()
        self.output_mode = tk.StringVar(value="same")   # "same" or "custom"
        self.custom_dir = tk.StringVar(value="")
        self.last_output_dir = None

        self.task_queue = queue.Queue()
        self.result_queue = queue.Queue()

        self._build_ui()
        self._start_worker()
        self.root.after(100, self._poll_results)

        if not self.markitdown_path:
            self._log(
                "markitdown was not found on this system's PATH.\n"
                "Install it with:  pipx install markitdown\n"
                "Then restart this app.",
                kind="error",
            )

    # ---------------------------------------------------------------- UI

    def _build_ui(self):
        pad = {"padx": 12, "pady": 6}

        header = tk.Label(
            self.root, text="MarkItDown Converter",
            font=("Helvetica", 16, "bold")
        )
        header.pack(anchor="w", **pad)

        # --- Output location controls ---
        loc_frame = tk.LabelFrame(self.root, text="Save markdown to", padx=10, pady=8)
        loc_frame.pack(fill="x", padx=12, pady=(0, 6))

        same_rb = tk.Radiobutton(
            loc_frame, text="Same folder as the original file (default)",
            variable=self.output_mode, value="same", command=self._update_location_label,
        )
        same_rb.pack(anchor="w")

        custom_row = tk.Frame(loc_frame)
        custom_row.pack(anchor="w", fill="x")
        custom_rb = tk.Radiobutton(
            custom_row, text="Custom folder:",
            variable=self.output_mode, value="custom", command=self._update_location_label,
        )
        custom_rb.pack(side="left")
        choose_btn = tk.Button(custom_row, text="Choose folder...", command=self._choose_folder)
        choose_btn.pack(side="left", padx=6)

        self.location_label = tk.Label(
            loc_frame, text="", fg="#3a6b3a", anchor="w", justify="left", wraplength=470
        )
        self.location_label.pack(anchor="w", fill="x", pady=(4, 0))
        self._update_location_label()

        # --- Drop zone ---
        self.drop_zone = tk.Label(
            self.root,
            text="Drag & drop files here\n\n— or —\n\nClick to browse",
            relief="ridge", bd=2, bg="#f4f6f8", fg="#555555",
            font=("Helvetica", 12), height=6, cursor="hand2",
        )
        self.drop_zone.pack(fill="both", expand=False, padx=12, pady=6)
        self.drop_zone.bind("<Button-1>", lambda e: self._browse_files())

        if HAS_DND:
            self.drop_zone.drop_target_register(DND_FILES)
            self.drop_zone.dnd_bind("<<Drop>>", self._on_drop)
        else:
            self.drop_zone.config(
                text="Drag & drop needs one extra package.\n"
                     "Run: pip install tkinterdnd2\n\n"
                     "Click here to browse files instead."
            )

        # --- Log ---
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=12, pady=(6, 0))

        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="word",
                            font=("Menlo", 11) if sys.platform == "darwin" else ("Consolas", 10))
        self.log.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(log_frame, command=self.log.yview)
        scroll.pack(side="right", fill="y")
        self.log.config(yscrollcommand=scroll.set)

        self.log.tag_config("ok", foreground="#1a7f37")
        self.log.tag_config("error", foreground="#c0392b")
        self.log.tag_config("info", foreground="#555555")

        # --- Bottom buttons ---
        btn_row = tk.Frame(self.root)
        btn_row.pack(fill="x", padx=12, pady=8)

        tk.Button(btn_row, text="Browse Files...", command=self._browse_files).pack(side="left")
        self.reveal_btn = tk.Button(
            btn_row, text="Open Last Output Folder", command=self._open_last_output,
            state="disabled",
        )
        self.reveal_btn.pack(side="left", padx=6)
        tk.Button(btn_row, text="Clear Log", command=self._clear_log).pack(side="right")

    def _update_location_label(self):
        if self.output_mode.get() == "same":
            self.location_label.config(
                text="Each .md file will be saved next to its original file."
            )
        else:
            folder = self.custom_dir.get() or "(no folder chosen yet)"
            self.location_label.config(text=f"All .md files will be saved to:\n{folder}")

    def _choose_folder(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.custom_dir.set(folder)
            self.output_mode.set("custom")
            self._update_location_label()

    # ------------------------------------------------------------ events

    def _on_drop(self, event):
        paths = parse_dnd_paths(event.data)
        self._enqueue_paths(paths)

    def _browse_files(self):
        paths = filedialog.askopenfilenames(title="Choose files to convert")
        if paths:
            self._enqueue_paths(list(paths))

    def _enqueue_paths(self, paths):
        if self.output_mode.get() == "custom" and not self.custom_dir.get():
            messagebox.showwarning(
                APP_TITLE,
                "Choose a custom output folder first, or switch back to "
                "'Same folder as the original file'.",
            )
            return

        if not self.markitdown_path:
            self._log("Cannot convert: markitdown is not installed / not on PATH.", kind="error")
            return

        for p in paths:
            p = p.strip()
            if not p:
                continue
            if os.path.isdir(p):
                self._log(f"Skipped folder (drop individual files): {p}", kind="info")
                continue
            if not os.path.isfile(p):
                self._log(f"Skipped (not found): {p}", kind="error")
                continue
            out_dir = self.custom_dir.get() if self.output_mode.get() == "custom" else os.path.dirname(p)
            self.task_queue.put((p, out_dir))
            self._log(f"Queued: {os.path.basename(p)}", kind="info")

    # ------------------------------------------------------------ worker

    def _start_worker(self):
        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()

    def _worker_loop(self):
        while True:
            src, out_dir = self.task_queue.get()
            try:
                self._convert_one(src, out_dir)
            except Exception as exc:  # noqa: BLE001
                self.result_queue.put(("error", src, None, str(exc)))
            self.task_queue.task_done()

    def _convert_one(self, src, out_dir):
        stem = Path(src).stem
        out_path = str(Path(out_dir) / f"{stem}.md")
        cmd = [self.markitdown_path, src, "-o", out_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0 and os.path.isfile(out_path):
            self.result_queue.put(("ok", src, out_path, proc.stderr.strip()))
        else:
            err = proc.stderr.strip() or f"markitdown exited with code {proc.returncode}"
            # Keep only the most useful last line(s) of a traceback.
            err_lines = [l for l in err.splitlines() if l.strip()]
            short_err = err_lines[-1] if err_lines else err
            self.result_queue.put(("error", src, out_path, short_err))

    # ------------------------------------------------------------- poll

    def _poll_results(self):
        try:
            while True:
                status, src, out_path, detail = self.result_queue.get_nowait()
                name = os.path.basename(src)
                if status == "ok":
                    self._log(f"✓ {name} → {out_path}", kind="ok")
                    self.last_output_dir = os.path.dirname(out_path)
                    self.reveal_btn.config(state="normal")
                else:
                    self._log(f"✗ {name} failed: {detail}", kind="error")
        except queue.Empty:
            pass
        self.root.after(150, self._poll_results)

    # -------------------------------------------------------------- log

    def _log(self, text, kind="info"):
        self.log.config(state="normal")
        timestamp = time.strftime("%H:%M:%S")
        self.log.insert("end", f"[{timestamp}] {text}\n", kind)
        self.log.see("end")
        self.log.config(state="disabled")

    def _clear_log(self):
        self.log.config(state="normal")
        self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    def _open_last_output(self):
        if self.last_output_dir:
            reveal_in_file_manager(self.last_output_dir)


def main():
    root = TkinterDnD.Tk() if HAS_DND else tk.Tk()
    MarkItDownGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
