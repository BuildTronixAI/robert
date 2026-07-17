"""
Buildtronix Pre-Con — Plan Distribution Engine
Phase 2: Replaces PlanHub

Handles:
- Drawing packages (collections of docs shared for a bid)
- Secure per-vendor share links (32-char token, no login required)
- Access logging (append-only, IP hashed)
- Expiry + revocation
"""

from __future__ import annotations
import hashlib
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class PackageStatus(str, Enum):
    DRAFT   = "draft"
    ACTIVE  = "active"
    EXPIRED = "expired"


class LinkStatus(str, Enum):
    ACTIVE  = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AccessAction(str, Enum):
    VIEW     = "view"
    DOWNLOAD = "download"


# ── Package Document Item ──────────────────────────────────────────────────────

@dataclass
class PackageDocument:
    item_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    package_id:   str = ""
    doc_id:       str = ""
    display_name: str = ""
    doc_version:  int = 1
    doc_hash:     str = ""
    sort_order:   int = 0
    added_at:     datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "item_id":     self.item_id,
            "doc_id":      self.doc_id,
            "display_name": self.display_name,
            "doc_version": self.doc_version,
            "doc_hash":    self.doc_hash,
            "sort_order":  self.sort_order,
        }


# ── Access Log Entry ──────────────────────────────────────────────────────────

@dataclass
class AccessLogEntry:
    log_id:      str = field(default_factory=lambda: str(uuid.uuid4()))
    link_id:     str = ""
    doc_id:      str = ""
    accessed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    action:      AccessAction = AccessAction.VIEW
    user_agent:  str = ""
    ip_hash:     str = ""  # SHA-256 of IP — never stored in plain text

    @staticmethod
    def hash_ip(ip: str) -> str:
        return hashlib.sha256(ip.encode()).hexdigest()

    def to_dict(self) -> dict:
        return {
            "log_id":      self.log_id,
            "link_id":     self.link_id,
            "doc_id":      self.doc_id,
            "accessed_at": self.accessed_at.isoformat(),
            "action":      self.action.value,
            "ip_hash":     self.ip_hash,
        }


# ── Vendor Share Link ──────────────────────────────────────────────────────────

@dataclass
class VendorShareLink:
    link_id:           str = field(default_factory=lambda: str(uuid.uuid4()))
    package_id:        str = ""
    vendor_id:         str = ""
    recipient_id:      str = ""
    token:             str = field(default_factory=lambda: secrets.token_urlsafe(24))
    created_at:        datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at:        Optional[datetime] = None
    first_accessed_at: Optional[datetime] = None
    last_accessed_at:  Optional[datetime] = None
    access_count:      int = 0
    status:            LinkStatus = LinkStatus.ACTIVE
    access_log:        list[AccessLogEntry] = field(default_factory=list)

    def is_valid(self) -> bool:
        if self.status != LinkStatus.ACTIVE:
            return False
        if self.expires_at and datetime.now(timezone.utc) > self.expires_at:
            self.status = LinkStatus.EXPIRED
            return False
        return True

    def record_access(self, doc_id: str, action: AccessAction,
                      user_agent: str = "", ip: str = "") -> AccessLogEntry:
        if not self.is_valid():
            raise PermissionError(f"Link is {self.status.value}")
        now = datetime.now(timezone.utc)
        entry = AccessLogEntry(
            link_id=self.link_id,
            doc_id=doc_id,
            action=action,
            user_agent=user_agent,
            ip_hash=AccessLogEntry.hash_ip(ip) if ip else "",
        )
        self.access_log.append(entry)
        self.access_count += 1
        self.last_accessed_at = now
        if not self.first_accessed_at:
            self.first_accessed_at = now
        return entry

    def revoke(self) -> None:
        self.status = LinkStatus.REVOKED

    def to_dict(self) -> dict:
        return {
            "link_id":           self.link_id,
            "package_id":        self.package_id,
            "vendor_id":         self.vendor_id,
            "recipient_id":      self.recipient_id,
            "token":             self.token,
            "expires_at":        self.expires_at.isoformat() if self.expires_at else None,
            "first_accessed_at": self.first_accessed_at.isoformat() if self.first_accessed_at else None,
            "last_accessed_at":  self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "access_count":      self.access_count,
            "status":            self.status.value,
        }


# ── Drawing Package ────────────────────────────────────────────────────────────

