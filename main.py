import telebot
import subprocess

# ================= CONFIG =================
BOT_TOKEN = "8598252838:AAH9vTbHGwy997NqRkbIZ9IMPGfBY6YUOaQ"
OWNER_ID = 7824798767  # replace with your Telegram user ID

bot = telebot.TeleBot(BOT_TOKEN)

# ================ COMMAND HANDLER =================
@bot.message_handler(func=lambda msg: True)
def handle_command(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    text = message.text.strip()

    if user_id != OWNER_ID:
        bot.reply_to(message, "🚫 Unauthorized access.")
        return

    try:
        result = subprocess.run(text, shell=True, capture_output=True, text=True, timeout=15)
        output = result.stdout.strip() or result.stderr.strip() or "✅ Command executed with no output."
        if len(output) > 3900:
            output = output[-3900:]  # prevent exceeding Telegram limits
        bot.send_message(chat_id, f"```bash\n{output}\n```", parse_mode="Markdown")
    except Exception as e:
        bot.send_message(chat_id, f"❌ Error: {str(e)}")

print("🚀 Simple Terminal Bot running...")
bot.polling()
