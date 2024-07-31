#!/usr/local/bin/python3
# coding: utf-8

import configparser
import logging
import random
import threading
import time
import json
import os
import sys
import re
import redis
from pyrogram import Client, filters, types

from search_engine import SearchEngine
from config import BOT_ID, REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD
from init_client import get_client
from utils import setup_logger, TokenBucket

setup_logger()

app = get_client()
tgdb = SearchEngine()
r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, password=REDIS_PASSWORD)

# 创建一个令牌桶，每秒允许5个操作
bucket = TokenBucket(tokens=5, fill_rate=5)

SYNC_STATUS_FILE = "sync_status.json"


def load_config():
    config = configparser.ConfigParser(allow_no_value=True)
    config.optionxform = lambda option: option
    config.read("sync.ini")
    return config


def is_allowed(chat_id, chat_type):
    config = load_config()
    whitelist = config.options("whitelist") if config.has_section("whitelist") else []
    blacklist = config.options("blacklist") if config.has_section("blacklist") else []

    chat_id_str = str(chat_id)
    chat_type_str = f"`{chat_type}`"

    if whitelist:
        return chat_id_str in whitelist or chat_type_str in whitelist
    elif blacklist:
        return chat_id_str not in blacklist and chat_type_str not in blacklist
    return True


def rate_limited_upsert(message):
    while not bucket.consume(1):
        time.sleep(0.2)
    tgdb.upsert(message)


@app.on_edited_message(~filters.chat(BOT_ID))
def message_edit_handler(client, message):
    if is_allowed(message.chat.id, message.chat.type):
        logging.info("Editing old message: %s-%s", message.chat.id, message.id)
        r.lpush('message_queue', serialize_message(message))
    else:
        logging.info("Skipping edited message from chat %s (type: %s) due to whitelist/blacklist", message.chat.id,
                     message.chat.type)

def safe_edit(msg, new_text):
    key = "sync-chat"
    if not r.exists(key):
        time.sleep(random.random())
        r.set(key, "ok", ex=2)
        msg.edit_text(new_text)


def get_last_synced_id(uid):
    return int(r.get(f"last_synced:{uid}") or 0)


def update_last_synced_id(uid, message_id):
    r.set(f"last_synced:{uid}", str(message_id))


def load_sync_status():
    if os.path.exists(SYNC_STATUS_FILE):
        try:
            with open(SYNC_STATUS_FILE, 'r') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.warning(
                f"Failed to load {SYNC_STATUS_FILE}. File might be empty or corrupted. Starting with empty sync status.")
    return {}


def save_sync_status(status):
    with open(SYNC_STATUS_FILE, 'w') as f:
        json.dump(status, f)


def clear_redis_queue():
    r.delete('message_queue')


def reset_token_bucket():
    global bucket
    bucket = TokenBucket(tokens=5, fill_rate=5)


def clear_all_sync_data():
    # 清除同步状态文件
    if os.path.exists(SYNC_STATUS_FILE):
        os.remove(SYNC_STATUS_FILE)

    # 清除 Redis 中的所有数据
    r.flushdb()

    # 重置令牌桶
    reset_token_bucket()

    # 清除 MeiliSearch 中的所有数据
    # tgdb.clean_db()


def get_chat_id(chat):
    if isinstance(chat, int):
        return chat
    if isinstance(chat, str):
        if chat.startswith('-100'):
            return int(chat)
        elif chat.startswith('-'):
            return int(chat)
        else:
            return int(chat)
    return chat.id


def sync_history():
    global msg
    time.sleep(30)
    config = load_config()

    sync_status = load_sync_status()

    if config.has_section("sync"):
        saved = app.send_message("me", "Starting to sync history...")

        for uid in list(sync_status.keys()):
            if uid not in config.options("sync"):
                del sync_status[uid]

        for uid in config.options("sync"):
            if uid not in sync_status or not sync_status[uid].get('completed', False):
                try:
                    chat_id = get_chat_id(uid)
                    chat = app.get_chat(chat_id)
                    if not is_allowed(chat.id, chat.type):
                        logging.info(f"Skipping sync for chat {uid} due to whitelist/blacklist")
                        continue

                    last_synced_id = get_last_synced_id(uid)

                    sync_status[uid] = {'completed': False, 'last_id': last_synced_id}
                    save_sync_status(sync_status)

                    for msg in app.get_chat_history(chat.id):
                        if msg.id <= last_synced_id:
                            break
                        serialized_msg = serialize_message(msg)
                        r.lpush('message_queue', serialized_msg)

                        if msg.id % 100 == 0:
                            log = f"Synced messages up to ID {msg.id} for {uid}"
                            logging.info(log)
                            safe_edit(saved, log)
                            sync_status[uid]['last_id'] = msg.id
                            save_sync_status(sync_status)
                            time.sleep(1)

                    update_last_synced_id(uid, msg.id)
                    sync_status[uid]['completed'] = True
                    save_sync_status(sync_status)
                except Exception as e:
                    logging.error(f"Error syncing history for {uid}: {str(e)}")
                    safe_edit(saved, f"Error syncing {uid}: {str(e)}")
                    time.sleep(5)

        log = "Sync history complete"
        logging.info(log)
        safe_edit(saved, log)


def serialize_message(message):
    chat = message.chat
    return json.dumps({
        'id': message.id,
        'chat': {
            'id': chat.id,
            'type': str(chat.type),
            'title': getattr(chat, 'title', None),
            'username': getattr(chat, 'username', None)
        },
        'date': message.date.isoformat(),
        'text': message.text,
        'caption': message.caption,
        'from_user': {
            'id': message.from_user.id if message.from_user else None,
            'first_name': message.from_user.first_name if message.from_user else None,
            'last_name': message.from_user.last_name if message.from_user else None,
            'username': message.from_user.username if message.from_user else None
        } if message.from_user else None
    })


@app.on_message((filters.outgoing | filters.incoming) & ~filters.chat(BOT_ID))
def message_handler(client: Client, message: types.Message):
    if is_allowed(message.chat.id, message.chat.type):
        logging.info("Adding new message: %s-%s", message.chat.id, message.id)
        r.lpush('message_queue', serialize_message(message))
    else:
        logging.info("Skipping message from chat %s (type: %s) due to whitelist/blacklist", message.chat.id,
                     message.chat.type)


def process_queue():
    while True:
        message_json = r.rpop('message_queue')
        if message_json:
            message_dict = json.loads(message_json)
            rate_limited_upsert(message_dict)
        else:
            time.sleep(1)


if __name__ == "__main__":
    if len(sys.argv) > 1:
        if sys.argv[1] == "--clear-sync":
            clear_all_sync_data()
            print("All sync data, Redis queue, and ~~MeiliSearch~~ data have been cleared.")
        elif sys.argv[1] == "--reset-sync":
            clear_all_sync_data()
            print("All sync data has been reset, and MeiliSearch data has been cleared.")
    else:
        threading.Thread(target=sync_history).start()
        threading.Thread(target=process_queue, daemon=True).start()
        app.run()
