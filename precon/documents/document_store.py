"""
Buildtronix Pre-Con — Document Store
Phase 1: Shared document infrastructure

Handles:
- Document upload + SHA-256 hash computation
- Version tracking + supersession detection
- Addendum detection (hash match, filename match, manual)
"""

from __future__ import annotations
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class DocType(str, Enum):
    DRAWINGS  = "drawings"
    SPECS     = "specs"
    ADDENDUM  = "addendum"
    OTHER     = "other"


class DocStatus(str, Enum):
    ACTIVE     = "active"
    SUPERSEDED = "superseded"


class DetectionMethod(str, Enum):
    HASH_MATCH     = "hash_match"
    FILENAME_MATCH = "filename_match"
    MANUAL         = "manual"


@dataclass
class ProjectDocument:
    doc_id:        str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id:    str = ""
    company_id:    str = ""
    filename:      str = ""
    file_hash:     str = ""
    version:       int = 1
    superseded_by: Optional[str] = None
    uploaded_by:   str = ""
    uploaded_at:   datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    doc_type:      DocType = DocType.DRAWINGS
    status:        DocStatus = DocStatus.ACTIVE

    def supersede(self, new_doc_id: str) -> None:
        self.superseded_by = new_doc_id
        self.status = DocStatus.SUPERSEDED

    def to_dict(self) -> dict:
        return {
            "doc_id":        self.doc_id,
            "project_id":    self.project_id,
            "company_id":    self.company_id,
            "filename":      self.filename,
            "file_hash":     self.file_hash,
            "version":       self.version,
            "superseded_by": self.superseded_by,
            "uploaded_by":   self.uploaded_by,
            "uploaded_at":   self.uploaded_at.isoformat(),
            "doc_type":      self.doc_type.value,
            "status":        self.status.value,
        }


@dataclass
class AddendumDetection:
    """Result of addendum detection on a newly uploaded document."""
    is_addendum:       bool = False
    detection_method:  Optional[DetectionMethod] = None
    prior_doc_id:      Optional[str] = None
    prior_doc_version: int = 0
    confidence:        float = 0.0  # 0.0 - 1.0


class DocumentStore:
    """
    In-memory document store for a single project.
    Production: backed by Supabase project_documents table.
    """

    def __init__(self, project_id: str, company_id: str):
        self.project_id  = project_id
        self.company_id  = company_id
        self._docs: dict[str, ProjectDocument] = {}

    # ── Upload ────────────────────────────────────────────────────────────────

    @staticmethod
    def compute_hash(content: bytes) -> str:
        """SHA-256 hash of file content."""
        return hashlib.sha256(content).hexdigest()

    def upload(self, filename: str, content: bytes,
               uploaded_by: str, doc_type: DocType = DocType.DRAWINGS,
               manual_supersedes: Optional[str] = None) -> tuple[ProjectDocument, AddendumDetection]:
        """
        Upload a document. Returns (document, detection_result).
        Automatically checks for addendum against existing docs.
        """
        file_hash = self.compute_hash(content)

        # Detect addendum
        detection = self._detect_addendum(filename, file_hash, manual_supersedes)

        # Determine version
        version = 1
        if detection.is_addendum and detection.prior_doc_id:
            prior = self._docs[detection.prior_doc_id]
            version = prior.version + 1

        doc = ProjectDocument(
            project_id=self.project_id,
            company_id=self.company_id,
            filename=filename,
            file_hash=file_hash,
            version=version,
            uploaded_by=uploaded_by,
            doc_type=doc_type if not detection.is_addendum else DocType.ADDENDUM,
        )
        self._docs[doc.doc_id] = doc

        # Mark prior as superseded
        if detection.is_addendum and detection.prior_doc_id:
            self._docs[detection.prior_doc_id].supersede(doc.doc_id)

        return doc, detection

    def mark_superseded(self, prior_doc_id: str, new_doc_id: str) -> AddendumDetection:
        """Manual addendum designation."""
        if prior_doc_id not in self._docs:
            raise KeyError(f"Document not found: {prior_doc_id}")
        if new_doc_id not in self._docs:
            raise KeyError(f"Document not found: {new_doc_id}")
        prior = self._docs[prior_doc_id]
        new   = self._docs[new_doc_id]
        prior.supersede(new.doc_id)
        new.doc_type = DocType.ADDENDUM
        new.version  = prior.version + 1
        return AddendumDetection(
            is_addendum=True,
            detection_method=DetectionMethod.MANUAL,
            prior_doc_id=prior_doc_id,
            prior_doc_version=prior.version,
            confidence=1.0,
        )

    # ── Query ─────────────────────────────────────────────────────────────────

    def get(self, doc_id: str) -> ProjectDocument:
        if doc_id not in self._docs:
            raise KeyError(f"Document not found: {doc_id}")
        return self._docs[doc_id]

    def list_active(self) -> list[ProjectDocument]:
        return [d for d in self._docs.values() if d.status == DocStatus.ACTIVE]

    def list_all(self) -> list[ProjectDocument]:
        return list(self._docs.values())

    def get_version_history(self, filename_root: str) -> list[ProjectDocument]:
        """All versions of a document by filename root (base name without extension)."""
        root = filename_root.lower().rsplit('.', 1)[0]
        return sorted(
            [d for d in self._docs.values()
             if d.filename.lower().rsplit('.', 1)[0] == root],
            key=lambda d: d.version
        )

    # ── Addendum Detection ────────────────────────────────────────────────────

    def _detect_addendum(self, filename: str, file_hash: str,
                         manual_supersedes: Optional[str]) -> AddendumDetection:
        """
        Detection priority:
        1. Manual supersession (confidence: 1.0)
        2. Exact filename match on an active document (confidence: 0.9)
        3. Base filename match (ignoring revision suffixes) (confidence: 0.7)
        """
        # Manual override
        if manual_supersedes:
            if manual_supersedes in self._docs:
                prior = self._docs[manual_supersedes]
                return AddendumDetection(
                    is_addendum=True,
                    detection_method=DetectionMethod.MANUAL,
                    prior_doc_id=manual_supersedes,
                    prior_doc_version=prior.version,
                    confidence=1.0,
                )

        active_docs = [d for d in self._docs.values() if d.status == DocStatus.ACTIVE]

        # Exact filename match
        for doc in active_docs:
            if doc.filename.lower() == filename.lower() and doc.file_hash != file_hash:
                return AddendumDetection(
                    is_addendum=True,
                    detection_method=DetectionMethod.FILENAME_MATCH,
                    prior_doc_id=doc.doc_id,
                    prior_doc_version=doc.version,
                    confidence=0.9,
                )

        # Base filename match (strip revision markers like _rev1, _A3, -v2)
        import re
        base = re.sub(r'[-_](rev|r|v|a|add|addendum)?[\d]+$', '',
                      filename.lower().rsplit('.', 1)[0], flags=re.IGNORECASE)
        for doc in active_docs:
            doc_base = re.sub(r'[-_](rev|r|v|a|add|addendum)?[\d]+$', '',
                              doc.filename.lower().rsplit('.', 1)[0], flags=re.IGNORECASE)
            if doc_base == base and doc.file_hash != file_hash:
                return AddendumDetection(
                    is_addendum=True,
                    detection_method=DetectionMethod.FILENAME_MATCH,
                    prior_doc_id=doc.doc_id,
                    prior_doc_version=doc.version,
                    confidence=0.7,
                )

        return AddendumDetection(is_addendum=False)
