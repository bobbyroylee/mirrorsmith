#!/usr/bin/env python3
"""Tiny GUI to paste a POESESSID into, saving it to the gitignored secret file.

Keeps the cookie off the terminal/chat: you paste into the masked field, it writes
to ~/.mirrorsmith/poesessid and exits. Nothing is printed.
"""

from __future__ import annotations

from pathlib import Path

import tkinter as tk
from tkinter import messagebox

DEST = Path.home() / ".mirrorsmith" / "poesessid"


def save(value: str, root: tk.Tk) -> None:
    v = value.strip()
    if not v:
        messagebox.showwarning("mirrorsmith", "Nothing to save — paste your POESESSID first.")
        return
    DEST.parent.mkdir(parents=True, exist_ok=True)
    DEST.write_text(v, encoding="utf-8")
    messagebox.showinfo("mirrorsmith", f"Saved ({len(v)} chars) to\n{DEST}\n\nYou can close this.")
    root.destroy()


def main() -> None:
    root = tk.Tk()
    root.title("mirrorsmith — save POESESSID")
    root.geometry("460x180")
    root.attributes("-topmost", True)
    root.configure(padx=16, pady=14)

    tk.Label(
        root,
        text="Paste your POESESSID cookie value below.\n"
             "It's saved locally to a gitignored file — never shown or committed.",
        justify="left",
    ).pack(anchor="w")

    entry = tk.Entry(root, show="•", width=52)
    entry.pack(fill="x", pady=12)
    entry.focus_set()

    btns = tk.Frame(root)
    btns.pack(fill="x")
    tk.Button(btns, text="Save", width=12, default="active",
              command=lambda: save(entry.get(), root)).pack(side="right")
    tk.Button(btns, text="Cancel", width=12, command=root.destroy).pack(side="right", padx=8)

    root.bind("<Return>", lambda _e: save(entry.get(), root))
    root.bind("<Escape>", lambda _e: root.destroy())
    root.mainloop()


if __name__ == "__main__":
    main()
