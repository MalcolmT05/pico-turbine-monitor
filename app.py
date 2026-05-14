import time
import random
import machine
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration securely
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# --- CONFIGURATION & VARIABLE INITIALIZATION ---
INTERVAL = 60  # 🕐 Exactly 1 minute updates
hourly_energy_wh = 0.0
daily_energy_wh = 0.0
sample_count = 0

# Track changes in calendar dates natively using system ticks
current_calendar_day = time.localtime()[2] 

# Configure hardware tracking
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def send_feed_report(client, feed_name, message):
    """Helper to safely push text messages to text feeds"""
    try:
        client.publish(f"{AIO_USER}/feeds/{feed_name}", message)
        print(f"📋 Feed Report Posted [{feed_name}]: {message}")
    except Exception as e:
        print(f"Failed sending text report to {feed_name}: {e}")

def start():
    global hourly_energy_wh, daily_energy_wh, sample_count, current_calendar_day
    
    print("--- 🔋 Full Operational Turbine Monitor Initialized ---")
    client = MQTTClient("pico_turbine_runtime", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    
    while True:
        local_now = time.localtime()
        this_day = local_now[2]
        this_hour = local_now[3]
        this_minute = local_now[4]
        
        # 1. MIDNIGHT RESET DETECTION
        if this_day != current_calendar_day:
            try:
                client.connect()
                day_summary = f"📆 DAILY TOTAL GENERATION = {round(daily_energy_wh, 2)} Wh."
                send_feed_report(client, "welcome-feed", day_summary)
                client.publish(f"{AIO_USER}/feeds/pico-status", f"[{this_hour:02d}:{this_minute:02d}] Midnight Reset Complete.")
                client.disconnect()
            except:
                pass
            
            # Reset daily metrics
            daily_energy_wh = 0.0
            current_calendar_day = this_day

        # 2. DATA CALCULATION (Simulated for now, ready for PZEM sensors)
        volts = round(random.uniform(11.0, 14.5), 2)
        amps  = round(random.uniform(0.0, 5.5), 2)
        watts = round(volts * amps, 2)
        pico_temp = get_internal_temp()
        
        # Calculate generation accumulate (Watts divided by 60 minutes in an hour)
        calculated_step_wh = (watts / 60.0)
        hourly_energy_wh += calculated_step_wh
        daily_energy_wh += calculated_step_wh
        sample_count += 1
        
        print(f"📡 [{this_hour:02d}:{this_minute:02d}] Reading: {volts}V | {amps}A | {watts}W")
        
        # 3. TRANSMIT CURRENT METRICS TO ADAFRUIT
        try:
            client.connect()
            
            # Streaming telemetry variables
            client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
            time.sleep_ms(150)
            client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
            time.sleep_ms(150)
            
            # Push periodic status updates every 15 minutes
            if sample_count % 15 == 0:
                status_msg = f"[{this_hour:02d}:{this_minute:02d}] System Normal. Day Accum: {round(daily_energy_wh, 2)}Wh"
                client.publish(f"{AIO_USER}/feeds/pico-status", status_msg)
                time.sleep_ms(150)
                
            # 4. HOURLY REPORT TRIGGER (Executes every 60 intervals/minutes)
            if sample_count >= 60:
                hour_summary = f"🕐 Hourly Generation ({this_hour:02d}:00) = {round(hourly_energy_wh, 2)} Wh."
                send_feed_report(client, "welcome-feed", hour_summary)
                hourly_energy_wh = 0.0
                sample_count = 0
                
            client.disconnect()
            print(f"✅ Telemetry updated. Running Day Total: {round(daily_energy_wh, 2)} Wh")
            
        except Exception as e:
            print("⚠️ Data transmission drop out:", e)
            
        # 5. DELAY UNTIL NEXT MINUTE CYCLE
        time.sleep(INTERVAL)
