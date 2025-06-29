from flask import Flask, request
import requests
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
import json
import os

app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_TOKEN")

def authorize_oauth():
    with open('/etc/secrets/token.json') as f:
        token_data = json.load(f)
    creds = Credentials.from_authorized_user_info(token_data)
    return gspread.authorize(creds)

def load_sheet_data():
    client = authorize_oauth()
    sheet = client.open_by_url('https://docs.google.com/spreadsheets/d/1hdflZHrim-qPNHeCgPr3J_6OBbggccjftziVGawzgY8/edit')
    worksheet = sheet.worksheet("Summary")
    rows = worksheet.get_all_values()
    header = rows[2]
    data = rows[3:]
    return pd.DataFrame(data, columns=header)

def fetch_sku_data_by_parent(parent_code, df):
    matching = df[df['Parent Code'] == parent_code.upper()]
    if matching.empty:
        return f"No SKUs found for parent code '{parent_code}'."
    
    messages = [f"📦 *Parent Code: {parent_code}*"]
    for _, row in matching.iterrows():
        messages.append(
            f"\n🔹 *{row['SKU Code']}*\n"
            f"GT Stock: {row['Available Quantity']} | Online Stock: {row['Available Quantity.']}\n"
            f"GT Pendency: {row['Pendency GT']} | Online Pendency: {row['Pendency Online']}"
        )
    return "\n".join(messages)


def split_message(text, limit=4000):
    lines = text.split('\n')
    chunks = []
    current_chunk = ''
    for line in lines:
        if len(current_chunk + '\n' + line) <= limit:
            current_chunk += '\n' + line
        else:
            chunks.append(current_chunk.strip())
            current_chunk = line
    if current_chunk:
        chunks.append(current_chunk.strip())
    return chunks
    

@app.route(f"/{TOKEN}", methods=["POST"])
def telegram_webhook():
    data = request.get_json()
    if "message" not in data or "text" not in data["message"]:
        return "No message", 200
    chat_id = data['message']['chat']['id']
    text = data['message']['text'].strip().upper()
    parent_code = text.replace("STOCK", "").strip()

    df = load_sheet_data()
    reply = fetch_sku_data_by_parent(parent_code, df)
    chunks = split_message(reply)

    for chunk in chunks:
        send_message(chat_id, chunk)


    # requests.post(
    #     f"https://api.telegram.org/bot{TOKEN}/sendMessage",
    #     data={"chat_id": chat_id, "text": reply, "parse_mode": "Markdown"}
    # )

    return "ok", 200

@app.route("/", methods=["GET"])
def index():
    return "Telegram bot is running!"

if __name__ == "__main__":
    app.run(debug=True)
