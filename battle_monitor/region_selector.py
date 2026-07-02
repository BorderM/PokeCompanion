from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from typing import Optional


@dataclass
class Rect:
    x: int
    y: int
    w: int
    h: int

    def normalized(self) -> "Rect":
        x1 = min(self.x, self.x + self.w)
        y1 = min(self.y, self.y + self.h)
        x2 = max(self.x, self.x + self.w)
        y2 = max(self.y, self.y + self.h)
        return Rect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))

    def to_dict(self):
        return {"x": self.x, "y": self.y, "w": self.w, "h": self.h}

    @classmethod
    def from_dict(cls, data):
        return cls(int(data["x"]), int(data["y"]), int(data["w"]), int(data["h"]))


def select_screen_region(parent: tk.Tk, title: str = "Drag to select region") -> Optional[Rect]:
    result: dict[str, Optional[Rect]] = {"rect": None}

    overlay = tk.Toplevel(parent)
    overlay.title(title)
    overlay.attributes("-fullscreen", True)
    overlay.attributes("-topmost", True)
    overlay.attributes("-alpha", 0.28)
    overlay.configure(bg="black")
    overlay.cursor = "crosshair"

    canvas = tk.Canvas(overlay, bg="black", highlightthickness=0)
    canvas.pack(fill="both", expand=True)
    instruction = canvas.create_text(
        30,
        30,
        anchor="nw",
        fill="white",
        text=f"{title}\nDrag a rectangle, release to accept. Press Esc to cancel.",
        font=("Segoe UI", 16, "bold"),
    )

    start = {"x": 0, "y": 0}
    rect_id = {"id": None}

    def on_down(event):
        start["x"] = overlay.winfo_pointerx()
        start["y"] = overlay.winfo_pointery()
        if rect_id["id"]:
            canvas.delete(rect_id["id"])
        rect_id["id"] = canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="red", width=3)

    def on_drag(event):
        if rect_id["id"]:
            canvas.coords(rect_id["id"], start["x"], start["y"], overlay.winfo_pointerx(), overlay.winfo_pointery())

    def on_up(event):
        end_x = overlay.winfo_pointerx()
        end_y = overlay.winfo_pointery()
        rect = Rect(start["x"], start["y"], end_x - start["x"], end_y - start["y"]).normalized()
        if rect.w >= 10 and rect.h >= 10:
            result["rect"] = rect
        overlay.destroy()

    def on_cancel(event=None):
        result["rect"] = None
        overlay.destroy()

    overlay.bind("<Escape>", on_cancel)
    canvas.bind("<ButtonPress-1>", on_down)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_up)
    overlay.grab_set()
    parent.wait_window(overlay)
    return result["rect"]
