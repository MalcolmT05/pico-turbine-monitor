import time
import random
import machine
import os
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# Global trackers to keep data between loops
hourly_energy_wh = 0.0
last_logged_hour = -1 

def get_internal_temp():
    """Reads the Pico's internal temperature sensor"""
    temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def start():
    global hourly_energy_wh, last_logged_hour
    
    # Get current time
    t = time.localtime()
    this_hour, this_min = t[3], t[4]
    
    # Baseline hour setup on first boot
    if last_logged_hour == -1:
        last_logged_hour = this_hour
        print(f"✅ Baseline set to hour: {this_hour}")

    # 1. CALCULATE POWER (Simulated for this example)
    volts = round(random.uniform(11.0, 14.5), 2)
    amps  = round(random.uniform(0.0, 5.5), 2)
    watts = round(volts * amps, 2)
    
    # Add to the hourly bucket (Wh = Watts / 60 minutes)
    hourly_energy_wh += (watts / 60.0)
    
    print(f"📡 [{this_hour:02d}:{this_min:02d}] {watts}W | Bucket: {round(hourly_energy_wh, 2)}Wh")

    # 2. SEND TO ADAFRUIT
    client = MQTTClient("pico_turbine", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    try:
        client.connect()
        
        # Publish Live metrics with 200ms delays to prevent throttling
        client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
        time.sleep_ms(200)
        
        client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
        time.sleep_ms(200)
        
        client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
        time.sleep_ms(200)
        
        client.publish(f"{AIO_USER}/feeds/pico-temp", str(get_internal_temp()))
        time.sleep_ms(200)

        # 3. HOURLY KWH TRIGGER (Runs at the top of every hour)
        if this_hour != last_logged_hour:
            # Convert accumulated Watt-hours to kWh
            total_kwh = round(hourly_energy_wh / 1000.0, 4)
            
            # Send pure number to your new 'total-generation' feed
            client.publish(f"{AIO_USER}/feeds/total-generation", str(total_kwh))
            time.sleep_ms(200)
            
            # Send text status update
            status_msg = f"🕐 Hourly Report: {total_kwh} kWh generated."
            client.publish(f"{AIO_USER}/feeds/pico-status", status_msg)
            print(f"📋 {status_msg}")
            
            # Reset bucket for the next hour
            hourly_energy_wh = 0.0
            last_logged_hour = this_hour
            
        client.disconnect()
        print("✅ Sync Success")
        
    except Exception as e:
        print(f"⚠️ Connection failed: {e}")
        # Memory cleanup
        try: client.disconnect()
        except: pass
