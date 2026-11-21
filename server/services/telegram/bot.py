"""
Telegram Bot Application & Long-Polling Worker [Person 4].
Integrates with python-telegram-bot, runs polling in a safe background task, and binds command handlers.
"""
import asyncio
import logging
from typing import Optional

from server.core.config import settings
from server.services.telegram.handlers import process_simulated_command

logger = logging.getLogger("server.services.telegram.bot")

_global_application = None


async def start_telegram_polling_safe(stop_event: asyncio.Event):
    """
    Runs the Telegram Bot polling loop in an isolated task.
    Guarded with exception handling so network errors NEVER crash FastAPI.
    """
    global _global_application

    token = settings.TELEGRAM_BOT_TOKEN
    if not token:
        logger.info("ℹ️ TELEGRAM_BOT_TOKEN not provided. Polling bot is dormant.")
        return

    try:
        from telegram import Update
        from telegram.ext import (
            Application,
            CommandHandler,
            MessageHandler,
            ContextTypes,
            filters,
        )
    except ImportError:
        logger.warning("python-telegram-bot is not installed. Polling disabled.")
        return

    logger.info("🤖 Initializing Telegram Bot Application with token...")
    application = None
    try:
        application = (
            Application.builder()
            .token(token)
            .connect_timeout(15.0)
            .read_timeout(20.0)
            .write_timeout(20.0)
            .pool_timeout(10.0)
            .build()
        )
        _global_application = application

        async def _safe_reply(update: Update, text: str):
            try:
                await update.message.reply_markdown(text)
            except Exception:
                await update.message.reply_text(text)

        # Command Handlers
        async def tg_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            arg = context.args[0] if context.args else ""
            res = await asyncio.to_thread(process_simulated_command, chat_id, f"/start {arg}".strip())
            await _safe_reply(update, res["response"])

        async def tg_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            arg = context.args[0] if context.args else ""
            res = await asyncio.to_thread(process_simulated_command, chat_id, f"/link {arg}".strip())
            await _safe_reply(update, res["response"])

        async def tg_unlink(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            res = await asyncio.to_thread(process_simulated_command, chat_id, "/unlink")
            await _safe_reply(update, res["response"])

        async def tg_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            res = await asyncio.to_thread(process_simulated_command, chat_id, "/orders")
            await _safe_reply(update, res["response"])

        async def tg_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            arg = context.args[0] if context.args else ""
            res = await asyncio.to_thread(process_simulated_command, chat_id, f"/check {arg}".strip())
            await _safe_reply(update, res["response"])

        async def tg_lockers(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            res = await asyncio.to_thread(process_simulated_command, chat_id, "/lockers")
            await _safe_reply(update, res["response"])

        async def tg_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            res = await asyncio.to_thread(process_simulated_command, chat_id, "/profile")
            await _safe_reply(update, res["response"])

        async def tg_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            res = await asyncio.to_thread(process_simulated_command, chat_id, "/help")
            await _safe_reply(update, res["response"])

        # Photo & Document Image Message Handler
        async def tg_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
            chat_id = update.effective_chat.id
            media_group_id = update.message.media_group_id

            try:
                photo_bytes = None
                filename = "shopee_upload.jpg"

                if update.message.photo:
                    file_obj = await update.message.photo[-1].get_file()
                    photo_bytes = await file_obj.download_as_bytearray()
                elif update.message.document and update.message.document.mime_type:
                    if update.message.document.mime_type.startswith("image/"):
                        file_obj = await update.message.document.get_file()
                        photo_bytes = await file_obj.download_as_bytearray()
                        filename = update.message.document.file_name or "document.jpg"

                if photo_bytes:
                    res = await asyncio.to_thread(
                        process_simulated_command,
                        chat_id=chat_id,
                        text="",
                        photo_bytes=bytes(photo_bytes),
                        filename=filename,
                        media_group_id=media_group_id,
                    )
                    if res.get("response") != "duplicate_album_ignored":
                        await _safe_reply(update, res["response"])
            except Exception as e:
                logger.error("Failed to process image from Telegram: %s", e)
                await update.message.reply_text("❌ Lỗi xử lý ảnh đơn hàng. Vui lòng thử lại.")

        application.add_handler(CommandHandler("start", tg_start))
        application.add_handler(CommandHandler("link", tg_link))
        application.add_handler(CommandHandler("unlink", tg_unlink))
        application.add_handler(CommandHandler("orders", tg_orders))
        application.add_handler(CommandHandler("status", tg_orders))
        application.add_handler(CommandHandler("check", tg_check))
        application.add_handler(CommandHandler("lockers", tg_lockers))
        application.add_handler(CommandHandler("profile", tg_profile))
        application.add_handler(CommandHandler("help", tg_help))

        # Catch both compressed photos and uncompressed image documents
        application.add_handler(
            MessageHandler(
                filters.PHOTO | (filters.Document.ALL & filters.Document.MimeType("image/*")),
                tg_image,
            )
        )

        await application.initialize()
        await application.start()
        await application.updater.start_polling(drop_pending_updates=True)
        logger.info("✅ Telegram Bot polling loop started successfully!")

        # Keep alive until shutdown signal
        while not stop_event.is_set():
            await asyncio.sleep(1.0)

    except Exception as exc:
        logger.warning("⚠️ Telegram Bot Polling caught exception: %s. FastAPI continues unaffected.", exc)
    finally:
        logger.info("🛑 Stopping Telegram Bot polling loop...")
        try:
            if application and application.updater and application.updater.running:
                await application.updater.stop()
            if application and application.running:
                await application.stop()
                await application.shutdown()
        except Exception as shutdown_err:
            logger.warning("Error stopping bot: %s", shutdown_err)


async def stop_telegram_polling_safe():
    """Explicit shutdown helper for the background bot application."""
    global _global_application
    if _global_application:
        try:
            if _global_application.updater and _global_application.updater.running:
                await _global_application.updater.stop()
            if _global_application.running:
                await _global_application.stop()
                await _global_application.shutdown()
        except Exception as e:
            logger.warning("Error in stop_telegram_polling_safe: %s", e)
        finally:
            _global_application = None

