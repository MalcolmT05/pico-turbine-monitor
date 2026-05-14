import time
import random
import machine
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration securely
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# --- CONFIGURATION & VARIABLE INITIALIZATION ---
INTERVAL = 60  # 🕐 Check and update every 60 seconds
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

def start():
    global hourly_energy_wh, daily_energy_wh, current_calendar_day, last_logged_hour
    
    print("--- 🔋 Real-Time Turbine Monitor Active ---")
    client = MQTTClient("pico_turbine_runtime", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    
    while True:
        # Get exact current real time from the Pico's synchronized clock
        local_now = time.localtime()
        this_day    = local_now[2]
        this_hour   = local_now[3]
        this_minute = local_now[4]
        
        # 1. MATHEMATICAL CALCULATIONS
        volts = round(random.uniform(11.0, 14.5), 2)
        amps  = round(random.uniform(0.0, 5.5), 2)
        watts = round(volts * amps, 2)
        pico_temp = get_internal_temp()
        
        # Power accumulation (Watts divided by 60 minutes)
        calculated_step_wh = (watts / 60.0)
        hourly_energy_wh += calculated_step_wh
        daily_energy_wh += calculated_step_wh
        
        print(f"📡 [{this_hour:02d}:{this_minute:02d}] Live: {volts}V | {amps}A | Total Accum: {round(daily_energy_wh, 2)}Wh")
        
        # 2. TRANSMIT MINUTELY TELEMETRY
        try:
            client.connect()
            client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
            time.sleep_ms(150)
            
            # 3. REAL-TIME CLOCK HOURLY TRIGGER (e.g., Exactly at 10:00, 11:00, 12:00)
            if this_hour != last_logged_hour:
                # Format a user-friendly timestamp label (e.g., "10:00 AM")
                am_pm = "a.m." if this_hour < 12 else "p.m."
                display_hour = this_hour if (0 < this_hour <= 12) else (this_hour % 12)
                if display_hour == 0: display_hour = 12
                
                hour_label = f"{display_hour} {am_pm}"
                
                hour_summary = f"🕐 Total Power at {hour_label} = {round(hourly_energy_wh, 2)} Wh"
                send_feed_report(client, "welcome-feed", hour_summary)
                
                # Reset the hourly metric container and lock in the current hour
                hourly_energy_wh = 0.0
                last_logged_hour = this_hour
            
            # 4. MIDNIGHT RESET TRIGGER
            if this_day != current_calendar_day:
                day_summary = f"📆 DAILY GRAND TOTAL = {round(daily_energy_wh, 2)} Wh"
                send_feed_report(client, "welcome-feed", day_summary)
                
                daily_energy_wh = 0.0
                current_calendar_day = this_day
                
            client.disconnect()
            
        except Exception as e:
            print("⚠️ Connection drop out inside loop:", e)
            
        # Delay exactly 1 minute
        time.sleep(INTERVAL)
