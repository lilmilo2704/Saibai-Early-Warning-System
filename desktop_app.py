# desktop_app.py
import tkinter as tk
from tkinter import ttk, messagebox
import json, os, yaml, threading, time, subprocess, sys
from datetime import datetime
import core  # shared logic

BASE_DIR = os.path.dirname(__file__)

def play_alarm():
    # Cross-platform attempt
    try:
        if sys.platform.startswith("win"):
            import winsound
            winsound.Beep(1000, 700); winsound.Beep(1200, 700); winsound.Beep(1000, 700)
        elif sys.platform == "darwin":
            subprocess.call(["afplay", "/System/Library/Sounds/Glass.aiff"])
        else:
            # linux
            subprocess.call(["paplay", "/usr/share/sounds/freedesktop/stereo/alarm-clock-elapsed.oga"])
    except Exception as e:
        print("Alarm sound fallback:", e)

def desktop_notify(title, body):
    try:
        if sys.platform.startswith("win"):
            # Simple Tk popup for portability
            messagebox.showinfo(title, body[:500])
        elif sys.platform == "darwin":
            subprocess.call(["osascript", "-e", f'display notification "{body[:120]}" with title "{title}"'])
        else:
            subprocess.call(["notify-send", title, body[:160]])
    except Exception as e:
        print("Notification fallback:", e)
        messagebox.showinfo(title, body[:500])

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Saibai EWS – MVP Desktop")
        self.geometry("980x720")
        self._build_ui()

    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)

        self.sender = SenderFrame(nb)
        self.dashboard = DashboardFrame(nb)

        nb.add(self.sender, text="Sender (IMS)")
        nb.add(self.dashboard, text="Receiver Dashboard")

class SenderFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        # Hazard & severity
        row = 0
        ttk.Label(self, text="Hazard").grid(row=row, column=0, sticky="w")
        self.hazard = ttk.Combobox(self, values=["FLOOD", "CYCLONE", "BUSHFIRE"], state="readonly")
        self.hazard.set("FLOOD"); self.hazard.grid(row=row, column=1, sticky="ew")

        ttk.Label(self, text="Severity").grid(row=row, column=2, sticky="w")
        self.sev = ttk.Combobox(self, values=["Advice", "Watch", "Warning", "WatchAndAct", "Emergency"], state="readonly")
        self.sev.set("Warning"); self.sev.grid(row=row, column=3, sticky="ew")

        row += 1
        ttk.Label(self, text="Area").grid(row=row, column=0, sticky="w")
        self.area = ttk.Entry(self); self.area.insert(0, "Saibai Island low-lying areas")
        self.area.grid(row=row, column=1, columnspan=3, sticky="ew")

        row += 1
        ttk.Label(self, text="Effective From (ISO)").grid(row=row, column=0, sticky="w")
        self.eff = ttk.Entry(self); self.eff.insert(0, datetime.now().isoformat(timespec='minutes'))
        self.eff.grid(row=row, column=1, sticky="ew")

        ttk.Label(self, text="Expected Until (ISO)").grid(row=row, column=2, sticky="w")
        self.until = ttk.Entry(self); self.until.insert(0, (datetime.now()).isoformat(timespec='minutes'))
        self.until.grid(row=row, column=3, sticky="ew")

        # Sections (English & Kalaw Kawaw Ya)
        def mk_text(label, rbase):
            ttk.Label(self, text=label+" (EN)").grid(row=rbase, column=0, sticky="nw")
            t_en = tk.Text(self, height=3, width=40); t_en.grid(row=rbase, column=1, sticky="nsew")
            ttk.Label(self, text=label+" (KKYA)").grid(row=rbase, column=2, sticky="nw")
            t_kk = tk.Text(self, height=3, width=40); t_kk.grid(row=rbase, column=3, sticky="nsew")
            return t_en, t_kk

        self.sections = {}
        labels = [("Issued", "issued"), ("Next update", "next_update"), ("What we are expecting", "expecting"),
                  ("What you need to do", "actions"), ("Support & recovery help", "support"),
                  ("For more information", "more_info")]
        row += 1
        for i, (label, key) in enumerate(labels):
            t_en, t_kk = mk_text(label, row)
            self.sections[key] = (t_en, t_kk)
            row += 1

        # Issuer/Contact
        ttk.Label(self, text="Issuer").grid(row=row, column=0, sticky="w")
        self.issuer = ttk.Entry(self); self.issuer.insert(0, "Saibai Disaster Management")
        self.issuer.grid(row=row, column=1, sticky="ew")

        ttk.Label(self, text="Contact").grid(row=row, column=2, sticky="w")
        self.contact = ttk.Entry(self); self.contact.insert(0, "07 0000 0000")
        self.contact.grid(row=row, column=3, sticky="ew")

        row += 1
        # Buttons
        bar = ttk.Frame(self); bar.grid(row=row, column=0, columnspan=4, sticky="ew", pady=8)
        ttk.Button(bar, text="Ring Office Alarm", command=self.ring_alarm).pack(side="left")
        ttk.Button(bar, text="Send Warning", command=self.send_warning).pack(side="left", padx=6)
        ttk.Button(bar, text="Notify Desktop", command=lambda: desktop_notify("EWS Alert", "Local desktop notification triggered.")).pack(side="left", padx=6)

        # make cols expand
        for c in range(4):
            self.grid_columnconfigure(c, weight=1)

    def ring_alarm(self):
        play_alarm()
        desktop_notify("Office Alarm", "Alarm sounded in the office (prototype).")

    def send_warning(self):
        hazard = self.hazard.get()
        severity = self.sev.get()
        area = self.area.get()
        tpl = {
            "template_version": "0.2-desktop",
            "hazard": hazard,
            "incident_id": f"{datetime.now().strftime('%Y%m%d%H%M%S')}-Saibai-{hazard}-GUI",
            "severity": severity,
            "area": area,
            "effective_from": self.eff.get(),
            "expected_until": self.until.get(),
            "msg": {
                "en": "", "kkya": ""
            },
            "sections": {},
            "channels_hint": [],
            "auto_fill": { "issuer": self.issuer.get(), "contact": self.contact.get() }
        }
        # sections
        for key, (t_en, t_kk) in self.sections.items():
            tpl["sections"][key] = {
                "en": t_en.get("1.0", "end").strip(),
                "kkya": t_kk.get("1.0", "end").strip()
            }
        # simple heuristics for channels
        tpl["channels_hint"] = ["sms","email","voice","meshtastic"]
        inc_id = core.ingest_incident(tpl)
        tr = core.triage(inc_id)
        core.queue_deliveries(tr)

        # orchestrate send in a thread (non-blocking UI)
        def run_send():
            core.orchestrate_sends(inc_id)
            desktop_notify("EWS – Sent", f"Incident {inc_id} processed.")
        threading.Thread(target=run_send, daemon=True).start()
        messagebox.showinfo("Queued", f"Incident {inc_id} queued for delivery.")

class DashboardFrame(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=10)
        self.tree = ttk.Treeview(self, columns=("incident","contact","status","attempts","last"), show="headings")
        for c, w in [("incident", 260), ("contact", 220), ("status", 120), ("attempts", 90), ("last", 180)]:
            self.tree.heading(c, text=c.title()); self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill="both", expand=True)
        btn = ttk.Frame(self); btn.pack(fill="x", pady=6)
        ttk.Button(btn, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(btn, text="Ack Stats", command=self.show_ack_stats).pack(side="left", padx=6)
        self.refresh()

    def refresh(self):
        for i in self.tree.get_children():
            self.tree.delete(i)
        deliveries = core.load_json(core.DELIVERIES)
        for did, d in deliveries.items():
            self.tree.insert("", "end", values=(d["incident_id"], d["contact"]["name"], d["status"], d["attempts"], d["last_attempt"]))

    def show_ack_stats(self):
        acks = core.load_json(core.ACKS)
        messagebox.showinfo("Acknowledgements", f"Acks: {len(acks)}")
        
if __name__ == "__main__":
    App().mainloop()
