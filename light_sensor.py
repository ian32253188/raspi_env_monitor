from apds9930 import APDS9930
import time, logging

def init_light_sensor():
    sensor = APDS9930(1)
    sensor.enable_ambient_light_sensor(False)
    time.sleep(1)
    logging.info("APDS9930 已啟用")
    return sensor

def read_light_data(sensor):
    try:
        return round(sensor.ambient_light, 1)
    except Exception as e:
        logging.error(f"光感測讀取錯誤: {e}")
        return None
