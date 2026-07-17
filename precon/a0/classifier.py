"""
A-0 Document Classifier
Classifies documents by content (not folder path).
Folder hint is passed in but treated as a signal only — never authoritative.

Classification states:
  PENDING_CLASSIFICATION  → ingested, not yet classified
  CLASSIFIED              → confident classification
  LOW_CONFIDENCE          → below threshold, needs review
  CLASSIFIER_FAILED       → retries exhausted → DLQ
  SUPERSEDED              → replaced by newer version
"""
import hashlib
import json
import time
import logging
from typing import Optional, Tuple
from enum import Enum

import httpx
from config import (
    OPENAI_API_KEY, CLASSIFIER_MODEL,
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    CLASSIFIER_RETRY_ATTEMPTS, CLASSIFIER_RETRY_BACKOFF_S,
    DOCUMENT_TYPES,
)

logger = logging.getLogger("a0.classifier")


class ClassificationStatus(str, Enum):
    PENDING           = "PENDING_CLASSIFICATION"
    CLASSIFIED        = "CLASSIFIED"
    LOW_CONFIDENCE    = "LOW_CONFIDENCE"
    FAILED            = "CLASSIFIER_FAILED"
    DLQ               = "DLQ"
    SUPERSEDED        = "SUPERSEDED"
    DELETED_OR_MISSING = "DELETED_OR_MISSING"


CLASSIFIER_PROMPT = """You are a construction document classifier for a preconstruction estimating system.

Given the following information about a file, classify it into exactly one document type.

Document types:
- PLANS: Architectural, mechanical, electrical, plumbing, structural drawings
- SPECS: Project specifications, project manual, technical requirements
- ADDENDA: Addenda, ASIs, clarifications that modify bid documents
- RFI: Requests for Information and their responses
- BID_FORM: Bid forms, bid proposal forms, pricing forms from GC/owner
- VENDOR_QUOTE: Quotes, proposals, pricing from subcontractors/vendors
- ESTIMATE: Internal cost estimates, cost recaps, takeoff sheets
- ARCHIVE: Archived or superseded documents
- UNKNOWN: Cannot determine type from available information

File information:
- File name: {file_name}
- Folder path hint: {folder_hint} (this is a hint only, not authoritative)
- File extension: {extension}
- File size (bytes): {byte_size}
- Content sample (first 500 chars if text): {content_sample}

Respond with JSON only:
{{
  "document_type": "<TYPE>",
  "confidence": <0.0-1.0>,
  "reasoning": "<one sentence>",
  "authority_tier": <0-5>
}}

Authority tiers: 5=Addenda (highest), 4=Bid Form, 3=RFI, 2=Specs, 1=Plans, 0=Other"""


def _prompt_hash(file_name: str, folder_hint: str) -> str:
    """Deterministic hash of the classification prompt template + inputs."""
    h = hashlib.sha256(
        f"{CLASSIFIER_PROMPT}|{file_name}|{folder_hint}".encode()
    ).hexdigest()
    return h


def _result_hash(result: dict) -> str:
    return hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()


