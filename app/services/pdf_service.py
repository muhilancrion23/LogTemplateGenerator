import os
import uuid
import logging

# pyrefly: ignore [missing-import]
import fitz  # PyMuPDF
from PIL import Image

from app.config import Config

logger = logging.getLogger(__name__)

# Render resolution: 2× scale = ~150 DPI → good OCR quality
# without blowing up memory on a 4 GB GPU machine.
RENDER_MATRIX = fitz.Matrix(2, 2)


class PDFService:

    @staticmethod
    def convert_pdf_to_images(
        pdf_path: str
    ) -> list[str]:
        """
        Rasterise every page of *pdf_path* to a PNG in the
        TEMP_FOLDER.

        Returns a list of absolute image paths.
        Raises RuntimeError if the file cannot be opened.
        """
        if not os.path.isfile(pdf_path):
            raise FileNotFoundError(
                f"PDF not found: {pdf_path}"
            )

        generated: list[str] = []

        try:
            pdf_doc = fitz.open(pdf_path)
        except Exception as err:
            raise RuntimeError(
                f"Cannot open PDF: {err}"
            ) from err

        logger.info(
            "Converting PDF (%d pages): %s",
            len(pdf_doc),
            pdf_path
        )

        try:
            for page_num in range(len(pdf_doc)):
                page = pdf_doc.load_page(page_num)
                pixmap = page.get_pixmap(
                    matrix=RENDER_MATRIX
                )

                image_filename = f"{uuid.uuid4()}.png"
                image_path = os.path.join(
                    Config.TEMP_FOLDER,
                    image_filename
                )

                # Convert via Pillow so we control format/quality
                pil_image = Image.frombytes(
                    "RGB",
                    [pixmap.width, pixmap.height],
                    pixmap.samples
                )
                pil_image.save(image_path, format="PNG")
                generated.append(image_path)

                logger.debug(
                    "Rendered page %d → %s",
                    page_num + 1,
                    image_path
                )
        finally:
            pdf_doc.close()

        return generated