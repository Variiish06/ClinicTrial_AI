#!/usr/bin/env python3
"""
DeliriumWatch — Raspberry Pi E-Ink Pager Service (v2)
Multi-patient, multi-Pi pager with auto-rotation and fleet reporting.

Run on: Raspberry Pi (same network as laptop running Flask)
Display: Waveshare 2.13inch e-Paper HAT (V4), 250x122, B/W
"""
import sys
import os
import time
import json
import signal
import logging
import subprocess
import threading

# Add Waveshare driver library path
EPAPER_LIB = "/home/pi/e-Paper/RaspberryPi_JetsonNano/python/lib"
if os.path.exists(EPAPER_LIB):
    sys.path.append(EPAPER_LIB)

import paho.mqtt.client as mqtt
from PIL import Image, ImageDraw, ImageFont
from waveshare_epd import epd2in13_V4 as epd_driver

# ─── CONFIGURATION ───────────────────────────────────────────────
# *** CHANGE THESE PER PAGER UNIT ***
PAGER_ID   = os.environ.get("PAGER_ID", "doc1")
PAGER_ZONE = os.environ.get("PAGER_ZONE", "Bay A")

MQTT_BROKER = os.environ.get("MQTT_BROKER", "172.20.10.5")
MQTT_PORT   = int(os.environ.get("MQTT_PORT", "1883"))

ROTATE_INTERVAL = 8      # Seconds between patient rotations
CLEAR_AFTER     = 300     # Clear alerts after 5 min
HEARTBEAT_EVERY = 10      # Heartbeat interval (seconds)
RSSI_EVERY      = 30      # RSSI report interval (seconds)

# MQTT Topics
TOPIC_ZONE      = f"deliriumwatch/pager/{PAGER_ID}/alerts"
TOPIC_BROADCAST = "deliriumwatch/pager/broadcast"
TOPIC_CLEAR     = f"deliriumwatch/pager/{PAGER_ID}/clear"
TOPIC_LEGACY    = "deliriumwatch/pager/doc1"  # backward compat
TOPIC_STATUS    = f"deliriumwatch/pager/{PAGER_ID}/status"
TOPIC_RSSI      = f"deliriumwatch/pager/{PAGER_ID}/rssi"

# ─── LOGGING ─────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("pager")

# ─── FONTS ───────────────────────────────────────────────────────
def load_fonts():
    try:
        return {
            "bold_18": ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 18),
            "bold_14": ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14),
            "reg_12":  ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12),
            "reg_10":  ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10),
            "reg_9":   ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 9),
        }
    except Exception:
        default = ImageFont.load_default()
        return {k: default for k in ["bold_18", "bold_14", "reg_12", "reg_10", "reg_9"]}

FONTS = load_fonts()

# ─── E-INK DISPLAY ──────────────────────────────────────────────
epd = None
W = 250  # epd.height (landscape width)
H = 122  # epd.width (landscape height)

def init_display():
    global epd, W, H
    log.info("Initializing E-Ink display...")
    try:
        epd = epd_driver.EPD()
        epd.init()
        epd.Clear(0xFF)
        W = epd.height  # 250
        H = epd.width   # 122
        log.info(f"Display ready: {H}x{W} (portrait: {epd.width}x{epd.height})")
    except Exception as e:
        log.error(f"Display init failed: {e}")
        epd = None

def render(image):
    """Push a PIL image to the display."""
    if epd:
        try:
            epd.display(epd.getbuffer(image))
        except Exception as e:
            log.error(f"Display render error: {e}")

def render_partial(image):
    """Use partial refresh for faster updates (less flicker)."""
    if epd:
        try:
            epd.displayPartial(epd.getbuffer(image))
        except Exception as e:
            # Fall back to full refresh
            render(image)

# ─── SCREEN DRAWING ─────────────────────────────────────────────
def draw_frame(draw):
    """Draw standard frame: border + header + footer."""
    # Outer border
    draw.rectangle((0, 0, W-1, H-1), outline=0, width=2)
    # Header bar
    draw.rectangle((2, 2, W-3, 22), fill=0)
    # Footer bar
    draw.rectangle((2, H-18, W-3, H-3), fill=0)

def draw_header(draw, title="DELIRIUMWATCH"):
    """Draw inverted header text."""
    draw.text((6, 4), title, font=FONTS["reg_10"], fill=255)
    draw.text((W-50, 4), time.strftime("%H:%M"), font=FONTS["reg_10"], fill=255)

