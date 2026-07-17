"""Telegram tool for Robert - sending messages via Telegram bot."""

import asyncio
from telegram import Bot
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


async def send_telegram_async(message: str, chat_id: str = None) -> bool:
    """Send a message via Telegram bot (async)."""
    try:
        token = TELEGRAM_BOT_TOKEN
        if not token:
            raise ValueError("TELEGRAM_BOT_TOKEN not configured")
        
        target_chat = chat_id or TELEGRAM_CHAT_ID
        if not target_chat:
            raise ValueError("No chat_id provided and TELEGRAM_CHAT_ID not configured")
        
        bot = Bot(token=token)
        await bot.send_message(
            chat_id=target_chat,
            text=message,
            parse_mode="Markdown"
        )
        return True
    except Exception as e:
        print(f"Failed to send Telegram message: {str(e)}")
        return False


def send_telegram(message: str, chat_id: str = None) -> bool:
    """
    Send a message via Telegram bot (sync wrapper).
    
    Args:
        message: Message text to send
        chat_id: Optional chat ID override
    
    Returns:
        True if successful, False otherwise
    """
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(send_telegram_async(message, chat_id))