@dataclass
class DrawingPackage:
    """
    A collection of project documents shared with vendors for a bid.
    One package per project. Docs can be added without regenerating links.
    """
    package_id:  str = field(default_factory=lambda: str(uuid.uuid4()))
    project_id:  str = ""
    company_id:  str = ""
    name:        str = ""
    description: str = ""
    status:      PackageStatus = PackageStatus.DRAFT
    expires_at:  Optional[datetime] = None  # bid_due + 7 days
    created_by:  str = ""
    created_at:  datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    documents:  list[PackageDocument] = field(default_factory=list)
    links:      list[VendorShareLink] = field(default_factory=list)

    # ── Document Management ───────────────────────────────────────────────────

    def add_document(self, doc_id: str, display_name: str,
                     doc_version: int, doc_hash: str) -> PackageDocument:
        """Add or update a document in the package. Existing links see it immediately."""
        # Update if already present
        for item in self.documents:
            if item.doc_id == doc_id:
                item.display_name = display_name
                item.doc_version  = doc_version
                item.doc_hash     = doc_hash
                return item
        item = PackageDocument(
            package_id=self.package_id,
            doc_id=doc_id,
            display_name=display_name,
            doc_version=doc_version,
            doc_hash=doc_hash,
            sort_order=len(self.documents),
        )
        self.documents.append(item)
        return item

    def remove_document(self, doc_id: str) -> None:
        self.documents = [d for d in self.documents if d.doc_id != doc_id]

    def reorder(self, doc_ids: list[str]) -> None:
        """Reorder documents. doc_ids must contain all existing doc IDs."""
        order = {did: i for i, did in enumerate(doc_ids)}
        for item in self.documents:
            item.sort_order = order.get(item.doc_id, 99)
        self.documents.sort(key=lambda d: d.sort_order)

    # ── Link Management ───────────────────────────────────────────────────────

    def generate_link(self, vendor_id: str, recipient_id: str,
                      expire_days: int = 7) -> VendorShareLink:
        """Generate a secure share link for one vendor/recipient."""
        expires_at = None
        if self.expires_at:
            expires_at = self.expires_at + timedelta(days=expire_days)
        link = VendorShareLink(
            package_id=self.package_id,
            vendor_id=vendor_id,
            recipient_id=recipient_id,
            expires_at=expires_at,
        )
        self.links.append(link)
        self.status = PackageStatus.ACTIVE
        return link

    def generate_links_for_recipients(self, recipients: list[dict],
                                      expire_days: int = 7) -> list[VendorShareLink]:
        """Bulk generate links for all ITB recipients."""
        new_links = []
        existing_recipients = {l.recipient_id for l in self.links}
        for r in recipients:
            if r["recipient_id"] not in existing_recipients:
                link = self.generate_link(
                    vendor_id=r["vendor_id"],
                    recipient_id=r["recipient_id"],
                    expire_days=expire_days,
                )
                new_links.append(link)
        return new_links

    def get_link_by_token(self, token: str) -> Optional[VendorShareLink]:
        for link in self.links:
            if link.token == token:
                return link
        return None

    def revoke_link(self, link_id: str) -> VendorShareLink:
        for link in self.links:
            if link.link_id == link_id:
                link.revoke()
                return link
        raise KeyError(f"Link not found: {link_id}")

    # ── Access ────────────────────────────────────────────────────────────────

    def access_document(self, token: str, doc_id: str,
                        action: AccessAction = AccessAction.VIEW,
                        user_agent: str = "", ip: str = "") -> AccessLogEntry:
        """
        Vendor accesses a document via token. Returns access log entry.
        Raises PermissionError if link is invalid/expired/revoked.
        """
        link = self.get_link_by_token(token)
        if not link:
            raise PermissionError("Invalid share link")
        return link.record_access(doc_id, action, user_agent, ip)

    # ── Access Report ─────────────────────────────────────────────────────────

    def access_report(self) -> dict:
        """Estimator-facing access dashboard."""
        rows = []
        for link in self.links:
            rows.append({
                "link_id":           link.link_id,
                "vendor_id":         link.vendor_id,
                "recipient_id":      link.recipient_id,
                "status":            link.status.value,
                "access_count":      link.access_count,
                "first_accessed_at": link.first_accessed_at.isoformat() if link.first_accessed_at else None,
                "last_accessed_at":  link.last_accessed_at.isoformat() if link.last_accessed_at else None,
                "docs_accessed":     list({e.doc_id for e in link.access_log}),
                "downloads":         sum(1 for e in link.access_log if e.action == AccessAction.DOWNLOAD),
            })
        return {
            "package_id":    self.package_id,
            "project_id":    self.project_id,
            "document_count": len(self.documents),
            "link_count":    len(self.links),
            "active_links":  sum(1 for l in self.links if l.status == LinkStatus.ACTIVE),
            "total_accesses": sum(l.access_count for l in self.links),
            "vendors":       rows,
        }

    def to_dict(self) -> dict:
        return {
            "package_id":  self.package_id,
            "project_id":  self.project_id,
            "company_id":  self.company_id,
            "name":        self.name,
            "status":      self.status.value,
            "expires_at":  self.expires_at.isoformat() if self.expires_at else None,
            "documents":   [d.to_dict() for d in self.documents],
            "link_count":  len(self.links),
        }
