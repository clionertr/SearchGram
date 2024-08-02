#!/usr/local/bin/python3
# coding: utf-8

import logging
import meilisearch
from meilisearch.errors import MeiliSearchApiError
from config import MEILI_HOST, MEILI_PASS
from utils import sizeof_fmt


class SearchEngine:
    def __init__(self):
        try:
            self.client = meilisearch.Client(MEILI_HOST, MEILI_PASS)
            self.ensure_index_exists()
        except Exception as e:
            logging.critical(f"Failed to connect to MeiliSearch: {str(e)}")
            raise

    def ensure_index_exists(self):
        try:
            self.client.get_index("telegram")
        except MeiliSearchApiError:
            logging.info("Creating new 'telegram' index")
            self.client.create_index("telegram", {"primaryKey": "ID"})
            self.client.index("telegram").update_filterable_attributes(["chat.id", "chat.type"])
            self.client.index("telegram").update_ranking_rules(
                ["timestamp:desc", "words", "typo", "proximity", "attribute", "sort", "exactness"]
            )
            self.client.index("telegram").update_sortable_attributes(["timestamp"])

    def upsert(self, message):
        try:
            data = {
                "ID": f"{message['chat']['id']}-{message['id']}",
                "message_id": message['id'],
                "chat": message['chat'],
                "date": message['date'],
                "text": message.get('text', ''),
                "caption": message.get('caption', ''),
                "from_user": message.get('from_user', {}),
                "timestamp": message['date']
            }

            self.client.index("telegram").add_documents([data], primary_key="ID")
        except MeiliSearchApiError as e:
            logging.error(f"Error upserting document: {str(e)}")
            self.ensure_index_exists()

    def search(self, keyword, _type=None, user=None, page=1, mode=None) -> dict:
        try:
            if mode:
                keyword = f'"{keyword}"'
            user = self._clean_user(user)
            params = {
                "limit": 10,
                "offset": (page - 1) * 10,
                "sort": ["timestamp:desc"],
                "matchingStrategy": "all" if mode else "last",
                "filter": None,
            }
            if user or _type:
                filter_conditions = []
                if user:
                    filter_conditions.append(f"chat.id = {user}")
                if _type:
                    filter_conditions.append(f"chat.type = {_type}")
                params["filter"] = " AND ".join(filter_conditions)

            logging.info(f"Search params: {params}")
            result = self.client.index("telegram").search(keyword, params)
            logging.info(f"Search result: {result}")
            return result
        except MeiliSearchApiError as e:
            if e.error_code == "index_not_found":
                logging.warning("Index not found during search, attempting to recreate")
                self.ensure_index_exists()
                return {"hits": [], "estimatedTotalHits": 0}
            logging.error(f"Error during search: {str(e)}")
            raise

    def ping(self):
        try:
            text = "Pong!\n"
            stats = self.client.get_all_stats()
            size = stats["databaseSize"]
            last_update = stats["lastUpdate"]
            for uid, index in stats["indexes"].items():
                text += f"Index {uid} has {index['numberOfDocuments']} documents\n"
            text += f"\nDatabase size: {sizeof_fmt(size)}\nLast update: {last_update}\n"
            return text
        except MeiliSearchApiError as e:
            logging.error(f"Error pinging MeiliSearch: {str(e)}")
            return "Error: Unable to ping MeiliSearch"

    def clean_db(self):
        try:
            self.client.delete_index("telegram")
            self.ensure_index_exists()
            return "Database cleaned and index recreated"
        except MeiliSearchApiError as e:
            logging.error(f"Error cleaning database: {str(e)}")
            return "Error: Unable to clean database"

    def delete_messages(self, chat_id=None, user_id=None):
        if chat_id is None and user_id is None:
            # 删除所有消息
            try:
                self.client.index("telegram").delete_all_documents()
                return "All messages have been deleted."
            except MeiliSearchApiError as e:
                logging.error(f"Error deleting all messages: {str(e)}")
                return f"Error occurred while deleting all messages: {str(e)}"

        filter_conditions = []
        if chat_id is not None:
            filter_conditions.append(f"chat.id = {chat_id}")
        if user_id is not None:
            filter_conditions.append(f"from_user.id = {user_id}")

        filter_string = " AND ".join(filter_conditions)
        params = {
            "filter": filter_string,
            "limit": 1000,
        }

        deleted_count = 0
        try:
            while True:
                results = self.client.index("telegram").search("", params)
                if not results["hits"]:
                    break

                ids_to_delete = [hit["ID"] for hit in results["hits"]]
                self.client.index("telegram").delete_documents(ids_to_delete)
                deleted_count += len(ids_to_delete)

            return f"Deleted {deleted_count} messages"
        except MeiliSearchApiError as e:
            logging.error(f"Error deleting messages: {str(e)}")
            return f"Error occurred. Deleted {deleted_count} messages before error: {str(e)}"

    @staticmethod
    def _clean_user(user):
        if user:
            return user.strip().replace("@", "")
        return None


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    search_engine = SearchEngine()
    print(search_engine.ping())