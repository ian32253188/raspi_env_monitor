import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')
SQLALCHEMY_DATABASE_URI = f"sqlite:///{DB_PATH}"
SQLALCHEMY_TRACK_MODIFICATIONS = False

DHT_PIN = 4
LED_PIN = 18
BUZZER_PIN = 19
DEFAULT_THRESHOLDS = {"temperature": 35.0, "humidity": 80.0, "light": 30.0}
