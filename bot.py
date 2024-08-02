#!/usr/local/bin/python3
# coding: utf-8

import argparse
import logging
from io import BytesIO
from typing import Tuple, Union
import subprocess
import os
import configparser

from pyrogram import Client, enums, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from search_engine import SearchEngine
from config import OWNER_IDS, TOKEN , bot2client_log
from init_client import get_client
from utils import setup_logger, rate_limit

tgdb = SearchEngine()

setup_logger()
app = get_client(TOKEN)
chat_types = [i for i in dir(enums.ChatType) if not i.startswith("_")]
parser = argparse.ArgumentParser()
parser.add_argument("keyword", help="the keyword to be searched")
parser.add_argument("-t", "--type", help="the type of message", default=None)
parser.add_argument("-u", "--user", help="the user who sent the message", default=None)
parser.add_argument("-m", "--mode", help="match mode, e: exact match, other value is fuzzy search", default=None)


def private_use(func):
    def wrapper(client: Client, update: Union[types.Message, types.CallbackQuery]):
        if isinstance(update, types.CallbackQuery):
            chat_id = update.message.chat.id
        elif isinstance(update, types.Message):
            chat_id = update.chat.id
        else:
            logging.warning("Unsupported update type")
            return

        if chat_id not in OWNER_IDS:
            logging.warning("Unauthorized user: %s", chat_id)
            return
        return func(client, update)

    return wrapper


@app.on_message(filters.command(["start", "help"]))
@rate_limit(5)
def start_help_handler(client: Client, message: types.Message):
    client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    if message.text.startswith("/start"):
        message.reply_text("Hello, I'm search bot. Use /help to see available commands.", quote=True)
    else:
        help_text = f"""
SearchGram Bot Help:

Search Commands:
1. **Global search**: Send any message to the bot
2. **Chat type search**: `-t=GROUP keyword`, supported types are {chat_types}
3. **Chat user search**: `-u=user_id|username keyword`
4. **Exact match**: `-m=e keyword` or directly add double-quotes `"keyword"`
5. Combine search options: `-t=GROUP -u=user_id|username keyword`
6. `/private [username] keyword`: Search in private chat with username, if omitted, search in all private chats

Delete Commands:
7. `/delete`: Delete all messages (requires confirmation)
8. `/delete chat [chat_id]`: Delete all messages from a specific chat
9. `/delete user [user_id]`: Delete all messages from a specific user

Client Management Commands (Admin only):
10. `/start_client`: Start the client script
11. `/stop_client`: Stop the client script
12. `/restart_client`: Restart the client script
13. `/view_log`: view log

Sync Management Commands (Admin only):
14. `/add_sync <chat_id>`: Add a chat ID to the sync list
15. `/remove_sync <chat_id>`: Remove a chat ID from the sync list
16. `/list_sync`: List all chat IDs in the sync list

Other Commands:
17. `/ping`: Check bot and database status

Search Tips:
- You can combine different search options for more precise results
- Use quotes for exact phrase matching
- For chat type search, available types are: {', '.join(chat_types)}

Note: Some commands are restricted to admin use only.
        """
        message.reply_text(help_text, quote=True, parse_mode=enums.ParseMode.MARKDOWN)


@app.on_message(filters.command(["ping"]))
@private_use
@rate_limit(10)
def ping_handler(client: Client, message: types.Message):
    client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    text = tgdb.ping()
    client.send_message(message.chat.id, text, parse_mode=enums.ParseMode.MARKDOWN)


