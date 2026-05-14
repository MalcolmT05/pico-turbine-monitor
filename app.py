import time
import random
import machine
import os
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# Global trackers (keep their values between loops)
hourly_energy_wh = 0.0
last_logged_hour = -1 

def get_internal_temp():
    temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def start():
    global hourly_energy_wh, last_logged_hour
    
    # Get current time
    t = time.localtime()
    this_hour, this_min = t[3], t[4]
    
    # Set baseline hour on first run
    if last_logged_hour == -1:
        last_logged_hour = this_hour
        print(f"✅ Baseline set to hour: {this_hour}")

    # 1. CALCULATE POWER
    volts = round(random.uniform(11.0, 14.5), 2)
    amps  = round(random.uniform(0.0, 5.5), 2)
    watts = round(volts * amps, 2)
    
    # Accumulate Watt-hours (Watts / 60 minutes)
    hourly_energy_wh += (watts / 60.0)
    
    print(f"📡 [{this_hour:02d}:{this_min:02d}] {watts}W | Bucket: {round(hourly_energy_wh, 2)}Wh")

    # 2. SEND TO ADAFRUIT
    client = MQTTClient("pico_turbine", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    try:
        client.connect()
        
        # Standard live feeds
        client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
        client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
        client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
        client.publish(f"{AIO_USER}/feeds/pico-temp", str(get_internal_temp()))

        # 3. HOURLY CLOCK TRIGGER (Top of the hour)
        if this_hour != last_logged_hour:
            # Convert Wh to kWh
            total_kwh = round(hourly_energy_wh / 1000.0, 4)
            
            # Send number to new feed
            client.publish(f"{AIO_USER}/feeds/total-generation", str(total_kwh))
            
            # Status update
            status_msg = f"🕐 Hourly Report: {total_kwh} kWh generated."
            client.publish(f"{AIO_USER}/feeds/pico-status", status_msg)
            print(f"📋 {status_msg}")
            
            # Reset
            hourly_energy_wh = 0.0
            last_logged_hour = this_hour
            
        client.disconnect()
        print("✅ Sync Success")
        
    except Exception as e:
        print(f"⚠️ Connection failed: {e}")
