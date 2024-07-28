#!/usr/local/bin/python3
# coding: utf-8

import os

APP_ID = int(os.getenv("APP_ID", 2000000008))
APP_HASH = os.getenv("APP_HASH", "8xxxxxxx0")
TOKEN = os.getenv("TOKEN", "15196165195:AAxxxxxxxxxxxxxxx8")

MEILI_HOST = os.getenv("MEILI_HOST", "http://127.0.0.1:7700")
MEILI_PASS = os.getenv("MEILI_MASTER_KEY", 'MIGxxxxxxxxxboxixZfjOMW8d0QORs')

OWNER_IDS  = [570000049, 619000003]
BOT_ID = int(TOKEN.split(":")[0])

PROXY = os.getenv("PROXY")
IPv6 = bool(os.getenv("IPv6", False))

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))