@app.on_message(filters.command(["delete"]))
@private_use
@rate_limit(10)
def delete_messages_handler(client: Client, message: types.Message):
    args = message.text.split()[1:]

    if len(args) == 0:
        # 删除所有消息的二次确认
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Yes, delete all", callback_data="delete_all_confirm")],
            [InlineKeyboardButton("No, cancel", callback_data="delete_cancel")]
        ])
        message.reply_text("Are you sure you want to delete all messages? This action cannot be undone.",
                           reply_markup=keyboard)
    elif len(args) == 2:
        delete_type, id_to_delete = args
        try:
            id_to_delete = int(id_to_delete)
        except ValueError:
            message.reply_text("Error: ID must be an integer")
            return

        if delete_type == "chat":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes, delete", callback_data=f"delete_chat_confirm_{id_to_delete}")],
                [InlineKeyboardButton("No, cancel", callback_data="delete_cancel")]
            ])
            message.reply_text(f"Are you sure you want to delete all messages from chat {id_to_delete}?",
                               reply_markup=keyboard)
        elif delete_type == "user":
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("Yes, delete", callback_data=f"delete_user_confirm_{id_to_delete}")],
                [InlineKeyboardButton("No, cancel", callback_data="delete_cancel")]
            ])
            message.reply_text(f"Are you sure you want to delete all messages from user {id_to_delete}?",
                               reply_markup=keyboard)
        else:
            message.reply_text("Error: First argument must be either 'chat' or 'user'")
    else:
        message.reply_text("Usage: /delete [chat|user] [id]")


@app.on_callback_query(filters.regex(r"^delete_"))
@private_use
def delete_callback_handler(client: Client, callback_query: types.CallbackQuery):
    data = callback_query.data

    try:
        if data == "delete_all_confirm":
            result = tgdb.delete_messages()
        elif data.startswith("delete_chat_confirm_"):
            chat_id = int(data.split("_")[-1])
            result = tgdb.delete_messages(chat_id=chat_id)
        elif data.startswith("delete_user_confirm_"):
            user_id = int(data.split("_")[-1])
            result = tgdb.delete_messages(user_id=user_id)
        elif data == "delete_cancel":
            result = "Delete operation cancelled."
        else:
            result = "Invalid operation"

        callback_query.edit_message_text(result)
    except Exception as e:
        error_message = f"An error occurred while deleting messages: {str(e)}"
        logging.error(error_message, exc_info=True)
        callback_query.edit_message_text(error_message)




@app.on_message(filters.command(["start_client", "stop_client", "restart_client", "live"]))
@private_use
def manage_client(client: Client, message: types.Message):
    command = message.text.split()[0][1:]  # 获取命令名称
    client_script = "./client.py"
    log_file = "./client.log"
    client_status = 10
    if command == "start_client" and bot2client_log:
        try:
            with open(log_file, "a") as log:
                subprocess.Popen(["python", client_script], stdout=log, stderr=log)

            message.reply_text("Client script started successfully. Logs are being written to client.log.")
        except Exception as e:
            message.reply_text(f"Failed to start client script: {str(e)}")
    
    elif command == "start_client":
        subprocess.Popen(["python", client_script])
        message.reply_text("Client script started successfully.")


    
    elif command == "stop_client":
        try:
            subprocess.run(["pkill", "-f", client_script])
            subprocess.run(["pkill", "-f", client_script])
            subprocess.run(["pkill", "-f", client_script])
            message.reply_text("Client script stopped successfully.")

        except Exception as e:
            message.reply_text(f"Failed to stop client script: {str(e)}")
    
    elif command == "restart_client":
        try:
            subprocess.run(["pkill", "-f", client_script])
            with open(log_file, "a") as log:
                subprocess.Popen(["python", client_script], stdout=log, stderr=log)
            message.reply_text("Client script restarted successfully. Logs are being written to client.log.")

        except Exception as e:
            message.reply_text(f"Failed to restart client script: {str(e)}")

    elif command == "live":
        message.reply_text(f"Client is {client_status}")


    elif command == "view_log":
        try:
            with open(log_file, "r") as log:
                last_lines = log.readlines()[-20:]  # 获取最后20行
            log_content = "".join(last_lines)
            message.reply_text(f"Last 20 lines of client.log:\n\n{log_content}")
        except Exception as e:
            message.reply_text(f"Failed to read log file: {str(e)}")
