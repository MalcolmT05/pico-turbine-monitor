import time
import random
import machine
import os
import urequests
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

# Configure hardware tracking
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def send_status_msg(client, message):
    """Utility function to stream text logs to the pico-status feed"""
    try:
        client.publish(f"{AIO_USER}/feeds/pico-status", message)
        print(f"📋 Status Log Streamed: {message}")
    except Exception as e:
        print(f"Failed sending status log: {e}")

def sync_pico_clock():
    """Fetches text time directly from Adafruit's local time string API"""
    print("⏰ Fetching local text time from Adafruit API...")
    # This specific endpoint outputs text in your account's designated timezone format: YYYY-MM-DD HH:MM:SS
    url = f"https://io.adafruit.com/api/v2/{AIO_USER}/integrations/time/task"
    try:
        res = urequests.get(url)
        if res.status_code == 200:
            time_str = res.text.strip() # Example: "2026-05-14 13:12:05"
            print(f"📥 Received Raw Time String: {time_str}")
            
            # Split the date and time segments out safely
            date_part, time_part = time_str.split(" ")
            year, month, day = map(int, date_part.split("-"))
            hour, minute, second = map(int, time_part.split(":"))
            
            # Apply to hardware RTC using standard MicroPython 8-item tuple
            # Format: (year, month, day, weekday, hour, minute, second, subseconds)
            machine.RTC().datetime((year, month, day, 0, hour, minute, second, 0))
            print("✅ Clock hardware synchronized successfully!")
        else:
            print(f"❌ Adafruit Time API returned status: {res.status_code}")
        res.close()
    except Exception as e:
        print("⚠️ Clock sync parsing failed. Falling back to onboard timer:", e)

def process_offline_vault(client):
    """Checks if backup data exists from an outage and uploads recovery status"""
    try:
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
                        stored_wh = float(parts[3])
            
            recovery_msg = f"🟢 Wi-Fi Recovered! Logged {outage_lines} mins of outage from {first_timestamp} to {last_timestamp}. Peak Accum: {round(stored_wh, 2)} Wh."
            send_status_msg(client, recovery_msg)
            os.remove(BACKUP_FILE)
            print("✅ Storage vault cleared and synced.")
    except Exception as e:
        print("⚠️ Failed to process offline vault data:", e)

def start():
    global hourly_energy_wh, daily_energy_wh
    
    print("--- 🔋 Turbine Monitoring System Online ---")
    
    # Force real-time clock sync immediately on start using Adafruit
    sync_pico_clock()
    
    # Establish baseline tracking markers *after* time sync has aligned the hours
    local_now = time.localtime()
    current_calendar_day = local_now[2] 
    last_logged_hour = local_now[3]
    
    client = MQTTClient("pico_turbine_runtime", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    
    while True:
        local_now = time.localtime()
        this_day    = local_now[2]
        this_hour   = local_now[3]
        this_minute = local_now[4]
        
        # 1. MATHEMATICAL CALCULATIONS (Simulated turbine input)
        volts = round(random.uniform(11.0, 14.5), 2)
        amps  = round(random.uniform(0.0, 5.5), 2)
        watts = round(volts * amps, 2)
        pico_temp = get_internal_temp()
        
        # Power accumulation calculation
        calculated_step_wh = (watts / 60.0)
        hourly_energy_wh += calculated_step_wh
        daily_energy_wh += calculated_step_wh
        
        print(f"📡 [{this_hour:02d}:{this_minute:02d}] Live: {volts}V | {amps}A | Running Daily Total: {round(daily_energy_wh, 2)}Wh")
        
        # 2. ATTEMPT DATA TRANSMISSION
        try:
            client.connect()
            process_offline_vault(client)
            
            # Stream live metrics to gauges and graphs
            client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
            time.sleep_ms(150)
            
            # Heartbeat to the stream block
            send_status_msg(client, f"⚡ Pico Active at {this_hour:02d}:{this_minute:02d} | Live: {watts}W")
            time.sleep_ms(150)
            
            # 3. REAL-TIME CLOCK HOURLY TRIGGER
            if this_hour != last_logged_hour:
                final_hour_wh = round(hourly_energy_wh, 2)
                
                # Push raw number data to your hourly graph feed
                client.publish(f"{AIO_USER}/feeds/turbine-hourly-power", str(final_hour_wh))
                time.sleep_ms(150)
                
                # Push a matching text log notification to your stream block
                send_status_msg(client, f"🕐 Hourly Report: Accumulated {final_hour_wh} Wh over the past hour.")
                
                # Reset hourly tracker and lock in current hour
                hourly_energy_wh = 0.0
                last_logged_hour = this_hour
            
            # 4. MIDNIGHT RESET TRIGGER
            if this_day != current_calendar_day:
                send_status_msg(client, f"📆 Daily Total Reset. Grand Total for yesterday: {round(daily_energy_wh, 2)} Wh.")
                daily_energy_wh = 0.0
                current_calendar_day = this_day
                
            client.disconnect()
            print("✅ Telemetry successfully pushed.")
            
        except Exception as e:
            print(f"⚠️ Wi-Fi Error: {e}. Saving telemetry to vault storage...")
            try:
                with open(BACKUP_FILE, "a") as vault:
                    vault.write(f"{this_hour:02d}:{this_minute:02d},{volts},{amps},{round(daily_energy_wh, 2)}\n")
                print(f"💾 Saved record locally at {this_hour:02d}:{this_minute:02d}")
            except Exception as file_err:
                print("🛑 Critical storage failure:", file_err)
            
        time.sleep(INTERVAL)
