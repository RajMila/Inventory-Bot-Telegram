from flask import Flask, request, send_file
import requests
import pandas as pd
import gspread
from google.oauth2.credentials import Credentials
import json
import os
import io

app = Flask(__name__)
TOKEN = os.getenv("TELEGRAM_TOKEN")

# State dictionary to keep track of users
user_state = {}

# Authorize Google Sheets
def authorize_oauth():
    with open('/root/Inventory-Bot-Telegram/token.json') as f:
    # with open('/etc/secrets/token.json') as f:
        token_data = json.load(f)
    creds = Credentials.from_authorized_user_info(token_data)
    return gspread.authorize(creds)

def load_stock_data():
    client = authorize_oauth()
    sheet = client.open_by_url('https://docs.google.com/spreadsheets/d/1hdflZHrim-qPNHeCgPr3J_6OBbggccjftziVGawzgY8/edit')
    worksheet = sheet.worksheet("Summary")
    rows = worksheet.get_all_values()
    header = rows[2]
    data = rows[3:]
    return pd.DataFrame(data, columns=header)

def load_pendency_data():
    client = authorize_oauth()
    sheet = client.open_by_url('https://docs.google.com/spreadsheets/d/1ZhYd7Mx5A0SlLpIAsojkEeHavMdHyvOqKArJ-RaXl2Y/edit')
    worksheet = sheet.worksheet("Sheet1")
    rows = worksheet.get_all_values()
    header = rows[0]
    data = rows[1:]
    return pd.DataFrame(data, columns=header)

def get_unique_ss_names(df):
    return sorted(df['Trimmed SS Name'].dropna().unique().tolist())

def get_summary_text(df, ss_name):
    filtered = df[df['Trimmed SS Name'] == ss_name]
    filtered['Item Quantity'] = pd.to_numeric(filtered['Item Quantity'], errors='coerce').fillna(0)
    filtered['Item Price Excluding Tax'] = pd.to_numeric(filtered['Item Price Excluding Tax'], errors='coerce').fillna(0)
    total_qty = filtered['Item Quantity'].sum()
    total_amt = filtered['Item Price Excluding Tax'].sum()
    return f"\U0001F4CB *Summary for {ss_name}*\nPending Qty: *{int(total_qty)}*\nPending Amount: *₹{total_amt:,.2f}*"


def send_excel_file(chat_id, df):
    output = io.BytesIO()
    df.to_excel(output, index=False)
    output.seek(0)
    files = {'document': ('data.xlsx', output)}
    requests.post(f"https://api.telegram.org/bot{TOKEN}/sendDocument", data={'chat_id': chat_id}, files=files)

def send_message(chat_id, text, reply_markup=None):
    chunks = split_message(text)
    for chunk in chunks:
        data = {
            "chat_id": chat_id,
            "text": chunk,
            "parse_mode": "Markdown"
        }
        if reply_markup and chunk == chunks[-1]:
            data["reply_markup"] = json.dumps(reply_markup)
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data=data)

def split_message(text, limit=1500):
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

@app.route("/webhook", methods=["POST","GET"])
def webhook():
    data = request.get_json(force=True, silent=True)
    print("Webhook received:", data)
    message = data.get("message")
    if not message:
        return "ok", 200

    chat_id = message["chat"]["id"]
    text = message.get("text", "").strip()

    # STOCK QUERY PATH
    if text.upper().startswith("STOCK"):
        stock_df = load_stock_data()
        parent_code = text.upper().replace("STOCK", "").strip()
        matching = stock_df[stock_df['Parent Code'] == parent_code.upper()]
        if matching.empty:
            send_message(chat_id, f"No SKUs found for parent code '{parent_code}'.")
        else:
            reply = [f"\U0001F4E6 *Parent Code: {parent_code}*"]
            for _, row in matching.iterrows():
                reply.append(
                    f"\n\U0001F539 *{row['SKU Code']}*\n"
                    f"GT Stock: {row['Available Quantity']} | Online Stock: {row['Available Quantity.']}\n"
                    # f"GT Pendency: {row['Pendency GT']} | Online Pendency: {row['Pendency Online']}"
                )
            send_message(chat_id, "\n".join(reply))
        return "ok", 200

    # SS PENDENCY PATH
    pendency_df = load_pendency_data()

    if text.lower() in ["/start", "start"]:
        ss_list = get_unique_ss_names(pendency_df)
        keyboard = [[{"text": ss}] for ss in ss_list]
        reply_markup = {"keyboard": keyboard, "one_time_keyboard": True, "resize_keyboard": True}
        user_state[chat_id] = {}
        send_message(chat_id, "Select a Super Stockist (SS):", reply_markup)
        return "ok", 200

    if chat_id in user_state and 'ss_name' not in user_state[chat_id]:
        if text in pendency_df['Trimmed SS Name'].values:
            user_state[chat_id]['ss_name'] = text
            reply = get_summary_text(pendency_df, text)
            send_message(chat_id, reply)
            filtered_df = pendency_df[pendency_df['Trimmed SS Name'] == text]
            send_excel_file(chat_id, filtered_df)
        else:
            send_message(chat_id, "Invalid SS. Please try again.")
        user_state.pop(chat_id, None)
        return "ok", 200

    send_message(chat_id, "Type /start to begin")
    return "ok", 200

@app.route("/")
def home():
    return "Telegram bot is running!"

if __name__ == "__main__":
    # app.run(debug=True)
    app.run(host="0.0.0.0", port=5000)