@app.on_message(filters.command(["view_client_log"]))
@private_use
def view_client_log(client: Client, message: types.Message):
    log_file = "./client.log"
    try:
        with open(log_file, "r") as log:
            last_lines = log.readlines()[-50:]  # 获取最后50行
        log_content = "".join(last_lines)
        if len(log_content) > 4096:
            # 如果日志内容太长，发送为文件
            with BytesIO(log_content.encode()) as file:
                file.name = "client_log.txt"
                message.reply_document(file, caption="Last 50 lines of client.log")
        else:
            message.reply_text(f"Last 50 lines of client.log:\n\n{log_content}")
    except Exception as e:
        message.reply_text(f"Failed to read log file: {str(e)}")
@app.on_message(filters.command(["add_sync", "remove_sync", "list_sync"]))
@private_use
def manage_sync(client: Client, message: types.Message):
    command = message.text.split()[0][1:]
    args = message.text.split()[1:]
    config = configparser.ConfigParser(allow_no_value=True)
    config.read("./sync.ini")
    
    if command == "add_sync":
        if len(args) != 1:
            message.reply_text("用法: /add_sync <chat_id>")
            return
        chat_id = args[0]
        if "sync" not in config:
            config["sync"] = {}
        config["sync"][chat_id] = None
        with open("./sync.ini", "w") as configfile:
            config.write(configfile)
        message.reply_text(f"已将 {chat_id} 添加到同步列表。")
    
    elif command == "remove_sync":
        if len(args) != 1:
            message.reply_text("用法: /remove_sync <chat_id>")
            return
        chat_id = args[0]
        if "sync" in config and chat_id in config["sync"]:
            config.remove_option("sync", chat_id)
            with open("./sync.ini", "w") as configfile:
                config.write(configfile)
            message.reply_text(f"已从同步列表中移除 {chat_id}。")
        else:
            message.reply_text(f"在同步列表中未找到 {chat_id}。")
    
    elif command == "list_sync":
        if "sync" in config and config["sync"]:
            sync_list = "\n".join(config["sync"].keys())
            message.reply_text(f"当前同步列表：\n{sync_list}")
        else:
            message.reply_text("同步列表为空。")


def generate_navigation(page, total_pages):
    if total_pages <= 1:
        return None

    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"p|{page - 1}"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"n|{page + 1}"))

    return InlineKeyboardMarkup([buttons])


def parse_search_results(data: dict) -> str:
    result = ""
    hits = data.get("hits", [])
    total_hits = data.get("estimatedTotalHits", 0)
    result += f"Total Hits: {total_hits}\n\n"

    if not hits:
        return result + "No results found."

    for hit in hits:
        text = hit.get("text") or hit.get("caption")
        if not text:
            continue

        chat_id = hit["chat"]["id"]
        chat_type = hit["chat"]["type"]
        from_user = hit.get("from_user", {})

        if chat_type == "ChatType.CHANNEL":
            chat_username = hit["chat"].get("title", "Channel")
            from_username = "Channel"
        elif chat_type == "ChatType.PRIVATE":
            chat_username = from_user.get('username') or str(chat_id)
            from_username = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or "Unknown"
        else:  # 群组
            chat_username = hit["chat"].get("title", str(chat_id))
            from_username = f"{from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip() or "Unknown"

        date = hit["date"]
        message_id = hit["message_id"]

        if chat_type == "ChatType.PRIVATE":
            deep_link = f"tg://user?id={chat_id}"
            text_link = f"tg://openmessage?user_id={chat_id}&message_id={message_id}"
        elif isinstance(chat_id, int) and chat_id < 0:
            chat_id_str = str(abs(chat_id))
            if chat_id_str.startswith('100'):
                chat_id_str = chat_id_str[3:]
            deep_link = f"tg://resolve?domain=c/{chat_id_str}"
            text_link = f"https://t.me/c/{chat_id_str}/{message_id}"
        else:
            deep_link = f"tg://user?id={chat_id}"
            text_link = f"https://t.me/{chat_username}/{message_id}"

        result += f"{from_username} -> [{chat_username}]({deep_link}) on {date}:\n"
        result += f"`{text[:100]}{'...' if len(text) > 100 else ''}`\n"
        result += f"[Quick Jump]({text_link})\n\n"

    return result


