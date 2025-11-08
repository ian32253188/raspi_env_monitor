app.py
import threading
import time
import sqlite3
import logging
from datetime import datetime
from flask import Flask, render_template, jsonify
from flask_sqlalchemy import SQLAlchemy
import RPi.GPIO as GPIO
import dht11
import random
import os
from apds9930 import APDS9930
from flask import request
from openai import OpenAI

# Set up logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 初始化 GPIO 模式
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)

app = Flask(__name__)
# ✅ 先定義 BASE_DIR，再設定資料庫路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'data.db')

app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{DB_PATH}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# GPIO setup
DHT_PIN = 4  # DHT11 Data pin
LED_PIN = 18  # LED

# 蜂鳴器設定
BUZZER_PIN = 19
GPIO.setup(BUZZER_PIN, GPIO.OUT)
GPIO.output(BUZZER_PIN, 1)  # 初始靜音（低電平觸發）

# 在開頭區域初始化時加入 PWM
buzzer_pwm = GPIO.PWM(BUZZER_PIN, 1000)  # 建立 PWM，初始頻率 1000 Hz
buzzer_pwm.stop()  # 先關閉蜂鳴器


# 預設警報閾值
alert_thresholds = {
    "temperature": 35.0,
    "humidity": 80.0,
    "light": 30.0
}

# Sensor initialization
try:
    light_detect = APDS9930(1)
    light_detect.enable_ambient_light_sensor(False)
    logger.info("APDS9930 Light sensor initialized successfully")
    time.sleep(1)
except Exception as e:
    logger.error(f"Failed to initialize Light sensor: {e}")
    exit(1)
    
try:
    instance = dht11.DHT11(pin=DHT_PIN)
    logger.info("DHT11 sensor initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize DHT11 sensor: {e}")
    exit(1)

# Database model (must match existing sensor_data table)
class SensorData(db.Model):
    __tablename__ = 'sensor_data'  # Explicitly set table name
    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.String(20))
    temperature = db.Column(db.Float)
    humidity = db.Column(db.Float)
    light = db.Column(db.Float)

# Verify existing table schema
def check_table_schema():
    try:
        with app.app_context():
            conn = sqlite3.connect('data.db')
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(sensor_data)")
            columns = cursor.fetchall()
            expected_columns = [
                ('id', 'INTEGER'),
                ('timestamp', 'TEXT'),
                ('temperature', 'REAL'),
                ('humidity', 'REAL'),
                ('light', 'REAL')
            ]
            actual_columns = [(col[1], col[2]) for col in columns]  # Name and type
            if set(expected_columns).issubset(set(actual_columns)):
                logger.info("Existing sensor_data table schema is compatible")
            else:
                logger.error(f"Schema mismatch. Expected {expected_columns}, found {actual_columns}")
                exit(1)
            cursor.execute("SELECT COUNT(*) FROM sensor_data")
            count = cursor.fetchone()[0]
            logger.info(f"Table sensor_data contains {count} records")
            conn.close()
    except Exception as e:
        logger.error(f"Failed to verify sensor_data table: {e}")
        exit(1)

