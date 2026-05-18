"""
TemplateService — MongoDB CRUD for saved parameter templates.
"""
import logging
from datetime import datetime, timezone

# pyrefly: ignore [missing-import]
from bson import ObjectId
# pyrefly: ignore [missing-import]
from pymongo import MongoClient
# pyrefly: ignore [missing-import]
from pymongo.collection import Collection
# pyrefly: ignore [missing-import]
from pymongo.errors import PyMongoError

from app.config import Config

logger = logging.getLogger(__name__)

_client: MongoClient | None = None
_collection: Collection | None = None


def _get_collection() -> Collection:
    global _client, _collection
    if _collection is None:
        _client = MongoClient(Config.MONGO_URI)
        db = _client[Config.MONGO_DB_NAME]
        _collection = db["templates"]
        # Index for fast name lookup
        _collection.create_index("name")
    return _collection


class TemplateService:

    @staticmethod
    def save_template(
        name: str,
        parameters: list[dict],
        description: str = "",
        source_filename: str = ""
    ) -> str:
        """
        Persist a validated template to MongoDB.
        Returns the inserted document _id as a string.
        """
        col = _get_collection()
        doc = {
            "name": name.strip(),
            "description": description.strip(),
            "parameters": parameters,
            "source_filename": source_filename,
            "created_at": datetime.now(
                tz=timezone.utc
            ).isoformat()
        }
        try:
            result = col.insert_one(doc)
            logger.info(
                "Template saved: %s (_id=%s)",
                name,
                result.inserted_id
            )
            return str(result.inserted_id)
        except PyMongoError as err:
            raise RuntimeError(
                f"Failed to save template: {err}"
            ) from err

    @staticmethod
    def list_templates() -> list[dict]:
        """Return all saved templates (lightweight list)."""
        col = _get_collection()
        try:
            cursor = col.find(
                {},
                {
                    "_id": 1,
                    "name": 1,
                    "description": 1,
                    "created_at": 1,
                    "source_filename": 1
                }
            ).sort("created_at", -1)
            templates = []
            for doc in cursor:
                doc["_id"] = str(doc["_id"])
                templates.append(doc)
            return templates
        except PyMongoError as err:
            raise RuntimeError(
                f"Failed to list templates: {err}"
            ) from err

    @staticmethod
    def get_template(template_id: str) -> dict | None:
        """Fetch a single template by its MongoDB _id."""
        col = _get_collection()
        try:
            doc = col.find_one(
                {"_id": ObjectId(template_id)}
            )
            if doc:
                doc["_id"] = str(doc["_id"])
            return doc
        except Exception as err:
            logger.error(
                "Error fetching template %s: %s",
                template_id,
                err
            )
            return None

    @staticmethod
    def delete_template(template_id: str) -> bool:
        """Delete a template. Returns True if deleted."""
        col = _get_collection()
        try:
            result = col.delete_one(
                {"_id": ObjectId(template_id)}
            )
            return result.deleted_count > 0
        except PyMongoError as err:
            raise RuntimeError(
                f"Failed to delete template: {err}"
            ) from err