import network
import time
import random
import rp2
import machine
import ntptime
from umqtt.simple import MQTTClient
import senko  
from secrets import secrets  # 🔐 Import your hidden credentials

# --- 1. CONFIGURATION (SAFE FOR PUBLIC GITHUB) ---
rp2.country('MY') 

# Extracting credentials securely from local secrets.py file
WIFI_SSID = secrets['wifi_ssid']
WIFI_PASS = secrets['wifi_pass']
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# 🚀 OTA Remote Update Settings
# CHANGE THESE TWO LINES TO MATCH YOUR GITHUB PROFILE EXACTLY:
GITHUB_USER = "MalcolmT05"  
GITHUB_REPO = "pico-turbine-monitor"      

# Energy Tracking Variables
hourly_energy_wh = 0.0
daily_energy_wh = 0.0
sample_count = 0
INTERVAL = 60  
current_calendar_day = None 

# Hardware Setup
led = machine.Pin("LED", machine.Pin.OUT)
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

# --- 2. OTA UPDATE FUNCTION ---
def check_for_updates():
    print("Checking for remote code updates...")
    OTA = senko.Senko(
        user=GITHUB_USER,
        repo=GITHUB_REPO,
        files=["main.py"]
    )
    try:
        if OTA.update():
            print("🚀 New update found and installed! Rebooting Pico...")
            blink_led(10, 0.05) 
            machine.reset()     
        else:
            print("✅ Code is up to date.")
    except Exception as e:
        print("OTA Update check failed:", e)

# --- 3. HELPER FUNCTIONS ---
def sync_time():
    global current_calendar_day
    try:
        ntptime.host = "pool.ntp.org"
        ntptime.settime()
        local_time_sec = time.time() + 28800
        (year, month, mday, hour, minute, second, weekday, yearday) = time.localtime(local_time_sec)
        machine.RTC().datetime((year, month, mday, weekday, hour, minute, second, 0))
        current_calendar_day = mday
        print(f"Time Synced! Local Time: {hour:02d}:{minute:02d}")
    except Exception as e:
        print("Time sync failed:", e)
        current_calendar_day = time.localtime()[2]

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def blink_led(times, delay=0.1):
    for _ in range(times):
        led.on()
        time.sleep(delay)
        led.off()
        time.sleep(delay)

def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print(f"Connecting to {WIFI_SSID}...")
        wlan.connect(WIFI_SSID, WIFI_PASS)
        for i in range(20):
            if wlan.isconnected(): break
            led.toggle()
            time.sleep(1)
    if wlan.isconnected():
        print("WiFi Connected!")
        blink_led(3, 0.05)
        sync_time()
    else:
        print("WiFi Failed.")

# --- 4. REPORTING LOGIC ---
def send_feed_report(message):
    client = MQTTClient("pico_report", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    try:
        client.connect()
        client.publish(f"{AIO_USER}/feeds/welcome-feed", message)
        client.disconnect()
    except Exception as e:
        print("Failed sending to welcome feed:", e)

def send_data():
    global hourly_energy_wh, daily_energy_wh, sample_count, current_calendar_day
    local_now = time.localtime()
    this_day = local_now[2]
    this_hour = local_now[3]
    
    if current_calendar_day is not None and this_day != current_calendar_day:
        day_summary = f"📆 DAILY TOTAL GENERATION = {round(daily_energy_wh, 2)} Wh."
        send_feed_report(day_summary)
        daily_energy_wh = 0.0
        current_calendar_day = this_day
        
        # Check for remote updates automatically at midnight transition
        check_for_updates()

    volts = round(random.uniform(11.0, 14.5), 2)
    amps  = round(random.uniform(0.0, 5.5), 2)
    watts = round(volts * amps, 2)
    pico_temp = get_internal_temp()
    
    calculated_step_wh = (watts / 60)
    hourly_energy_wh += calculated_step_wh
    daily_energy_wh += calculated_step_wh
    sample_count += 1
    
    client = MQTTClient("pico_turbine_box", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    try:
        client.connect()
        client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
        time.sleep_ms(200)
        client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
        time.sleep_ms(200)
        client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
        time.sleep_ms(200)
        client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
        client.disconnect()
        print(f"[{local_now[3]:02d}:{local_now[4]:02d}] 🚀 SUCCESS! Live update sent. Day Accum: {round(daily_energy_wh,2)}Wh")
    except Exception as e:
        print("Update failed:", e)

    if sample_count >= 60:
        hour_summary = f"🕐 Hourly Generation ({this_hour:02d}:00) = {round(hourly_energy_wh, 2)} Wh."
        send_feed_report(hour_summary)
        hourly_energy_wh = 0.0
        sample_count = 0

# --- 5. MAIN EXECUTION FLOW ---
# 🔌 Safety delay so Thonny can connect without crashing the backend!
print("Booting up in 2 seconds...")
time.sleep(2) 

connect_wifi()

if network.WLAN(network.STA_IF).isconnected():
    check_for_updates()  # Run the check immediately on power-up!

while True:
    if network.WLAN(network.STA_IF).isconnected():
        send_data()
    else:
        connect_wifi()
        
    time.sleep(INTERVAL)
