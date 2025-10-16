Home Alerts — Real-Time "At Home / Left Home / Back Home" Notification System

This project automatically sends email alerts when a tracked device enters or leaves a defined “home” zone.
It integrates ThingsBoard, PostgreSQL (Docker), and Python (with Gmail App Passwords).

1. System Overview

A GPS-enabled device (via HTTP or MQTT) sends telemetry (lat, lon) to ThingsBoard.

ThingsBoard stores the data inside a PostgreSQL database (running in Docker).

A Python watcher script polls the latest telemetry and determines if the device has entered or exited the defined “home” radius.

Email notifications are sent automatically using Gmail SMTP.

Alert Types

At Home — on startup, if device is inside the home radius.

Left Home — when device exits the radius.

Back Home — when device re-enters the radius after leaving.

2. Prerequisites

Docker installed (for ThingsBoard deployment).

PostgreSQL (automatically included in ThingsBoard container).

Python 3 installed on the host machine.

Gmail account with an App Password
.

Ubuntu EC2 instance or equivalent Linux server.

3. Setup Instructions
Step 1: Connect to EC2
ssh -i "your-key.pem" ubuntu@your-ec2-public-ip

Step 2: Verify Docker is running
sudo docker ps


Ensure a container named mytb (or similar) appears.

Step 3: Access ThingsBoard

Open the browser and visit:

http://<your-ec2-public-ip>:8080


Default credentials:

Username: tenant@thingsboard.org
Password: tenant


(Change credentials in production.)

Step 4: Create .home_alerts.env
nano ~/.home_alerts.env


Add:

GMAIL_USER="your_gmail_address@gmail.com"
GMAIL_PASS="your_16_char_app_password"
TO_EMAIL="destination_email@example.com"

HOME_LAT=00.000000
HOME_LON=00.000000
RADIUS_M=120

Step 5: Save the Python Script
nano ~/home_alerts_gmail.py


Paste your watcher script here (the version that polls the PostgreSQL DB and sends alerts).

Step 6: Run the Script
set -a && source ~/.home_alerts.env && set +a
python3 ~/home_alerts_gmail.py


Expected output:

[info] Home alerts watching '<Device Name>' @ (HOME_LAT, HOME_LON) r=120m
[YYYY-MM-DD HH:MM:SS] dist=XXm in_home=True

4. Running in Background

To run continuously after logout:

nohup python3 ~/home_alerts_gmail.py > ~/home_alerts.log 2>&1 &


To view logs:

tail -f ~/home_alerts.log


To stop:

pkill -f home_alerts_gmail.py

5. Email Alert Logic
Condition	Trigger	Subject	Example
First detection	Inside radius	At Home	Device is at home
Leaving radius	Distance > RADIUS_M	Left Home	Device just left home
Returning	Distance < RADIUS_M	Back Home	Device just arrived home
6. Troubleshooting
Issue	Possible Fix
No logs updating	The device isn’t sending new telemetry; verify in ThingsBoard.
Docker permission denied	Use sudo docker ps.
No email alerts	Check Gmail App Password and .env variables.
Script stopped running	Restart with nohup python3 ~/home_alerts_gmail.py &.
7. Query to Check Latest Coordinates
sudo docker exec -it mytb psql -U thingsboard -d thingsboard -c "
WITH dev AS (SELECT id FROM device WHERE name = '<Your Device Name>')
SELECT to_timestamp(t.ts/1000.0) AS ts_utc, k.key, t.dbl_v
FROM ts_kv t
JOIN key_dictionary k ON t.key=k.key_id
JOIN dev d ON t.entity_id=d.id
WHERE k.key IN ('lat','lon')
ORDER BY ts_utc DESC
LIMIT 4;"

8. Possible Improvements

Add SMS or WhatsApp alerts using Twilio.

Log all “enter” and “exit” events into a ThingsBoard dashboard.

Support multiple users or multiple zones.
