import time
import random
import machine
import os
import urequests
import gc
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration securely
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# --- CONFIGURATION ---
INTERVAL = 60  
BACKUP_FILE = "backup_log.txt"
hourly_energy_wh = 0.0  # We track in Wh internally for precision

# Configure hardware tracking
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def send_status_msg(client, message):
    try:
        client.publish(f"{AIO_USER}/feeds/pico-status", message)
        print(f"📋 Status: {message}")
    except:
        pass

def start():
    global hourly_energy_wh
    
    # Get current time
    local_now = time.localtime()
    this_hour = local_now[3]
    this_minute = local_now[4]
    
    # Set the baseline hour on the very first run
    if not hasattr(start, "last_logged_hour"):
        start.last_logged_hour = this_hour

    # 1. CALCULATIONS
    volts = round(random.uniform(11.0, 14.5), 2)
    amps  = round(random.uniform(0.0, 5.5), 2)
    watts = round(volts * amps, 2)
    
    # Add to the hourly bucket (Watts / 60 minutes = Watt-hours)
    hourly_energy_wh += (watts / 60.0)
    
    print(f"📡 [{this_hour:02d}:{this_minute:02d}] Live: {watts}W | Hourly Bucket: {round(hourly_energy_wh, 2)}Wh")
    
    # 2. TRANSMISSION
    client = MQTTClient("pico_turbine", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    try:
        client.connect()
        
        # Publish Live metrics
        client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
        client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
        client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
        client.publish(f"{AIO_USER}/feeds/pico-temp", str(get_internal_temp()))
        
        # 3. THE HOURLY KWH TRIGGER
        # This triggers exactly when the clock rolls over (e.g., 15:59 -> 16:00)
        if this_hour != start.last_logged_hour:
            # Convert Wh to kWh
            total_kwh = round(hourly_energy_wh / 1000.0, 4)
            
            # Publish to the NEW feed (Number only!)
            client.publish(f"{AIO_USER}/feeds/total-generation", str(total_kwh))
            
            send_status_msg(client, f"🕐 Hourly Reset: Generated {total_kwh} kWh in the last hour.")
            
            # Reset bucket for the new hour
            hourly_energy_wh = 0.0
            start.last_logged_hour = this_hour
            
        client.disconnect()
        print("✅ Sync Complete.")
        
    except Exception as e:
        print(f"⚠️ Offline: {e}")
        # Emergency backup to file
        with open(BACKUP_FILE, "a") as f:
            f.write(f"{this_hour:02d}:{this_minute:02d},{volts},{amps},{round(hourly_energy_wh, 2)}\n")
        gc.collect()
