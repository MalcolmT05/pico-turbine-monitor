import time
import random
from umqtt.simple import MQTTClient
from secrets import secrets

AIO_USER = secrets['aio_user']
AIO_KEY  = secrets['aio_key']

def send_status_update(status_text):
    try:
        client = MQTTClient("pico_status_hb", "io.adafruit.com", user=AIO_USER, password=AIO_KEY, ssl=False)
        client.connect()
        client.publish(f"{AIO_USER}/feeds/pico-status", status_text)
        client.disconnect()
        print(f"Status pushed: {status_text}")
    except Exception as e:
        print("Adafruit upload failed:", e)

def start():
    """This is the entry point called by main.py"""
    print("--- Turbine Application Started ---")
    send_status_update("System Online via GitHub Bootloader")
    
    while True:
        # Your simulation data logic lives here
        volts = round(random.uniform(11.0, 14.5), 2)
        print(f"Reading Sensor: {volts}V")
        
        # Adjust testing interval here seamlessly via GitHub edits!
        time.sleep(10)
