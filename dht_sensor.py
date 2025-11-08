import dht11, logging
from config import DHT_PIN

instance = dht11.DHT11(pin=DHT_PIN)

def read_dht_data():
    result = instance.read()
    if result.is_valid():
        return result.temperature, result.humidity
    else:
        logging.warning("DHT11 讀取失敗")
        return None, None