def parse_and_search(text, page=1) -> Tuple[str, InlineKeyboardMarkup | None]:
    args = parser.parse_args(text.split())
    logging.info("Search keyword: %s, type: %s, user: %s, page: %s, mode: %s", args.keyword, args.type, args.user, page,
                 args.mode)
    results = tgdb.search(args.keyword, args.type, args.user, page, args.mode)
    text = parse_search_results(results)

    total_hits = results.get("estimatedTotalHits", 0)
    total_pages = (total_hits - 1) // 10 + 1  # Assuming 10 results per page
    markup = generate_navigation(page, total_pages)
    return text, markup


@app.on_message(filters.command(chat_types) & filters.text & filters.incoming)
@private_use
@rate_limit(3)
def type_search_handler(client: Client, message: types.Message):
    parts = message.text.split(maxsplit=2)
    chat_type = parts[0][1:].upper()
    if len(parts) == 1:
        message.reply_text(f"/{chat_type} [username] keyword", quote=True, parse_mode=enums.ParseMode.MARKDOWN)
        return
    user_filter = f"-u={parts[1]}" if len(parts) > 2 else ""
    keyword = parts[2] if len(parts) > 2 else parts[1]

    refined_text = f"-t={chat_type} {user_filter} {keyword}"
    client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    text, markup = parse_and_search(refined_text)
    send_search_result(client, message, text, markup)


@app.on_message(filters.text & filters.incoming)
@private_use
@rate_limit(2)
def search_handler(client: Client, message: types.Message):
    client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    try:
        text, markup = parse_and_search(message.text)
        send_search_result(client, message, text, markup)
    except Exception as e:
        error_message = f"An error occurred while processing your request: {str(e)}"
        logging.error(f"Error in search_handler: {str(e)}", exc_info=True)
        message.reply_text(error_message, quote=True)


def send_search_result(client: Client, message: types.Message, text: str, markup: InlineKeyboardMarkup):
    if not text:
        message.reply_text("No results found.", quote=True)
        return

    if len(text) > 4096:
        logging.warning("Message too long, sending as file instead")
        file = BytesIO(text.encode())
        file.name = "search_result.txt"
        message.reply_text("Your search result is too long, sending as file instead", quote=True)
        message.reply_document(file, quote=True, parse_mode=enums.ParseMode.MARKDOWN, reply_markup=markup)
        file.close()
    else:
        message.reply_text(
            text, quote=True, parse_mode=enums.ParseMode.MARKDOWN, reply_markup=markup, disable_web_page_preview=True
        )


@app.on_callback_query(filters.regex(r"n|p"))
@rate_limit(1)
def send_method_callback(client: Client, callback_query: types.CallbackQuery):
    direction, page = callback_query.data.split("|")
    new_page = int(page) + (1 if direction == "n" else -1)
    message = callback_query.message
    user_query = message.reply_to_message.text

    parts = user_query.split(maxsplit=2)
    if user_query.startswith("/"):
        user_filter = f"-u={parts[1]}" if len(parts) > 2 else ""
        keyword = parts[2] if len(parts) > 2 else parts[1]
        refined_text = f"-t={parts[0][1:].upper()} {user_filter} {keyword}"
    else:
        refined_text = user_query

    client.send_chat_action(message.chat.id, enums.ChatAction.TYPING)
    new_text, new_markup = parse_and_search(refined_text, new_page)
    message.edit_text(new_text, reply_markup=new_markup, disable_web_page_preview=True)


if __name__ == "__main__":
    app.run()