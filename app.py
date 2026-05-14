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

def send_status_msg(client, message):
    """Utility function to stream text logs to the pico-status feed"""
    try:
        client.publish(f"{AIO_USER}/feeds/pico-status", message)
        print(f"📋 Status Log Streamed: {message}")
    except Exception as e:
        print(f"Failed sending status log: {e}")

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
            
            # Stream a recovery text alert to your Stream box
            recovery_msg = f"🟢 Wi-Fi Recovered! Logged {outage_lines} mins of outage from {first_timestamp} to {last_timestamp}. Peak Accum: {round(stored_wh, 2)} Wh."
            send_status_msg(client, recovery_msg)
            
            # Clean up storage by deleting the backup file
            os.remove(BACKUP_FILE)
            print("✅ Storage vault cleared and synced.")
    except Exception as e:
        print("⚠️ Failed to process offline vault data:", e)

def start():
    global hourly_energy_wh, daily_energy_wh, current_calendar_day, last_logged_hour
    
    print("--- 🔋 Turbine Monitoring System Online ---")
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
            
            # Check and dump old backup logs if coming back online
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
            
            # Send a live "Heartbeat" to the stream block so you know the Pico is actively communicating
            send_status_msg(client, f"⚡ Pico Active at {this_hour:02d}:{this_minute:02d} | Live: {watts}W")
            time.sleep_ms(150)
            
            # 3. REAL-TIME CLOCK HOURLY TRIGGER (Pushes number to a GRAPH at 10:00, 11:00, 12:00 etc.)
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
