import requests

response = requests.get("https://2d8e-2400-4070-3b23-8d10-58e0-4609-9985-969.ngrok-free.app/scheduled-messages/send")

if response.status_code == 200:
    print("✅ 成功:", response.json())  # {'message': 'こんにちは、FastAPI!'}
else:
    print("❌ エラー:", response.status_code, response.text)