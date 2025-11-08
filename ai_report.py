from openai import OpenAI

def generate_ai_report(sensor_context):
    client = OpenAI(
        api_key="YOUR_API_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )
    response = client.chat.completions.create(
        model="gemini-2.0-flash",
        messages=[
            {"role": "system", "content": "你是一位環境感測數據分析專家，請使用繁體中文回答。"},
            {"role": "user", "content": f"分析以下資料: {sensor_context}"}
        ]
    )
    return response.choices[0].message.content
