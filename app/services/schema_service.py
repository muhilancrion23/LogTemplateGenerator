"""
SchemaService — turns raw VLM text output into a validated,
deduplicated ParameterList dict ready for the frontend.
"""
import json
import logging
import re

from pydantic import ValidationError

from app.models.parameter_model import ParameterList

logger = logging.getLogger(__name__)

# Valid parameter types
VALID_TYPES = {"number", "text", "boolean"}


class SchemaService:

    # ── JSON Cleaning ─────────────────────────────────────

    @staticmethod
    def _strip_markdown_fences(text: str) -> str:
        """Remove ```json … ``` or ``` … ``` wrappers."""
        text = re.sub(
            r"```(?:json)?\s*",
            "",
            text,
            flags=re.IGNORECASE
        )
        return text.replace("```", "")

    @staticmethod
    def _trim_to_json_boundaries(text: str) -> str:
        """
        Slice the string so it starts at the first '{' and
        ends at the last '}'. Handles leading/trailing noise
        from VLM preambles like 'Here is the JSON:'.
        """
        first = text.find("{")
        last = text.rfind("}")
        if first == -1 or last == -1 or last < first:
            return text
        return text[first : last + 1]

    @staticmethod
    def clean_json_response(raw: str) -> str:
        text = raw.strip()
        text = SchemaService._strip_markdown_fences(text)
        text = SchemaService._trim_to_json_boundaries(text)
        return text.strip()

    # ── JSON Extraction (multi-strategy) ─────────────────

    @staticmethod
    def _strategy_full_parse(text: str) -> dict | None:
        """Try parsing the entire cleaned string as JSON."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return None

    @staticmethod
    def _strategy_raw_decode_scan(text: str) -> list[dict]:
        """
        Scan the text for all valid JSON objects using
        JSONDecoder.raw_decode (handles concatenated blobs).
        """
        decoder = json.JSONDecoder()
        objects: list[dict] = []
        idx = 0
        while idx < len(text):
            brace = text.find("{", idx)
            if brace == -1:
                break
            try:
                obj, consumed = decoder.raw_decode(
                    text[brace:]
                )
                if isinstance(obj, dict):
                    objects.append(obj)
                idx = brace + consumed
            except json.JSONDecodeError:
                idx = brace + 1
        return objects

    @staticmethod
    def _strategy_parameter_blocks(
        text: str
    ) -> list[dict]:
        """
        Extract individual parameter dicts even when the
        parent wrapper is truncated. Looks for blocks that
        start with {"asset" or {"description".
        """
        params: list[dict] = []
        pattern = re.compile(
            r'\{\s*"(?:asset|description)"'
        )
        for match in pattern.finditer(text):
            start = match.start()
            depth = 0
            for i in range(start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        block = text[start : i + 1]
                        try:
                            parsed = json.loads(block)
                            if (
                                isinstance(parsed, dict)
                                and "description" in parsed
                            ):
                                params.append(parsed)
                        except json.JSONDecodeError:
                            pass
                        break
        return params

    @staticmethod
    def _strategy_fix_truncated(text: str) -> dict | None:
        """
        Attempt to close a truncated JSON array/object by
        trying common suffixes.
        """
        last_brace = text.rfind("}")
        if last_brace == -1:
            return None
        stub = text[: last_brace + 1]
        for suffix in ("", "]}", "}]}", "]}"):
            try:
                return json.loads(stub + suffix)
            except json.JSONDecodeError:
                continue
        return None

    @staticmethod
    def extract_json(raw_text: str) -> dict:
        """
        Try multiple strategies in order of reliability and
        return the first that yields a usable dict.

        Raises ValueError if all strategies fail.
        """
        cleaned = SchemaService.clean_json_response(
            raw_text
        )
        merged_params: list[dict] = []

        # ── Strategy 1: full parse ────────────────────────
        full = SchemaService._strategy_full_parse(cleaned)
        if full is not None:
            if (
                "parameters" in full
                and isinstance(full["parameters"], list)
            ):
                return full
            # If it's a single parameter object
            if "description" in full:
                return {"parameters": [full]}

        # ── Strategy 2: scan for all JSON objects ─────────
        objects = SchemaService._strategy_raw_decode_scan(
            cleaned
        )
        for obj in objects:
            if isinstance(
                obj.get("parameters"), list
            ):
                merged_params.extend(obj["parameters"])

        if merged_params:
            return {"parameters": merged_params}

        if objects:
            # Last object might be the full result
            last = objects[-1]
            if "description" in last:
                return {"parameters": [last]}
            return last

        # ── Strategy 3: individual parameter blocks ───────
        blocks = SchemaService._strategy_parameter_blocks(
            cleaned
        )
        if blocks:
            return {"parameters": blocks}

        # ── Strategy 4: fix truncated JSON ────────────────
        fixed = SchemaService._strategy_fix_truncated(
            cleaned
        )
        if fixed is not None:
            if isinstance(
                fixed.get("parameters"), list
            ):
                return fixed

        raise ValueError(
            f"All JSON parsing strategies failed.\n"
            f"Raw output (first 500 chars):\n"
            f"{raw_text[:500]}"
        )

    # ── Normalisation helpers ─────────────────────────────

    @staticmethod
    def _coerce_setpoints(param: dict) -> dict:
        """Ensure setpoints is always a plain dict."""
        sp = param.get("setpoints")
        if not isinstance(sp, dict):
            if isinstance(sp, list) and sp:
                param["setpoints"] = sp[0]
            else:
                param["setpoints"] = {}
        return param

    @staticmethod
    def _coerce_type(param: dict) -> dict:
        """Normalise the type field to one of the allowed values."""
        raw_type = str(
            param.get("type", "number")
        ).lower().strip()

        # Map common aliases
        type_map = {
            "numeric": "number",
            "float": "number",
            "integer": "number",
            "int": "number",
            "string": "text",
            "str": "text",
            "bool": "boolean",
        }
        param["type"] = type_map.get(
            raw_type,
            raw_type if raw_type in VALID_TYPES else "number"
        )
        return param

    @staticmethod
    def _deduplicate(
        params: list[dict]
    ) -> list[dict]:
        """
        Remove parameters with duplicate descriptions
        (case-insensitive) and skip any without a description.
        """
        seen: set[str] = set()
        unique: list[dict] = []
        for param in params:
            desc = str(
                param.get("description", "")
            ).strip()
            if not desc:
                continue
            key = desc.lower()
            if key not in seen:
                seen.add(key)
                param["description"] = desc
                unique.append(param)
        return unique

    # ── Public API ────────────────────────────────────────

    @staticmethod
    def normalize_schema(raw_text: str) -> dict:
        """
        Parse, clean, validate and return a normalized
        parameter schema dict.

        Raises ValueError on unrecoverable errors.
        """
        try:
            parsed = SchemaService.extract_json(raw_text)

            params = parsed.get("parameters")
            if not isinstance(params, list):
                raise ValueError(
                    "Parsed JSON is missing a "
                    "'parameters' list."
                )

            # Coerce each parameter
            coerced = [
                SchemaService._coerce_type(
                    SchemaService._coerce_setpoints(p)
                )
                for p in params
                if isinstance(p, dict)
            ]

            # Deduplicate
            deduped = SchemaService._deduplicate(coerced)

            if not deduped:
                raise ValueError(
                    "No valid parameters extracted from "
                    "the document."
                )

            # Pydantic validation
            validated = ParameterList(
                parameters=deduped
            )
            result = validated.model_dump()

            # Enforce business rule: asset is always empty
            for p in result["parameters"]:
                p["asset"] = ""

            logger.info(
                "Normalized schema: %d parameters",
                len(result["parameters"])
            )
            return result

        except ValidationError as err:
            raise ValueError(
                f"Schema validation failed: {err}"
            ) from err
        except ValueError:
            raise
        except Exception as err:
            raise ValueError(
                f"Unexpected error in schema "
                f"normalization: {err}"
            ) from err