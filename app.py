import time
import random
import machine
import os
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration securely
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# --- CONFIGURATION & VARIABLE INITIALIZATION ---
INTERVAL = 60  # 🕐 Check and update every 60 seconds
BACKUP_FILE = "backup_log.txt"
hourly_energy_wh = 0.0
daily_energy_wh = 0.0

# Track the calendar date AND the current hour to look for changes
local_now = time.localtime()
current_calendar_day = local_now[2] 
last_logged_hour = local_now[3]

# Configure hardware tracking
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def send_feed_report(client, feed_name, message):
    try:
        client.publish(f"{AIO_USER}/feeds/{feed_name}", message)
        print(f"📋 Feed Report Posted [{feed_name}]: {message}")
    except Exception as e:
        print(f"Failed sending text report to {feed_name}: {e}")

def process_offline_vault(client):
    """Checks if backup data exists from a Wi-Fi outage and uploads a summary"""
    try:
        # Check if the backup file exists in storage
        files = os.listdir()
        if BACKUP_FILE in files:
            print("📦 Offline backup data found! Processing vault...")
            
            outage_lines = 0
            stored_wh = 0.0
            first_timestamp = ""
            last_timestamp = ""
            
            with open(BACKUP_FILE, "r") as f:
                for line in f:
                    parts = line.strip().split(",")
                    if len(parts) == 4:
                        outage_lines += 1
                        if outage_lines == 1:
                            first_timestamp = parts[0]
                        last_timestamp = parts[0]
                        # Accumulate the saved daily progress
                        stored_wh = float(parts[3])
            
            # Send a recovery summary report to your text feed
            recovery_msg = f"📡 Wi-Fi Recovered! Logged {outage_lines} mins of outage data from {first_timestamp} to {last_timestamp}. Peak Accum: {round(stored_wh, 2)} Wh."
            send_feed_report(client, "welcome-feed", recovery_msg)
            
            # Clean up storage by deleting the backup file
            os.remove(BACKUP_FILE)
            print("✅ Storage vault cleared and synced with Adafruit.")
    except Exception as e:
        print("⚠️ Failed to process offline vault data:", e)

def start():
    global hourly_energy_wh, daily_energy_wh, current_calendar_day, last_logged_hour
    
    print("--- 🔋 Real-Time Turbine Monitor & Vault Storage Active ---")
    client = MQTTClient("pico_turbine_runtime", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    
    while True:
        # Get exact current real time from the Pico's clock
        local_now = time.localtime()
        this_day    = local_now[2]
        this_hour   = local_now[3]
        this_minute = local_now[4]
        
        # 1. MATHEMATICAL CALCULATIONS (Simulated readings, ready for physical sensors)
        volts = round(random.uniform(11.0, 14.5), 2)
        amps  = round(random.uniform(0.0, 5.5), 2)
        watts = round(volts * amps, 2)
        pico_temp = get_internal_temp()
        
        # Power accumulation calculation
        calculated_step_wh = (watts / 60.0)
        hourly_energy_wh += calculated_step_wh
        daily_energy_wh += calculated_step_wh
        
        print(f"📡 [{this_hour:02d}:{this_minute:02d}] Live: {volts}V | {amps}A | Total Accum: {round(daily_energy_wh, 2)}Wh")
        
        # 2. ATTEMPT DATA TRANSMISSION
        try:
            client.connect()
            
            # If we connected successfully, check if we need to dump an old backup file first
            process_offline_vault(client)
            
            # Streaming live numeric variables
            client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
            time.sleep_ms(150)
            
            # 3. REAL-TIME CLOCK HOURLY TRIGGER (Updates exactly at 10:00, 11:00, 12:00, etc.)
            if this_hour != last_logged_hour:
                # Format a user-friendly timestamp label (e.g., "12 p.m.")
                am_pm = "a.m." if this_hour < 12 else "p.m."
                display_hour = this_hour if (0 < this_hour <= 12) else (this_hour % 12)
                if display_hour == 0: display_hour = 12
                
                hour_label = f"{display_hour} {am_pm}"
                hour_summary = f"🕐 Total Power at {hour_label} = {round(hourly_energy_wh, 2)} Wh"
                send_feed_report(client, "welcome-feed", hour_summary)
                
                # Reset hourly tracker and lock in current hour
                hourly_energy_wh = 0.0
                last_logged_hour = this_hour
            
            # 4. MIDNIGHT RESET TRIGGER
            if this_day != current_calendar_day:
                day_summary = f"📆 DAILY GRAND TOTAL = {round(daily_energy_wh, 2)} Wh"
                send_feed_report(client, "welcome-feed", day_summary)
                
                daily_energy_wh = 0.0
                current_calendar_day = this_day
                
            client.disconnect()
            print("✅ Telemetry successfully pushed to Adafruit.")
            
        except Exception as e:
            # FALLBACK LOGIC IF WIFI IS DOWN OR DISCONNECTED
            print(f"⚠️ Wi-Fi Error: {e}. Saving telemetry to internal vault storage...")
            try:
                with open(BACKUP_FILE, "a") as vault:
                    # Write timestamp, volts, amps, and running daily energy to local memory
                    vault.write(f"{this_hour:02d}:{this_minute:02d},{volts},{amps},{round(daily_energy_wh, 2)}\n")
                print(f"💾 Saved record locally at {this_hour:02d}:{this_minute:02d}")
            except Exception as file_err:
                print("🛑 Critical hardware storage failure:", file_err)
            
        # Delay exactly 1 minute before checking everything again
        time.sleep(INTERVAL)