@app.route('/set_thresholds', methods=['POST'])
def set_thresholds():
    global alert_thresholds
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data received"}), 400

        alert_thresholds["temperature"] = float(data.get("temperature", alert_thresholds["temperature"]))
        alert_thresholds["humidity"] = float(data.get("humidity", alert_thresholds["humidity"]))
        alert_thresholds["light"] = float(data.get("light", alert_thresholds["light"]))

        # ✅ 更新閾值時立即靜音
        stop_buzzer_immediate()

        logger.info(f"✅ Updated thresholds: {alert_thresholds}")
        return jsonify({"success": True, "thresholds": alert_thresholds})
    except Exception as e:
        logger.error(f"Failed to set thresholds: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/create_report', methods=['POST'])
def create_report():
    try:
        data = SensorData.query.order_by(SensorData.id.desc()).limit(50).all()
        labels = [d.timestamp for d in data]
        temps = [d.temperature for d in data]
        hums = [d.humidity for d in data]
        lights = [d.light for d in data]

        # 反轉順序（由舊到新）
        labels = labels[::-1]
        temps = temps[::-1]
        hums = hums[::-1]
        lights = lights[::-1]

        # 組成要給模型看的 context
        sensor_context = {
            "timestamps": [str(t) for t in labels],
            "temperature": temps,
            "humidity": hums,
            "light": lights
        }


        client = OpenAI(
            api_key="金鑰",
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        response = client.chat.completions.create(
            model="gemini-2.0-flash",
            messages=[
                {
                    "role": "system",
                    "content": "你是一位專業的環境感測數據分析專家，請使用繁體中文回答。"
                },
                {
                    "role": "user",
                    "content": f"以下是最新的感測資料：{sensor_context}。請用繁體中文分析溫度、濕度、光度的趨勢與異常。"
                }
            ]
        )
        message = response.choices[0].message.content
        print("報告內容%s" % response.choices[0].message.content)
        
        return jsonify({"success": True, "message": message})
    except Exception as e:
        logger.error(f"Failed to create report: {e}")
        return jsonify({"error": str(e)}), 500
        
# Alarm function
def trigger_alarm():
    try:
        logger.info("Triggering alarm")
        GPIO.output(BUZZER_PIN, GPIO.HIGH)
        time.sleep(3)
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        for _ in range(3):
            GPIO.output(LED_PIN, GPIO.HIGH)
            time.sleep(0.5)
            GPIO.output(LED_PIN, GPIO.LOW)
            time.sleep(0.5)
    except Exception as e:
        logger.error(f"Alarm execution failed: {e}")

# Data collection function with thread lock
data_lock = threading.Lock()
# 全域變數儲存蜂鳴器狀態
buzzer_active = False
buzzer_timer = None
alert_triggered_tem = 26
alert_triggered_hum = 60
alert_triggered_lig = 160

def stop_buzzer_immediate():
    """立即停止蜂鳴器並重置狀態（確保完全靜音）"""
    global buzzer_active, buzzer_timer
    try:
        if buzzer_timer and buzzer_timer.is_alive():
            buzzer_timer.cancel()
        buzzer_pwm.ChangeDutyCycle(0)   # 停止輸出聲音
        buzzer_pwm.stop()               # 停止 PWM
        GPIO.output(BUZZER_PIN, GPIO.HIGH)  # 轉為高電平（靜音）
        buzzer_active = False
        logger.info("🔇 蜂鳴器已停止")
    except Exception as e:
        logger.error(f"Stop buzzer failed: {e}")
        
def collect_data():
    global buzzer_active
    global alert_triggered_tem
    global alert_triggered_hum
    global alert_triggered_lig
    while True:
        result = instance.read()
        try:
            if result.is_valid():  # 模擬測試
                temperature = result.temperature
                humidity = result.humidity
                print("目前溫度: %d 度C" % result.temperature)
                print("目前濕度: %d %%" % result.humidity)
                light = round(light_detect.ambient_light, 1)
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                logging.info(f"Collected data: Temperature={temperature}°C, Humidity={humidity}%, Light={light}%")

                # 判斷是否超出警報閾值
                alert_triggered_tem = temperature > alert_thresholds["temperature"]
                alert_triggered_hum = humidity > alert_thresholds["humidity"]
                alert_triggered_lig = light < alert_thresholds["light"]

                if alert_triggered_tem or alert_triggered_hum or alert_triggered_lig:
                    if not buzzer_active:
                        buzzer_active = True
                        logger.warning(f"⚠️ 警報觸發! 當前值: T={temperature}, H={humidity}, L={light}")
                        GPIO.output(BUZZER_PIN, GPIO.LOW)  # 低電平啟動蜂鳴器
                        buzzer_pwm.start(50)
                else:
                    if buzzer_active:
                        stop_buzzer_immediate()

                # 寫入資料庫
                with app.app_context():
                    with data_lock:
                        new_data = SensorData(
                            timestamp=timestamp,
                            temperature=temperature,
                            humidity=humidity,
                            light=light
                        )
                        db.session.add(new_data)
                        db.session.commit()

                time.sleep(2)
        except Exception as e:
            logger.error(f"Error reading sensor or saving to database: {e}")


# Start background thread
# Web routes
@app.route('/')
def index():
    try:
        data = SensorData.query.order_by(SensorData.id.desc()).all()
        logger.info(f"Loaded {len(data)} records for web display")
        return render_template('index.html', data=data)
    except Exception as e:
        logger.error(f"Failed to load web data: {e}")
        return "Error: Unable to load data, check logs", 500

# API for real-time data
@app.route('/data')
def get_data():
    global buzzer_active
    global alert_triggered_tem
    global alert_triggered_hum
    global alert_triggered_lig
    try:
        data = SensorData.query.order_by(SensorData.id.desc()).limit(50).all()
        labels = [d.timestamp for d in data]
        temps = [d.temperature for d in data]
        hums = [d.humidity for d in data]
        lights = [d.light for d in data]

        # 使用實際蜂鳴器狀態，而非重算閾值
        buzzer_status = "ON" if buzzer_active else "OFF"

        return jsonify(
            labels=labels[::-1],
            temps=temps[::-1],
            hums=hums[::-1],
            lights=lights[::-1],
            buzzer=buzzer_status,
            tem=alert_triggered_tem,
            hum=alert_triggered_hum,
            lig=alert_triggered_lig
        )
    except Exception as e:
        logger.error(f"API data retrieval failed: {e}")
        return jsonify(error=str(e)), 500

# Check database contents
def check_db():
    try:
        conn = sqlite3.connect('data.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM sensor_data ORDER BY id DESC LIMIT 10")
        rows = cursor.fetchall()
        logger.info("Last 10 database records:")
        for row in rows:
            logger.info(row)
        conn.close()
    except Exception as e:
        logger.error(f"Failed to check database contents: {e}")


def init_db():
    with app.app_context():
        db.create_all()
        logger.info("Database and sensor_data table created successfully")


if __name__ == '__main__':
    logger.info("Starting Flask server")
    init_db()
    check_table_schema()  # Verify existing table
    threading.Thread(target=collect_data, daemon=True).start()
    check_db()  # Check database at startup
    app.run(host='192.168.0.115', port=5000, debug=True)
    #app.run(host='192.168.0.229', port=5000, debug=True)


index.html
<!DOCTYPE html>
<html>
<head>
    <title>即時環境監測平台</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1, h2 { color: #2C3E50; }
        canvas { max-width: 100%; height: auto !important; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
        /* 背景遮罩 */
        .modal-overlay {
          display: none;
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          background-color: rgba(0,0,0,0.5);
          justify-content: center;
          align-items: center;
          z-index: 1000;
        }

        /* 彈出視窗 */
        .modal {
          background-color: #fff;
          border-radius: 10px;
          padding: 20px;
          width: 600px;               /* ✅ 寬度變寬 */
          max-height: 80vh;           /* ✅ 限制最高不超過視窗高度 */
          box-shadow: 0 0 15px rgba(0,0,0,0.3);
          text-align: center;
          font-family: "Noto Sans TC", sans-serif;
          display: flex;
          flex-direction: column;
        }

        .modal h2 {
          margin-top: 0;
          color: #333;
        }

        /* 可滾動內容區域 */
        .modal-content-scroll {
          overflow-y: auto;           /* ✅ 加上滾動條 */
          text-align: left;
          color: #555;
          margin-top: 10px;
          padding-right: 10px;
          flex-grow: 1;               /* ✅ 撐開可滾動區域 */
          white-space: pre-wrap;
        }

        .close-btn {
          margin-top: 15px;
          padding: 10px 25px;
          background-color: #007bff;
          border: none;
          color: white;
          border-radius: 5px;
          cursor: pointer;
          align-self: center;         /* ✅ 置中 */
        }

        .close-btn:hover {
          background-color: #0056b3;
        }

        /* 按鈕 */
        #fetchBtn {
          margin: 40px;
          padding: 10px 20px;
          font-size: 16px;
          border-radius: 8px;
          border: none;
          background-color: #007bff;
          color: white;
          cursor: pointer;
        }
        #fetchBtn:hover {
          background-color: #0056b3;
        }
    </style>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css">
</head>
<body>
    <h1>即時環境監測</h1>
    <div id="buzzer-alert-lig" style="
        display:none;
        background-color: red;
        color: white;
        font-size: 24px;
        text-align: center;
        padding: 10px;
        border-radius: 8px;
        animation: blink 0.2s infinite;
    ">
        ⚠️ 光線過低！蜂鳴器已觸發！
    </div>
    <div id="buzzer-alert-hum" style="
        display:none;
        background-color: red;
        color: white;
        font-size: 24px;
        text-align: center;
        padding: 10px;
        border-radius: 8px;
        animation: blink 0.2s infinite;
    ">
        ⚠️ 濕度過高！蜂鳴器已觸發！
    </div>
    <div id="buzzer-alert-tem" style="
        display:none;
        background-color: red;
        color: white;
        font-size: 24px;
        text-align: center;
        padding: 10px;
        border-radius: 8px;
        animation: blink 0.2s infinite;
    ">
        ⚠️ 氣溫過高！蜂鳴器已觸發！
    </div>
     <div style="margin-bottom: 20px;">
        <h2><i class="fa-solid fa-bell"></i> 警報設定</h2>
        <i class="fa-solid fa-temperature-high" style="color:red;"></i> 溫度警報: 
        <input type="number" id="temp-th" value="35" step="0.1" style="width:80px;"> °C　
        <i class="fa-solid fa-droplet" style="color:blue;"></i> 濕度警報: 
        <input type="number" id="humi-th" value="80" step="0.1" style="width:80px;"> %　
        <i class="fa-solid fa-sun" style="color:orange;"></i> 光線警報: 
        <input type="number" id="light-th" value="30" step="0.1" style="width:80px;"> lux　
        <button onclick="updateThresholds()">
            <i class="fa-solid fa-rotate"></i> 更新設定
        </button>
        <button onclick="createReport()">
            <i class="fa-solid fa-robot"></i> 生成報告
        </button>
    </div>
    <!-- 彈出視窗 -->
    <div id="modalOverlay" class="modal-overlay">
      <div class="modal">
        <h2>AI 分析結果</h2>
        <div class="modal-content-scroll" id="aiResponse"></div>
        <button class="close-btn" id="closeBtn">關閉</button>
      </div>
    </div>

    <style>
    @keyframes blink {
        0% { opacity: 1; }
        50% { opacity: 0.2; }
        100% { opacity: 1; }
    }
    </style>
    <style>
        th, td {
            border: 1px solid #ddd;
            padding: 8px;
            text-align: center;
        }
        th {
            background-color: #f2f2f2;
            position: sticky;
            top: 0;
            z-index: 2;
        }
        #history-table tbody tr:nth-child(even) {
            background-color: #fafafa;
        }
        #history-table tbody tr:hover {
            background-color: #e8f4ff;
        }
    </style>


    <canvas id="chart" width="800" height="400"></canvas>
    
    <h2>歷史數據 (即時更新)</h2>
    <div style="max-height: 300px; overflow-y: auto; border: 1px solid #ccc; border-radius: 8px;">
        <table id="history-table" border="1" style="width:100%; border-collapse: collapse;">
            <thead>
                <tr>
                    <th>時間</th>
                    <th>溫度 (°C)</th>
                    <th>濕度 (%)</th>
                    <th>光度</th>
                </tr>
            </thead>
            <tbody>
                {% for d in data %}
                <tr>
                    <td>{{ d.timestamp }}</td>
                    <td>{{ d.temperature | round(1) }}</td>
                    <td>{{ d.humidity | round(1) }}</td>
                    <td>{{ d.light | round(1) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>


    <script>
        // 用於儲存 Chart 實例，避免重複創建
        let myChart; 

        // 1. 初始圖表設置函數
        function initChart(data) {
            const ctx = document.getElementById('chart').getContext('2d');
            myChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.labels,
                    datasets: [
                        { 
                            label: '溫度 (°C)', 
                            data: data.temps, 
                            borderColor: 'red',
                            backgroundColor: 'rgba(255, 99, 132, 0.2)',
                            fill: false,
                            tension: 0.1
                        },
                        { 
                            label: '濕度 (%)', 
                            data: data.hums, 
                            borderColor: 'blue',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            fill: false,
                            tension: 0.1
                        },
                        { 
                            label: 'Light度', 
                            data: data.lights, 
                            borderColor: 'yellow',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)',
                            fill: false,
                            tension: 0.1
                        },
                    ]
                },
                options: { 
                    responsive: true,
                    scales: {
                        y: {
                            beginAtZero: false
                        }
                    }
                }
            });
        }

        // 2. 圖表更新函數 (僅更新數據，不重新創建)
        function updateChartData(data) {
            if (myChart) {
                // 更新數據
                myChart.data.labels = data.labels;
                myChart.data.datasets[0].data = data.temps; // 溫度
                myChart.data.datasets[1].data = data.hums; // 濕度
                myChart.data.datasets[2].data = data.lights; // 濕度
                // 平滑更新圖表
                myChart.update(); 
            } else {
                // 第一次載入時初始化圖表
                initChart(data); 
            }
        }

        // 3. 表格更新函數 (動態重繪歷史表格)
        function updateTable(data) {
            const tbody = document.querySelector('#history-table tbody');
            if (!tbody) return; 

            // 清空舊的行
            tbody.innerHTML = ''; 

            // 假設 /data 返回的數據是從舊到新 (labels, temps, hums)
            // 我們反向遍歷來讓最新的數據顯示在表格頂部
            for (let i = data.labels.length - 1; i >= 0; i--) {
                const row = tbody.insertRow();
                // 時間
                row.insertCell().textContent = data.labels[i]; 
                // 溫度 (保留一位小數)
                row.insertCell().textContent = parseFloat(data.temps[i]).toFixed(1); 
                // 濕度 (保留一位小數)
                row.insertCell().textContent = parseFloat(data.hums[i]).toFixed(1);
                row.insertCell().textContent = parseFloat(data.lights[i]).toFixed(1);
            }
        }

        // 4. 主要獲取和更新函數：一次調用，更新圖表和表格
        function fetchDataAndUpdate() {
            fetch('/data')
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP 錯誤! 狀態碼: ${response.status}`);
                    }
                    return response.json();
                })
                .then(data => {
                    updateChartData(data);
                    updateTable(data);

                    // ⚠️ 蜂鳴器警示互動
                    const alertBox_lig = document.getElementById('buzzer-alert-lig');
                    if (data.buzzer === "ON" && data.lig == true) {
                        alertBox_lig.style.display = 'block';
                    } else {
                        alertBox_lig.style.display = 'none';
                    }
                    // ⚠️ 蜂鳴器警示互動
                    const alertBox_hum = document.getElementById('buzzer-alert-hum');
                    if (data.buzzer === "ON" && data.hum == true) {
                        alertBox_hum.style.display = 'block';
                    } else {
                        alertBox_hum.style.display = 'none';
                    }
                    // ⚠️ 蜂鳴器警示互動
                    const alertBox_tem = document.getElementById('buzzer-alert-tem');
                    if (data.buzzer === "ON" && data.tem == true) {
                        alertBox_tem.style.display = 'block';
                    } else {
                        alertBox_tem.style.display = 'none';
                    }
                })
                .catch(error => {
                    console.error('數據獲取失敗:', error);
                });
        }

        function updateThresholds() {
            const temperature = parseFloat(document.getElementById('temp-th').value);
            const humidity = parseFloat(document.getElementById('humi-th').value);
            const light = parseFloat(document.getElementById('light-th').value);

            fetch('/set_thresholds', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ temperature, humidity, light })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    alert(`✅已更新警報設定：
        溫度 > ${data.thresholds.temperature} °C
        濕度 > ${data.thresholds.humidity} %
        光線 < ${data.thresholds.light} lux`);
                } else {
                    alert('❌ 更新失敗: ' + data.error);
                }
            })
            .catch(err => {
                alert('伺服器錯誤: ' + err);
            });
        }

        function createReport() {
            fetch('/create_report', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    // 顯示 AI 回覆內容
                    document.getElementById("aiResponse").textContent = data.message;

                    // 顯示彈窗
                    document.getElementById("modalOverlay").style.display = "flex";

                } else {
                    alert('❌ 更新失敗: ' + data.error);
                }
            })
            .catch(err => {
                alert('伺服器錯誤: ' + err);
            });
        }

        document.getElementById("closeBtn").addEventListener("click", () => {
            document.getElementById("modalOverlay").style.display = "none";
        });

        // 程式啟動點
        // 頁面載入時先執行一次
        fetchDataAndUpdate();             
        
        // 設定定時器，每 2 秒自動更新所有內容 (圖表與表格)
        setInterval(fetchDataAndUpdate, 2000); 
        
    </script>
</body>
</html>