class DocumentClassifier:
    """
    Classifies documents by content.
    Failure-safe: returns PENDING status on network/API errors.
    Never drops a document from the registry.
    """

    def __init__(self):
        self._client = httpx.Client(
            base_url="https://api.openai.com",
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            timeout=30,
        )

    def classify(
        self,
        file_name:      str,
        folder_hint:    str,
        extension:      str,
        byte_size:      int,
        content_sample: str = "",
    ) -> Tuple[ClassificationStatus, dict]:
        """
        Returns (status, result_dict).
        result_dict keys: document_type, confidence, reasoning, authority_tier,
                          prompt_hash, result_hash, classifier_version, attempts
        Never raises — failures return CLASSIFIER_FAILED status.
        """
        prompt_h = _prompt_hash(file_name, folder_hint)
        last_error = None

        for attempt in range(1, CLASSIFIER_RETRY_ATTEMPTS + 1):
            try:
                r = self._client.post(
                    "/v1/chat/completions",
                    json={
                        "model": CLASSIFIER_MODEL,
                        "messages": [
                            {
                                "role": "user",
                                "content": CLASSIFIER_PROMPT.format(
                                    file_name=file_name,
                                    folder_hint=folder_hint,
                                    extension=extension,
                                    byte_size=byte_size,
                                    content_sample=content_sample[:500],
                                ),
                            }
                        ],
                        "response_format": {"type": "json_object"},
                        "temperature": 0.0,
                    },
                )
                r.raise_for_status()
                raw = r.json()["choices"][0]["message"]["content"]
                parsed = json.loads(raw)

                doc_type   = parsed.get("document_type", "UNKNOWN").upper()
                confidence = float(parsed.get("confidence", 0.0))
                reasoning  = parsed.get("reasoning", "")
                auth_tier  = int(parsed.get("authority_tier", 0))

                # Validate type
                if doc_type not in DOCUMENT_TYPES:
                    doc_type = "UNKNOWN"
                    confidence = 0.0

                result = {
                    "document_type":  doc_type,
                    "confidence":     confidence,
                    "reasoning":      reasoning,
                    "authority_tier": auth_tier,
                    "prompt_hash":    prompt_h,
                    "result_hash":    _result_hash(parsed),
                    "classifier_version": CLASSIFIER_MODEL,
                    "attempts":       attempt,
                }

                if confidence < CLASSIFIER_CONFIDENCE_THRESHOLD:
                    logger.warning(
                        f"Low confidence {confidence:.2f} for {file_name} → {doc_type}"
                    )
                    return ClassificationStatus.LOW_CONFIDENCE, result

                return ClassificationStatus.CLASSIFIED, result

            except Exception as e:
                last_error = str(e)
                logger.warning(f"Classifier attempt {attempt}/{CLASSIFIER_RETRY_ATTEMPTS} failed: {e}")
                if attempt < CLASSIFIER_RETRY_ATTEMPTS:
                    time.sleep(CLASSIFIER_RETRY_BACKOFF_S * attempt)

        # All retries exhausted
        logger.error(f"Classifier failed for {file_name} after {CLASSIFIER_RETRY_ATTEMPTS} attempts: {last_error}")
        return ClassificationStatus.FAILED, {
            "document_type":  "UNKNOWN",
            "confidence":     0.0,
            "reasoning":      f"Classifier failed: {last_error}",
            "authority_tier": 0,
            "prompt_hash":    prompt_h,
            "result_hash":    "",
            "classifier_version": CLASSIFIER_MODEL,
            "attempts":       CLASSIFIER_RETRY_ATTEMPTS,
        }


def get_folder_hint(path: str) -> str:
    """Extract folder hint from path — lowercase, space-normalized."""
    from config import FOLDER_HINT_MAP
    path_lower = path.lower().replace("\\", "/").replace("_", " ").replace("-", " ")
    parts = path_lower.split("/")
    for part in reversed(parts[:-1]):  # walk folders from closest
        for keyword, hint_type in FOLDER_HINT_MAP.items():
            if keyword in part:
                return hint_type
    return "UNKNOWN"


def resolve_final_type(
    folder_hint: str,
    content_type: str,
    content_confidence: float,
    authority_tier_map: dict[str, int] | None = None,
) -> Tuple[str, bool]:
    """
    Resolves final_document_type per A-0 mismatch rules.
    Returns (final_type, classification_mismatch).

    Fails UP the authority hierarchy when content says higher-authority type.
    """
    if authority_tier_map is None:
        authority_tier_map = {
            "ADDENDA": 5, "BID_FORM": 4, "RFI": 3,
            "SPECS": 2, "PLANS": 1,
            "VENDOR_QUOTE": 0, "ESTIMATE": 0, "ARCHIVE": 0, "UNKNOWN": 0,
        }

    if folder_hint == content_type:
        return content_type, False

    folder_tier  = authority_tier_map.get(folder_hint, 0)
    content_tier = authority_tier_map.get(content_type, 0)

    if content_tier > folder_tier:
        # Content says higher authority — fail up, pending review
        pending_map = {
            "ADDENDA":   "ADDENDUM_PENDING_REVIEW",
            "RFI":       "RFI_PENDING_REVIEW",
            "BID_FORM":  "BID_FORM_PENDING_REVIEW",
            "PLANS":     "DRAWING_PENDING_REVIEW",
        }
        pending_type = pending_map.get(content_type, content_type + "_PENDING_REVIEW")
        return pending_type, True
    else:
        # Folder says higher — still pending review (downgrade needs proof)
        pending_map = {
            "ADDENDA":   "ADDENDUM_PENDING_REVIEW",
            "RFI":       "RFI_PENDING_REVIEW",
            "BID_FORM":  "BID_FORM_PENDING_REVIEW",
        }
        if folder_hint in pending_map:
            return pending_map[folder_hint], True
        # Lower folder authority, lower content — use content
        return content_type, False
