"""PhoneCam Hub: receives the phone's pose, applies your settings, forwards it to opentrack."""
import json
import os
import socket
import struct
import sys
import threading
import time

PORT = 4243                     # phone -> hub
OPENTRACK = ("127.0.0.1", 4242)  # hub -> opentrack ("UDP over network" input)
CFG_PATH = os.path.join(os.path.expanduser("~"), ".phonecam_hub.json")
AXES = ["X", "Y", "Z", "Yaw", "Pitch", "Roll"]
DEFAULTS = {"rot": 1.0, "pos": 1.0, "smooth": 0.3, "inv": [False] * 6, "forward": True,
            "mouse": 12.0, "hold_rmb": True}


def load_cfg():
    cfg = json.loads(json.dumps(DEFAULTS))
    try:
        with open(CFG_PATH) as f:
            cfg.update(json.load(f))
    except Exception:
        pass
    return cfg


def save_cfg(cfg):
    try:
        with open(CFG_PATH, "w") as f:
            json.dump(cfg, f)
    except Exception:
        pass


def local_ips():
    ips = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ips.add(info[4][0])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    return sorted(i for i in ips if not i.startswith("127."))


# ---- Mouse emulation (Windows). Used by "Mouse look mode" for cameras that only take mouse input.
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]

    class _UNION(ctypes.Union):
        _fields_ = [("mi", _MOUSEINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]

    def _send_mouse(flags, dx=0, dy=0):
        inp = _INPUT(type=0, u=_UNION(mi=_MOUSEINPUT(dx, dy, 0, flags, 0, 0)))
        ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(_INPUT))

    def mouse_move(dx, dy):
        _send_mouse(0x0001, dx, dy)  # MOUSEEVENTF_MOVE (relative)

    def mouse_button(down):
        _send_mouse(0x0008 if down else 0x0010)  # right button down / up

    def key_down(vk):
        return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
else:
    def mouse_move(dx, dy):
        pass

    def mouse_button(down):
        pass

    def key_down(vk):
        return False

VK_F8 = 0x77


