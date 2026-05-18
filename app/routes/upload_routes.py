"""
upload_routes.py — Flask blueprint for:
  POST /upload          → extract parameters from a document
  POST /templates/save  → persist a validated template
  GET  /templates       → list saved templates
  GET  /templates/<id>  → fetch one template
  DELETE /templates/<id>→ delete a template
  GET  /               → serve the frontend

Gemini PDF strategy
-------------------
For PDFs we now send the raw file directly to Gemini's File API
(one API call, full cross-page context, no local rasterisation needed).
Set USE_PDF_DIRECT=true in your environment to enable this; the default
falls back to the original per-page image approach for compatibility.
"""
import logging
import os

from flask import Blueprint, jsonify, render_template, request

from app.services.file_service import FileService
from app.services.pdf_service import PDFService
from app.services.schema_service import SchemaService
from app.services.template_service import TemplateService
from app.services.vlm_service import VLMService

logger = logging.getLogger(__name__)

upload_blueprint = Blueprint("upload", __name__)

# When True, PDFs are sent directly to Gemini (1 API call).
# When False, PDFs are rasterised to images first (original behaviour).
_USE_PDF_DIRECT = os.environ.get("USE_PDF_DIRECT", "true").lower() == "true"


# ── Helpers ──────────────────────────────────────────────────

def _error(message: str, status: int = 400):
    return jsonify({"error": message}), status


# ── Routes ───────────────────────────────────────────────────

@upload_blueprint.route("/", methods=["GET"])
def home():
    return render_template("index.html")


@upload_blueprint.route("/upload", methods=["POST"])
def upload_document():
    """
    Accept a PDF or image, run Gemini extraction, return schema.
    Multipart field: file
    """
    uploaded_file = request.files.get("file")
    if not uploaded_file:
        return _error("No file attached.")

    saved_path: str | None = None
    temp_images: list[str] = []

    try:
        # 1. Validate + save upload
        saved_path = FileService.save_file(uploaded_file)
        original_filename = uploaded_file.filename or ""
        is_pdf = saved_path.lower().endswith(".pdf")

        # 2. Choose extraction strategy
        if is_pdf and _USE_PDF_DIRECT:
            # ── Fast path: send PDF bytes directly to Gemini ──
            logger.info("Using direct PDF extraction for: %s", original_filename)
            raw_output = VLMService.extract_parameters_from_pdf(saved_path)

        else:
            # ── Image path: rasterise PDF pages, then send images ──
            if is_pdf:
                temp_images = PDFService.convert_pdf_to_images(saved_path)
            else:
                temp_images = [saved_path]

            if not temp_images:
                return _error("Document appears to be empty or unreadable.")

            raw_output = VLMService.extract_parameters(temp_images)

        # 3. Schema normalisation + validation
        schema = SchemaService.normalize_schema(raw_output)
        schema["source_filename"] = original_filename

        return jsonify(schema), 200

    except ValueError as err:
        logger.warning("Extraction error: %s", err)
        return _error(str(err), 422)

    except Exception as err:
        logger.exception("Unexpected error during upload")
        return _error(f"Internal processing error: {err}", 500)

    finally:
        # Clean up temp rasterised images
        if temp_images and saved_path and saved_path.lower().endswith(".pdf"):
            FileService.cleanup_files(temp_images)
        # Always delete the saved upload (Gemini has its own copy)
        if saved_path:
            FileService.delete_file(saved_path)


@upload_blueprint.route("/templates/save", methods=["POST"])
def save_template():
    """
    Persist a user-validated template.
    JSON body: { name, description, source_filename, parameters[] }
    """
    body = request.get_json(silent=True)
    if not body:
        return _error("Request body must be JSON.")

    name = str(body.get("name", "")).strip()
    if not name:
        return _error("Template 'name' is required.")

    parameters = body.get("parameters")
    if not isinstance(parameters, list) or not parameters:
        return _error("'parameters' must be a non-empty list.")

    try:
        inserted_id = TemplateService.save_template(
            name=name,
            parameters=parameters,
            description=str(body.get("description", "")),
            source_filename=str(body.get("source_filename", ""))
        )
        return jsonify({"message": "Template saved.", "id": inserted_id}), 201
    except RuntimeError as err:
        logger.error("Save template error: %s", err)
        return _error(str(err), 500)


@upload_blueprint.route("/templates", methods=["GET"])
def list_templates():
    try:
        templates = TemplateService.list_templates()
        return jsonify({"templates": templates}), 200
    except RuntimeError as err:
        return _error(str(err), 500)


@upload_blueprint.route("/templates/<template_id>", methods=["GET"])
def get_template(template_id: str):
    doc = TemplateService.get_template(template_id)
    if not doc:
        return _error("Template not found.", 404)
    return jsonify(doc), 200


@upload_blueprint.route("/templates/<template_id>", methods=["DELETE"])
def delete_template(template_id: str):
    try:
        deleted = TemplateService.delete_template(template_id)
        if not deleted:
            return _error("Template not found.", 404)
        return jsonify({"message": "Deleted."}), 200
    except RuntimeError as err:
        return _error(str(err), 500)