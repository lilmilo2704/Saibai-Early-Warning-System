# core.py
import os, json, yaml, uuid, random
from datetime import datetime

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "data")
CONFIG = yaml.safe_load(open(os.path.join(BASE_DIR, "config.yaml")))
ROUTING = yaml.safe_load(open(os.path.join(BASE_DIR, "routing_rules.yaml")))

INCIDENTS = os.path.join(DATA_DIR, "incidents.json")
DELIVERIES = os.path.join(DATA_DIR, "deliveries.json")
ACKS = os.path.join(DATA_DIR, "acks.json")

os.makedirs(DATA_DIR, exist_ok=True)
for f in [INCIDENTS, DELIVERIES, ACKS]:
    if not os.path.exists(f):
        open(f, "w").write("{}")

def load_json(p):
    try:
        with open(p) as fh:
            return json.load(fh)
    except:
        return {}

def save_json(p, obj):
    open(p, "w").write(json.dumps(obj, indent=2))

def now_iso():
    return datetime.now().isoformat(timespec='seconds')

# --------- Channel stubs / integrations ---------
def send_email(to, subject, body):
    print(f"[EMAIL] → {to}: {subject}\n{body}\n"); return True

def send_sms(to, body):
    print(f"[SMS] → {to}: {body}"); return True

def send_voice_call(to, body):
    print(f"[VOICE] calling {to}: '{body[:120]}...'"); return True

def send_meshtastic(body):
    print(f"[MESH] packets:")
    from utils.meshtastic_shorthand import apply_shorthand, split_for_mesh
    max_chars = CONFIG["meshtastic"]["max_chars"]
    mapping = CONFIG["meshtastic"]["shorthand_map"]
    compact = apply_shorthand(body, mapping)
    parts = split_for_mesh(compact, max_chars)
    for i, p in enumerate(parts, 1):
        print(f"  - [{i}/{len(parts)}] {p}")
    return True

def send_radio(body):
    print(f"[RADIO] broadcast placeholder: '{body[:160]}'"); return True

CHANNEL_FUNCS = {
    #"email": send_email,
    "email": lambda to, msg: send_email(to, *msg.split('\n', 1)),
    "sms": send_sms,
    "voice": send_voice_call,
    "meshtastic": lambda _to, body: send_meshtastic(body),
    "radio": lambda _to, body: send_radio(body),
}

def ack_key(incident_id, contact):
    return f"{incident_id}:{contact}"

# --------- Business logic ---------
def ingest_incident(tpl: dict):
    incs = load_json(INCIDENTS)
    incs[tpl["incident_id"]] = tpl
    save_json(INCIDENTS, incs)
    return tpl["incident_id"]

def triage(incident_id: str):
    incs = load_json(INCIDENTS)
    tpl = incs.get(incident_id)
    if not tpl: return None
    hazard = tpl["hazard"]
    severity = tpl["severity"]
    default_order = CONFIG["channels"]["order_default"]
    hazard_order = CONFIG["channels"]["order_by_hazard"].get(hazard, default_order)
    rule = ROUTING["rules"].get(hazard)
    if not rule:
        recipients_groups = []
        preferred = hazard_order
    else:
        recipients_groups = rule["recipients"]
        preferred = rule["severity_channels"].get(severity, hazard_order)
    if "channels_hint" in tpl:
        merged = []
        for c in preferred + [c for c in hazard_order if c not in preferred]:
            if c not in merged: merged.append(c)
        for c in tpl["channels_hint"]:
            if c not in merged: merged.append(c)
        preferred = merged
    return {
        "incident_id": incident_id,
        "hazard": hazard,
        "severity": severity,
        "area": tpl.get("area",""),
        "channels": preferred,
        "recipients_groups": recipients_groups,
        "lang_available": list(tpl.get("msg", {}).keys())
    }

def expand_recipients(groups):
    out = []
    for g in groups or []:
        out.extend(CONFIG["contacts"]["groups"].get(g, []))
    return out

def build_message(tpl, lang="en"):
    # Compose from rich sections if provided
    sections = tpl.get("sections", {})
    bullets = []
    order = ["issued", "next_update", "expecting", "actions", "support", "more_info"]
    for key in order:
        val = sections.get(key, {}).get(lang) or sections.get(key, {}).get("en")
        if val: bullets.append(f"{val}")
    base_msg = "\n\n".join(bullets) if bullets else (tpl.get("msg", {}).get(lang) or tpl.get("msg", {}).get("en",""))
    footer = f"\n\nIssuer: {tpl['auto_fill'].get('issuer','')}. Contact: {tpl['auto_fill'].get('contact','')}."
    subject = f"{tpl['hazard']} {tpl['severity']} – {tpl.get('area','')}"
    return subject, base_msg + footer

def queue_deliveries(triage_obj):
    deliveries = load_json(DELIVERIES)
    inc_id = triage_obj["incident_id"]
    contacts = expand_recipients(triage_obj["recipients_groups"])
    for c in contacts:
        key = str(uuid.uuid4())
        deliveries[key] = {
            "incident_id": inc_id, "contact": c, "status": "queued",
            "attempts": 0, "channel_index": 0, "last_attempt": None, "acknowledged": False
        }
    save_json(DELIVERIES, deliveries)
    return len(contacts)

def attempt_send(delivery_id, triage_obj):
    deliveries = load_json(DELIVERIES)
    acks = load_json(ACKS)
    incs = load_json(INCIDENTS)
    d = deliveries.get(delivery_id)
    if not d: return None
    tpl = incs[d["incident_id"]]
    channels = triage_obj["channels"]
    idx = d["channel_index"]
    if idx >= len(channels):
        d["status"] = "failed"
        deliveries[delivery_id] = d; save_json(DELIVERIES, deliveries)
        return {"status": "failed", "reason": "no_more_channels"}
    channel = channels[idx]
    lang = "kkya" if "Saibai" in d["contact"]["name"] and "kkya" in triage_obj["lang_available"] else "en"
    subject, body = build_message(tpl, lang=lang)
    to = d["contact"].get("email") if channel=="email" else d["contact"].get("phone") or d["contact"].get("voice")
    ok = CHANNEL_FUNCS[channel](to, subject + ("\n" if channel=="email" else " | ") + body)
    d["attempts"] += 1
    d["last_attempt"] = now_iso()
    if ok and random.random() < 0.6:
        acks[ack_key(d["incident_id"], d["contact"]["name"])] = {"ts": now_iso(), "via": channel}
        d["acknowledged"] = True
        d["status"] = "delivered"
    else:
        d["channel_index"] += 1
        d["status"] = "retry_pending"
    deliveries[delivery_id] = d
    save_json(DELIVERIES, deliveries)
    save_json(ACKS, acks)
    return d

def orchestrate_sends(incident_id):
    triage_obj = triage(incident_id)
    if not triage_obj: return {"error": "incident not found"}
    queued = queue_deliveries(triage_obj)
    deliveries = load_json(DELIVERIES)
    results = []
    for did, d in deliveries.items():
        if d["incident_id"] != incident_id: continue
        # try multiple attempts per contact until ack or max attempts
        max_attempts = CONFIG["retry_policy"]["max_attempts"]
        for _ in range(max_attempts):
            res = attempt_send(did, triage_obj)
            if res and res.get("acknowledged") or deliveries[did]["acknowledged"]:
                break
    return {"queued": queued}
