# 即時環境監測平台 (Raspberry Pi)
一個整合 DHT11 + APDS9930 感測器的 Flask 即時監測系統，可視化環境數據並自動生成 AI 分析報告。

## 安裝
```bash
git clone https://github.com/yourname/raspi_env_monitor.git
cd raspi_env_monitor
pip install -r requirements.txt
python app.py
```

## 功能
- 即時溫濕度與光度顯示
- 警報閾值可調整
- 蜂鳴器與 LED 警示
- AI 趨勢報告生成（Gemini API）
