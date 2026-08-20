import os
import sqlite3
from pathlib import Path

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    filters,
)


# ============================================================
# CONFIGURATION
# ============================================================

BOT_TOKEN = os.getenv("8442975036:AAHm5JniUuLH6i8BrfFnginDCdZxeYSWR6g")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN is not set. Add BOT_TOKEN in Railway Variables."
    )

FEE_RATE = 10.0
EXCHANGE_RATE = 62.0


# ============================================================
# DATABASE
# ============================================================

# Railway Volume provides RAILWAY_VOLUME_MOUNT_PATH.
# Locally, use ./data.
volume_path = os.getenv("RAILWAY_VOLUME_MOUNT_PATH")

if volume_path:
    DATA_DIR = Path(volume_path)
else:
    DATA_DIR = Path(__file__).resolve().parent / "data"

DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "deposits.db"


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    conn = get_connection()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS deposits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


def add_deposit(chat_id: int, amount: float):
    conn = get_connection()

    conn.execute(
        """
        INSERT INTO deposits (chat_id, amount)
        VALUES (?, ?)
        """,
        (chat_id, amount),
    )

    conn.commit()
    conn.close()


def get_deposits(chat_id: int):
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT id, amount, created_at
        FROM deposits
        WHERE chat_id = ?
        ORDER BY id ASC
        """,
        (chat_id,),
    ).fetchall()

    conn.close()

    return rows


def clear_deposits(chat_id: int):
    conn = get_connection()

    conn.execute(
        """
        DELETE FROM deposits
        WHERE chat_id = ?
        """,
        (chat_id,),
    )

    conn.commit()
    conn.close()


# ============================================================
# CALCULATIONS
# ============================================================

def calculate(chat_id: int):
    rows = get_deposits(chat_id)

    total = sum(row["amount"] for row in rows)

    after_fee = total * (1 - FEE_RATE / 100)

    usdt = after_fee / EXCHANGE_RATE

    return rows, total, after_fee, usdt


def build_result(chat_id: int, action=None):
    rows, total, after_fee, usdt = calculate(chat_id)

    result = ""

    if action:
        result += f"{action}\n\n"

    result += f"Deposit Records ({len(rows)} entries):\n\n"

    if rows:
        for number, row in enumerate(rows, start=1):
            amount = row["amount"]

            if amount >= 0:
                result += f"{number}. +{amount:.2f}\n"
            else:
                result += f"{number}. {amount:.2f}\n"
    else:
        result += "No records yet.\n"

    result += (
        "\n"
        f"Total Deposit: {total:.2f}\n"
        f"Fee Rate: {FEE_RATE:.2f}%\n"
        f"Exchange Rate: {EXCHANGE_RATE:.2f}\n\n"
        f"Amount to Release: {after_fee:.2f} | {usdt:.2f} U\n"
        f"Pending Release: {after_fee:.2f} | {usdt:.2f} U"
    )

    return result


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    await update.message.reply_text(
        "✅ Deposit Calculator Bot Online\n\n"
        "Commands:\n"
        "/calculate - Show calculation\n"
        "/total - Show total only\n"
        "/clear - Clear your records\n"
        "/reset - Clear your records\n\n"
        "Examples:\n"
        "+1000 = Add deposit\n"
        "-500 = Deduct amount"
    )


# ============================================================
# AUTO + / -
# ============================================================

async def auto_add(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    chat_id = update.effective_chat.id

    try:

        # ADD
        if text.startswith("+"):

            value = text[1:].strip()

            if not value:
                raise ValueError

            amount = float(value)

            if amount <= 0:
                raise ValueError

            add_deposit(chat_id, amount)

            action = f"✅ Added: {amount:.2f}"

        # DEDUCT
        elif text.startswith("-"):

            value = text[1:].strip()

            if not value:
                raise ValueError

            amount = float(value)

            if amount <= 0:
                raise ValueError

            add_deposit(chat_id, -amount)

            action = f"➖ Deducted: {amount:.2f}"

        else:
            return

        await update.message.reply_text(
            build_result(chat_id, action)
        )

    except ValueError:

        await update.message.reply_text(
            "❌ Invalid amount.\n\n"
            "Use one of these formats:\n"
            "+1000\n"
            "-500"
        )


# ============================================================
# /CALCULATE
# ============================================================

async def calculate_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        build_result(chat_id)
    )


# ============================================================
# /TOTAL
# ============================================================

async def total_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    rows, total, after_fee, usdt = calculate(chat_id)

    await update.message.reply_text(
        f"💰 Current Total Deposit: {total:.2f}"
    )


# ============================================================
# /CLEAR
# ============================================================

async def clear_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    clear_deposits(chat_id)

    await update.message.reply_text(
        "🗑️ Your deposit records have been cleared."
    )


# ============================================================
# /RESET
# ============================================================

async def reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    chat_id = update.effective_chat.id

    clear_deposits(chat_id)

    await update.message.reply_text(
        "✅ Your deposit records have been reset."
    )


# ============================================================
# MAIN
# ============================================================

def main():

    print("================================")
    print("Starting Telegram Bot...")
    print(f"Database: {DB_PATH}")
    print("================================")

    # Create database/table
    init_database()

    application = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    # Commands
    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("calculate", calculate_command)
    )

    application.add_handler(
        CommandHandler("total", total_command)
    )

    application.add_handler(
        CommandHandler("clear", clear_command)
    )

    application.add_handler(
        CommandHandler("reset", reset_command)
    )

    # Automatically detect +1000 / -500
    application.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            auto_add
        )
    )

    print("✅ Bot is running...")

    # Telegram polling
    application.run_polling()


if __name__ == "__main__":
    main()