class Core:
    def __init__(self, cfg):
        self.cfg = cfg
        self.ref = None
        self.prev = None
        self.out = [0.0] * 6
        self.recenter_req = True
        self.last_rx = 0.0
        self.last_addr = None
        self.error = None
        self.mouse_on = False
        self.last_m = None
        self.acc_x = 0.0
        self.acc_y = 0.0
        self.fwd = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def process(self, raw):
        c = self.cfg
        if self.recenter_req:
            self.ref = list(raw)
            self.prev = None
            self.recenter_req = False
        v = [raw[i] - self.ref[i] for i in range(6)]
        v[3] = (v[3] + 180) % 360 - 180
        for i in range(6):
            v[i] *= c["pos"] if i < 3 else c["rot"]
            if c["inv"][i]:
                v[i] = -v[i]
        a = 1.0 - c["smooth"]
        if self.prev is not None:
            v = [p + (n - p) * a for p, n in zip(self.prev, v)]
        self.prev = v
        self.out = v
        return v

    def set_mouse(self, on):
        """Mouse look mode: phone rotation drives the mouse instead of opentrack head tracking."""
        if on == self.mouse_on:
            return
        self.mouse_on = on
        self.last_m = None
        self.acc_x = self.acc_y = 0.0
        if self.cfg["hold_rmb"]:
            mouse_button(on)
        if on:  # park the in-cab view in the middle while mouse mode is active
            try:
                self.fwd.sendto(struct.pack("<6d", *([0.0] * 6)), OPENTRACK)
            except OSError:
                pass

    def _mouse(self, v):
        if self.last_m is None:
            self.last_m = list(v)
            return
        dyaw = (v[3] - self.last_m[3] + 180) % 360 - 180
        dpitch = v[4] - self.last_m[4]
        self.last_m = list(v)
        k = self.cfg["mouse"]
        self.acc_x += dyaw * k
        self.acc_y += -dpitch * k
        ix, iy = int(self.acc_x), int(self.acc_y)
        self.acc_x -= ix
        self.acc_y -= iy
        if ix or iy:
            mouse_move(ix, iy)

    def serve(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind(("0.0.0.0", PORT))
        except OSError as e:
            self.error = f"Cannot open UDP port {PORT}: {e}"
            return
        while True:
            try:
                data, addr = sock.recvfrom(1024)
            except OSError:
                continue
            if data.startswith(b"PHONECAM_DISCOVER"):
                try:
                    sock.sendto(b"PHONECAM_HUB", addr)
                except OSError:
                    pass
                continue
            if len(data) < 48:
                continue
            v = self.process(struct.unpack("<6d", data[:48]))
            if self.mouse_on:
                self._mouse(v)
            self.last_rx = time.time()
            self.last_addr = addr[0]
            if self.cfg["forward"] and not self.mouse_on:
                try:
                    self.fwd.sendto(struct.pack("<6d", *v), OPENTRACK)
                except OSError:
                    pass


def main():
    import tkinter as tk
    from tkinter import ttk

    cfg = load_cfg()
    core = Core(cfg)
    threading.Thread(target=core.serve, daemon=True).start()

    root = tk.Tk()
    root.title("PhoneCam Hub")
    root.geometry("500x720")
    pad = {"padx": 12, "pady": 4}

    ttk.Label(root, text="PhoneCam Hub", font=("Segoe UI", 16, "bold")).pack(anchor="w", **pad)
    ips = ", ".join(local_ips()) or "unknown"
    ttk.Label(root, text=f"This PC's address: {ips}", wraplength=440).pack(anchor="w", **pad)
    status = ttk.Label(root, text="Waiting for phone...")
    status.pack(anchor="w", **pad)
    live = ttk.Label(root, text="", font=("Consolas", 9))
    live.pack(anchor="w", **pad)

    def slider(label, key, lo, hi):
        frame = ttk.Frame(root)
        frame.pack(fill="x", **pad)
        val = ttk.Label(frame, text=f"{cfg[key]:.2f}", width=5)
        ttk.Label(frame, text=label, width=24).pack(side="left")

        def on_change(v, key=key, val=val):
            cfg[key] = float(v)
            val.config(text=f"{float(v):.2f}")

        s = ttk.Scale(frame, from_=lo, to=hi, command=on_change)
        s.set(cfg[key])
        s.pack(side="left", fill="x", expand=True)
        val.pack(side="left")

    slider("Rotation sensitivity", "rot", 0.2, 3.0)
    slider("Movement sensitivity", "pos", 0.0, 3.0)
    slider("Smoothing", "smooth", 0.0, 0.95)
    slider("Mouse sensitivity (px/deg)", "mouse", 2.0, 40.0)

    ttk.Label(root, text="Invert axes (tick if a direction is backwards):").pack(anchor="w", **pad)
    inv_frame = ttk.Frame(root)
    inv_frame.pack(anchor="w", **pad)
    inv_vars = []
    for i, name in enumerate(AXES):
        var = tk.BooleanVar(value=cfg["inv"][i])
        inv_vars.append(var)

        def on_inv(i=i, var=var):
            cfg["inv"][i] = var.get()

        ttk.Checkbutton(inv_frame, text=name, variable=var, command=on_inv).grid(row=0, column=i, padx=4)

    fwd_var = tk.BooleanVar(value=cfg["forward"])

    def on_fwd():
        cfg["forward"] = fwd_var.get()

    ttk.Checkbutton(root, text="Send to opentrack", variable=fwd_var, command=on_fwd).pack(anchor="w", **pad)

    mouse_var = tk.BooleanVar(value=False)

    def on_mouse():
        core.set_mouse(mouse_var.get())

    ttk.Checkbutton(root, text="Mouse look mode (hotkey F8) - for external / free camera",
                    variable=mouse_var, command=on_mouse).pack(anchor="w", **pad)
    rmb_var = tk.BooleanVar(value=cfg["hold_rmb"])

    def on_rmb():
        cfg["hold_rmb"] = rmb_var.get()

    ttk.Checkbutton(root, text="Hold right mouse button in mouse mode (needed for camera 2)",
                    variable=rmb_var, command=on_rmb).pack(anchor="w", **pad)

    def recenter():
        core.recenter_req = True

    ttk.Button(root, text="Recenter", command=recenter).pack(anchor="w", **pad)

    help_text = (
        "Setup (once): install opentrack, set Input to 'UDP over network' (port 4242) "
        "and Output to 'freetrack 2.0 Enhanced', then press Start in opentrack.\n"
        "Phone: open PhoneCam, tap 'Find PC' (or type the address above), tap Start sending."
    )
    ttk.Label(root, text=help_text, wraplength=440, foreground="gray").pack(anchor="w", **pad)

    f8 = {"prev": False}

    def poll_hotkey():
        down = key_down(VK_F8)
        if down and not f8["prev"]:
            mouse_var.set(not mouse_var.get())
            core.set_mouse(mouse_var.get())
        f8["prev"] = down
        root.after(50, poll_hotkey)

    def tick():
        if core.error:
            status.config(text=core.error, foreground="red")
        elif core.last_rx and time.time() - core.last_rx < 1.5:
            status.config(text=f"Phone connected ({core.last_addr})", foreground="green")
        else:
            status.config(text="Waiting for phone...", foreground="gray")
        o = core.out
        live.config(text="  ".join(f"{n}:{o[i]:6.1f}" for i, n in enumerate(AXES)))
        root.after(200, tick)

    def on_close():
        core.set_mouse(False)
        save_cfg(cfg)
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    tick()
    poll_hotkey()
    root.mainloop()


if __name__ == "__main__":
    main()
