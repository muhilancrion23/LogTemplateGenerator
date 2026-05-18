import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Flask
    SECRET_KEY: str = os.getenv(
        "SECRET_KEY",
        "clonos-dev-secret"
    )
    DEBUG: bool = os.getenv(
        "FLASK_DEBUG",
        "False"
    ).lower() == "true"

    # Upload
    UPLOAD_FOLDER: str = os.getenv(
        "UPLOAD_FOLDER",
        "uploads"
    )
    TEMP_FOLDER: str = os.getenv(
        "TEMP_FOLDER",
        "temp"
    )
    MAX_CONTENT_LENGTH: int = int(
        os.getenv("MAX_CONTENT_LENGTH_MB", "50")
    ) * 1024 * 1024  # Convert MB → bytes

    # MongoDB
    MONGO_URI: str = os.getenv(
        "MONGO_URI",
        "mongodb://localhost:27017/"
    )
    MONGO_DB_NAME: str = os.getenv(
        "MONGO_DB_NAME",
        "clonos_ai"
    )

    # VLM Model
    VLM_MODEL_ID: str = os.getenv(
        "VLM_MODEL_ID",
        "HuggingFaceTB/SmolVLM-256M"
    )
    VLM_MAX_NEW_TOKENS: int = int(
        os.getenv("VLM_MAX_NEW_TOKENS", "1024")
    )

    @staticmethod
    def ensure_directories():
        """Create required directories if they don't exist."""
        for folder in [
            Config.UPLOAD_FOLDER,
            Config.TEMP_FOLDER
        ]:
            os.makedirs(folder, exist_ok=True)