import RPi.GPIO as GPIO, time, logging
from config import BUZZER_PIN, LED_PIN

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.setup(LED_PIN, GPIO.OUT)
buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)
buzzer_pwm.stop()

def stop_buzzer_immediate():
    buzzer_pwm.stop()
    GPIO.output(BUZZER_PIN, GPIO.HIGH)
    logging.info("蜂鳴器已靜音")
