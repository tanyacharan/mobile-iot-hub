#!/usr/bin/env python3
import json, math, os, subprocess, time, smtplib
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from datetime import datetime, timedelta, timezone

# ========= CONFIG =========
DEVICE_NAME   = "Nirali's iPhone"   # exact device name in ThingsBoard
HOME_LAT      = 34.02877
HOME_LNG      = -118.27968
HOME_RADIUS_M = 120                 # base "home" radius (meters)
HYSTERESIS_M  = 30                  # extra margin to avoid flapping
POLL_SEC      = 30                  # how often we check (seconds)
TZ_OFFSET_MIN = -420                # PDT ~ -420, PST ~ -480
STATE_FILE    = "/home/ubuntu/home_state.json"
CONTAINER     = "mytb"              # ThingsBoard container name

# ========= EMAIL (Gmail SMTP via env) =========
GMAIL_USER = os.getenv("GMAIL_USER")        # set in ~/.home_alerts.env
GMAIL_PASS = os.getenv("GMAIL_PASS")
TO_EMAIL   = os.getenv("TO_EMAIL", "nbmodi@usc.edu")

def send_email(subject: str, body: str):
    if not (GMAIL_USER and GMAIL_PASS and TO_EMAIL):
        print("[email] missing env vars: GMAIL_USER/GMAIL_PASS/TO_EMAIL")
        return
    msg = MIMEText(body, _charset="utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"]    = formataddr(("Home Alerts", GMAIL_USER))
    msg["To"]      = TO_EMAIL
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as s:
            s.ehlo(); s.starttls(); s.login(GMAIL_USER, GMAIL_PASS); s.send_message(msg)
        print(f"[email] sent to {TO_EMAIL}: {subject}")
    except Exception as e:
        print("[email error]", repr(e))

# ========= HELPERS =========
def haversine_m(lat1, lon1, lat2, lon2):
    R = 6371000.0
    to_rad = math.pi/180.0
    dlat = (lat2-lat1)*to_rad
    dlon = (lon2-lon1)*to_rad
    a = math.sin(dlat/2)**2 + math.cos(lat1*to_rad)*math.cos(lat2*to_rad)*math.sin(dlon/2)**2
    return 2*R*math.asin(math.sqrt(a))

def local_now():
    return datetime.now(timezone.utc) + timedelta(minutes=TZ_OFFSET_MIN)

def load_state():
    try:
        with open(STATE_FILE, "r") as f: return json.load(f)
    except Exception:
        # in_home: last decision (True/False/None). last_ts: last telemetry ts processed (ms)
        return {"in_home": None, "last_ts": 0}

def save_state(s):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f: json.dump(s, f)
    os.replace(tmp, STATE_FILE)

def query_latest_latlng():
    # query latest lat/lng for DEVICE_NAME from Postgres inside the TB container
    sql = r"""
WITH dev AS (SELECT id FROM device WHERE name = '%s'),
lat AS (
  SELECT t.ts, t.dbl_v AS lat
  FROM ts_kv t JOIN key_dictionary k ON t.key = k.key_id JOIN dev d ON t.entity_id = d.id
  WHERE k.key = 'lat' AND t.dbl_v IS NOT NULL
  ORDER BY t.ts DESC LIMIT 1
),
lng AS (
  SELECT t.ts, t.dbl_v AS lng
  FROM ts_kv t JOIN key_dictionary k ON t.key = k.key_id JOIN dev d ON t.entity_id = d.id
  WHERE (k.key = 'lng' OR k.key = 'lon') AND t.dbl_v IS NOT NULL
  ORDER BY t.ts DESC LIMIT 1
)
SELECT GREATEST(lat.ts,lng.ts), lat.lat, lng.lng FROM lat,lng LIMIT 1;
""" % DEVICE_NAME.replace("'", "''")
    cmd = [
        "sudo","docker","exec","-i",CONTAINER,
        "psql","-U","thingsboard","-d","thingsboard",
        "-tA","-F","|","-c", sql
    ]
    out = subprocess.check_output(cmd, timeout=12).decode().strip()
    if not out:
        return None
    ts, lat, lng = out.split("|")
    return {"ts": int(ts), "lat": float(lat), "lng": float(lng)}

def decide_in_home(prev_in_home: bool | None, dist_m: float) -> bool:
    """
    Hysteresis to avoid flip-flop at the boundary:
      - If we currently think we're IN, we only flip to OUT if dist > HOME_RADIUS_M + HYSTERESIS_M
      - If we currently think we're OUT, we only flip to IN if dist <= HOME_RADIUS_M
      - If unknown, use base radius.
    """
    enter_thresh = HOME_RADIUS_M
    exit_thresh  = HOME_RADIUS_M + HYSTERESIS_M
    if prev_in_home is True:
        return dist_m <= exit_thresh     # remain IN unless clearly outside
    elif prev_in_home is False:
        return dist_m <= enter_thresh    # only re-enter when clearly inside
    else:
        return dist_m <= enter_thresh

# ========= MAIN LOOP =========
def main():
    state = load_state()
    print(f"[info] Home alerts watching '{DEVICE_NAME}' @ ({HOME_LAT},{HOME_LNG}) r={HOME_RADIUS_M}m (hyst +{HYSTERESIS_M}m)")
    while True:
        try:
            row = query_latest_latlng()
        except Exception as e:
            print("[query error]", repr(e)); time.sleep(POLL_SEC); continue

        if not row:
            print("[warn] no lat/lng yet for device:", DEVICE_NAME); time.sleep(POLL_SEC); continue

        now = local_now()
        dist = int(haversine_m(row["lat"], row["lng"], HOME_LAT, HOME_LNG))
        prev_in = state.get("in_home")
        new_in  = decide_in_home(prev_in, dist_m=dist)
        ts_ms   = row["ts"]

        # Only act on NEW telemetry
        if ts_ms > state.get("last_ts", 0):
            # One-time announcement on startup
            if prev_in is None:
                if new_in:
                    send_email("At Home",  f"{DEVICE_NAME} is at home. Distance {dist} m. Time {now}.")
                else:
                    send_email("Left Home", f"{DEVICE_NAME} is away from home. Distance {dist} m. Time {now}.")
            # Transitions
            elif prev_in is True and new_in is False:
                send_email("Left Home", f"{DEVICE_NAME} just left home. Distance {dist} m. Time {now}.")
            elif prev_in is False and new_in is True:
                send_email("Back Home", f"{DEVICE_NAME} just arrived home. Distance {dist} m. Time {now}.")

            state["in_home"] = new_in
            state["last_ts"] = ts_ms
            save_state(state)

        print(f"[{now}] dist={dist}m in_home={new_in}")
        time.sleep(POLL_SEC)

if __name__ == "__main__":
    main()