def draw_footer(draw, page_text="", extra=""):
    """Draw footer with pager ID and optional page indicator."""
    draw.text((6, H-16), f"{PAGER_ID} | {PAGER_ZONE}", font=FONTS["reg_9"], fill=255)
    if page_text:
        # Right-align page indicator
        draw.text((W-55, H-16), page_text, font=FONTS["reg_9"], fill=255)
    if extra:
        draw.text((W//2-20, H-16), extra, font=FONTS["reg_9"], fill=255)

def draw_risk_bar(draw, risk_raw, y=88):
    """Draw a horizontal risk bar proportional to risk percentage."""
    bar_x = 8
    bar_w = W - 16
    bar_h = 8
    # Background
    draw.rectangle((bar_x, y, bar_x + bar_w, y + bar_h), outline=0)
    # Filled portion
    fill_w = int(bar_w * min(1.0, risk_raw))
    if fill_w > 0:
        draw.rectangle((bar_x, y, bar_x + fill_w, y + bar_h), fill=0)

def make_standby_screen():
    """Create the idle/waiting screen."""
    img = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(img)
    draw_frame(draw)
    draw_header(draw)

    draw.text((W//2 - 60, 32), "PAGER ACTIVE", font=FONTS["bold_18"], fill=0)
    draw.text((W//2 - 65, 56), "Waiting for alerts...", font=FONTS["reg_12"], fill=0)
    draw.text((W//2 - 50, 76), f"Broker: {MQTT_BROKER}", font=FONTS["reg_9"], fill=0)
    draw.text((W//2 - 40, 90), f"Zone: {PAGER_ZONE}", font=FONTS["reg_10"], fill=0)

    draw_footer(draw)
    return img

def make_alert_screen(patient, bed, risk, risk_raw, action, label, page_text=""):
    """Create an alert screen for a single patient."""
    img = Image.new("1", (W, H), 255)
    draw = ImageDraw.Draw(img)
    draw_frame(draw)

    # Header — alert style
    title = "!! DELIRIUM ALERT" if label == "HIGH" else "! RISK ALERT"
    draw_header(draw, title)

    # Patient name (truncate if needed)
    name_display = patient[:20] if len(patient) > 20 else patient
    draw.text((8, 26), name_display, font=FONTS["bold_18"], fill=0)

    # Bed location
    draw.text((8, 48), f"BED: {bed}", font=FONTS["reg_12"], fill=0)

    # Risk percentage — large
    draw.text((8, 64), f"RISK: {risk}", font=FONTS["bold_14"], fill=0)

    # Risk bar
    draw_risk_bar(draw, risk_raw, y=84)

    # Action text (inverted bar above footer)
    draw.rectangle((2, 96, W-3, H-19), fill=0)
    draw.text((8, 99), f"ACTION: {action}", font=FONTS["reg_10"], fill=255)

    draw_footer(draw, page_text=page_text)
    return img

# ─── ALERT QUEUE ─────────────────────────────────────────────────
alert_lock = threading.Lock()
alert_queue: list = []  # List of patient dicts, sorted by risk_raw desc
current_page = 0
last_alert_time = 0
last_rotate_time = 0

def update_alerts(new_alerts):
    """Replace the queue with the latest incoming alert to stop rotation."""
    global last_alert_time, current_page
    with alert_lock:
        alert_queue.clear()
        for alert in new_alerts:
            alert_queue.append(alert)
        
        # If an array was sent, sort by risk and keep only the top 1
        if alert_queue:
            alert_queue.sort(key=lambda a: a.get("risk_raw", 0), reverse=True)
            del alert_queue[1:]
            
        current_page = 0
        last_alert_time = time.time()

def clear_alerts():
    """Clear all alerts."""
    global last_alert_time, current_page
    with alert_lock:
        alert_queue.clear()
        current_page = 0
        last_alert_time = 0

def get_current_alert():
    """Get the current alert to display and page info."""
    with alert_lock:
        if not alert_queue:
            return None, "", 0
        idx = current_page % len(alert_queue)
        total = len(alert_queue)
        page_text = f"[{idx+1}/{total}]" if total > 1 else ""
        return alert_queue[idx], page_text, total

def advance_page():
    """Move to the next patient in the queue."""
    global current_page
    with alert_lock:
        if alert_queue:
            current_page = (current_page + 1) % len(alert_queue)

# ─── WIFI RSSI ──────────────────────────────────────────────────
def get_wifi_rssi():
    """Get WiFi signal strength in dBm."""
    try:
        result = subprocess.run(
            ["iwconfig", "wlan0"],
            capture_output=True, text=True, timeout=3
        )
        for line in result.stdout.split("\n"):
            if "Signal level" in line:
                # Parse "Signal level=-42 dBm"
                parts = line.split("Signal level=")
                if len(parts) > 1:
                    val = parts[1].split(" ")[0].strip()
                    return int(val)
    except Exception:
        pass
    return -100

# ─── MQTT CALLBACKS ──────────────────────────────────────────────
mqtt_client = None

def on_connect(client, userdata, flags, reason_code, properties):
    log.info(f"Connected to broker {MQTT_BROKER} — rc={reason_code}")
    # Subscribe to zone-specific, broadcast, clear, and legacy topics
    topics = [TOPIC_ZONE, TOPIC_BROADCAST, TOPIC_CLEAR, TOPIC_LEGACY]
    for t in topics:
        client.subscribe(t)
        log.info(f"  Subscribed: {t}")

def on_disconnect(client, userdata, flags, reason_code, properties):
    log.warning(f"Disconnected (rc={reason_code}). Auto-reconnecting...")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    log.info(f"MSG [{topic}]: {payload[:100]}")

    # Handle clear command
    if topic == TOPIC_CLEAR:
        log.info("Clear command received — resetting display.")
        clear_alerts()
        if epd:
            epd.init()
            render(make_standby_screen())
        return

    # Handle alert payload (single object or array)
    try:
        data = json.loads(payload)
        if isinstance(data, list):
            update_alerts(data)
        elif isinstance(data, dict):
            update_alerts([data])
        log.info(f"Alert queue now has {len(alert_queue)} patient(s)")
    except Exception as e:
        log.error(f"Failed to parse: {e}")

# ─── HEARTBEAT & RSSI THREADS ───────────────────────────────────
def heartbeat_thread(client):
    """Publish heartbeat status every HEARTBEAT_EVERY seconds."""
    while True:
        try:
            payload = json.dumps({
                "id": PAGER_ID,
                "zone": PAGER_ZONE,
                "status": "online",
                "alerts": len(alert_queue),
            })
            client.publish(TOPIC_STATUS, payload)
        except Exception:
            pass
        time.sleep(HEARTBEAT_EVERY)

def rssi_thread(client):
    """Publish WiFi RSSI every RSSI_EVERY seconds."""
    while True:
        try:
            rssi = get_wifi_rssi()
            payload = json.dumps({"id": PAGER_ID, "rssi": rssi})
            client.publish(TOPIC_RSSI, payload)
        except Exception:
            pass
        time.sleep(RSSI_EVERY)

# ─── SIGNAL HANDLING ─────────────────────────────────────────────
def handle_exit(signum, frame):
    log.info("Shutdown signal received, cleaning up...")
    if epd:
        try:
            epd.init()
            epd.Clear(0xFF)
            epd.sleep()
        except Exception:
            pass
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_exit)
signal.signal(signal.SIGINT, handle_exit)

# ─── MAIN ────────────────────────────────────────────────────────
def main():
    global last_rotate_time, mqtt_client

    log.info(f"=== DeliriumWatch Pager v2 ===")
    log.info(f"  PAGER_ID:   {PAGER_ID}")
    log.info(f"  PAGER_ZONE: {PAGER_ZONE}")
    log.info(f"  BROKER:     {MQTT_BROKER}:{MQTT_PORT}")

    init_display()

    # Show standby screen
    if epd:
        render(make_standby_screen())

    # MQTT setup
    mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    mqtt_client.on_connect    = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message    = on_message
    mqtt_client.reconnect_delay_set(min_delay=1, max_delay=30)

    log.info(f"Connecting to MQTT broker...")
    while True:
        try:
            mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
            break
        except Exception as e:
            log.warning(f"Broker unreachable ({e}), retrying in 5s...")
            time.sleep(5)

    mqtt_client.loop_start()

    # Start heartbeat and RSSI threads
    threading.Thread(target=heartbeat_thread, args=(mqtt_client,), daemon=True).start()
    threading.Thread(target=rssi_thread, args=(mqtt_client,), daemon=True).start()

    # Prepare for partial refresh
    if epd:
        try:
            base_img = make_standby_screen()
            epd.displayPartBaseImage(epd.getbuffer(base_img))
        except Exception:
            pass

    last_rotate_time = time.time()
    displaying_standby = True

    try:
        while True:
            now = time.time()
            alert, page_text, total = get_current_alert()

            if alert:
                displaying_standby = False
                # Check if it's time to rotate
                if total > 1 and (now - last_rotate_time >= ROTATE_INTERVAL):
                    advance_page()
                    alert, page_text, total = get_current_alert()
                    last_rotate_time = now

                # Render current alert
                if alert and epd:
                    img = make_alert_screen(
                        patient=alert.get("patient", "UNKNOWN"),
                        bed=alert.get("bed", "N/A"),
                        risk=alert.get("risk", "?%"),
                        risk_raw=alert.get("risk_raw", 0.5),
                        action=alert.get("action", "EVALUATE"),
                        label=alert.get("label", "HIGH"),
                        page_text=page_text,
                    )
                    try:
                        render_partial(img)
                    except Exception:
                        epd.init()
                        render(img)
                        epd.displayPartBaseImage(epd.getbuffer(img))

            elif not displaying_standby:
                # No alerts — check if we should return to standby
                if last_alert_time and (now - last_alert_time > CLEAR_AFTER):
                    log.info("Alerts expired, returning to standby.")
                    clear_alerts()
                    if epd:
                        epd.init()
                        render(make_standby_screen())
                    displaying_standby = True

            time.sleep(1)

    except KeyboardInterrupt:
        pass
    finally:
        mqtt_client.loop_stop()
        handle_exit(None, None)


if __name__ == "__main__":
    main()
