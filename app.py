import time
import random
import machine
from umqtt.simple import MQTTClient
from secrets import secrets

# Fetch configuration securely
AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

# Configure onboard temperature sensor
temp_sensor = machine.ADC(machine.ADC.CORE_TEMP)

def get_internal_temp():
    reading = temp_sensor.read_u16() * (3.3 / 65535)
    return round(27 - (reading - 0.706) / 0.001721, 2)

def start():
    """This is the entry point launched by main.py"""
    print("--- 🔋 Full Turbine Monitoring App Active ---")
    
    # Setup MQTT client
    client = MQTTClient("pico_turbine_runtime", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
    
    try:
        print("Connecting to Adafruit Broker...")
        client.connect()
        client.publish(f"{AIO_USER}/feeds/pico-status", "Monitoring System Online")
        client.disconnect()
        print("Initialization heartbeat sent successfully!")
    except Exception as e:
        print("🛑 Initial Adafruit Connection Failed:", e)

    while True:
        # 1. Simulate data stream (We will wire real PZEM sensors here next!)
        volts = round(random.uniform(11.0, 14.5), 2)
        amps  = round(random.uniform(0.0, 5.5), 2)
        watts = round(volts * amps, 2)
        pico_temp = get_internal_temp()
        
        print(f"📡 Sending: {volts}V | {amps}A | {watts}W")
        
        # 2. Connect and publish all streams to Adafruit
        try:
            client.connect()
            
            # Send to your exact feed keys
            client.publish(f"{AIO_USER}/feeds/turbine-voltage", str(volts))
            time.sleep_ms(200) # Small gaps stop Adafruit from throttling your account
            client.publish(f"{AIO_USER}/feeds/turbine-current", str(amps))
            time.sleep_ms(200)
            client.publish(f"{AIO_USER}/feeds/turbine-power", str(watts))
            time.sleep_ms(200)
            client.publish(f"{AIO_USER}/feeds/pico-temp", str(pico_temp))
            
            client.disconnect()
            print("✅ All metrics successfully updated on Adafruit!")
            
        except Exception as e:
            print("⚠️ Data push failed (Check your Adafruit feed keys or credentials):", e)
            
        # Wait 10 seconds before the next reading cycle
        time.sleep(10)
