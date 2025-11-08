from flask_sqlalchemy import SQLAlchemy
db = SQLAlchemy()

class SensorData(db.Model):
    __tablename__ = 'sensor_data'
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String(20))
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    light = db.Column(db.Float)
