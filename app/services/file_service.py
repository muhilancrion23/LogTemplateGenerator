import os
import uuid
import logging

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.config import Config

logger = logging.getLogger(__name__)


class FileService:

    ALLOWED_EXTENSIONS: set[str] = {
        # Images
        "png",
        "jpg",
        "jpeg",
        # Documents
        "pdf",
        # Spreadsheets
        "xlsx",
        "xls",
        "csv",
    }

    # Extensions that require spreadsheet → PDF conversion before
    # being sent to Gemini.
    SPREADSHEET_EXTENSIONS: set[str] = {"xlsx", "xls", "csv"}

    MAX_FILENAME_LENGTH: int = 200

    @staticmethod
    def allowed_file(filename: str) -> bool:
        """Check if file extension is in the allowed set."""
        if not filename or "." not in filename:
            return False
        ext = filename.rsplit(".", 1)[1].lower()
        return ext in FileService.ALLOWED_EXTENSIONS

    @staticmethod
    def get_extension(filename: str) -> str:
        """Return lowercase extension without dot."""
        return filename.rsplit(".", 1)[1].lower()

    @staticmethod
    def is_spreadsheet(file_path: str) -> bool:
        """Return True if the file needs spreadsheet → PDF conversion."""
        ext = FileService.get_extension(file_path)
        return ext in FileService.SPREADSHEET_EXTENSIONS

    @staticmethod
    def generate_safe_filename(filename: str) -> str:
        """
        Sanitize filename and prepend a UUID to prevent
        collisions and path traversal attacks.
        """
        secured = secure_filename(filename)

        # Fallback if secure_filename strips everything
        if not secured:
            secured = "upload"

        # Truncate to avoid filesystem limits
        if len(secured) > FileService.MAX_FILENAME_LENGTH:
            ext = FileService.get_extension(secured)
            secured = f"file.{ext}"

        unique_prefix = str(uuid.uuid4())
        return f"{unique_prefix}_{secured}"

    @staticmethod
    def save_file(file: FileStorage) -> str:
        """
        Validate and persist an uploaded file.

        Returns the absolute path to the saved file.
        Raises ValueError for invalid input.
        """
        if not file:
            raise ValueError("No file provided.")

        if not file.filename:
            raise ValueError("File has an empty filename.")

        if not FileService.allowed_file(file.filename):
            allowed = ", ".join(
                sorted(FileService.ALLOWED_EXTENSIONS)
            )
            raise ValueError(
                f"Unsupported file type. "
                f"Allowed: {allowed}"
            )

        safe_name = FileService.generate_safe_filename(
            file.filename
        )
        save_path = os.path.join(
            Config.UPLOAD_FOLDER,
            safe_name
        )

        file.save(save_path)
        logger.info("File saved: %s", save_path)
        return save_path

    @staticmethod
    def delete_file(file_path: str) -> None:
        """Silently remove a file if it exists."""
        try:
            if file_path and os.path.exists(file_path):
                os.remove(file_path)
                logger.info("Deleted file: %s", file_path)
        except OSError as err:
            logger.warning(
                "Could not delete %s: %s",
                file_path,
                err
            )

    @staticmethod
    def cleanup_files(paths: list[str]) -> None:
        """Remove a list of temporary files."""
        for path in paths:
            FileService.delete_file(path)