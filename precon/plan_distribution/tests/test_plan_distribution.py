"""Plan Distribution Engine Tests — Phase 2"""
import pytest, sys, os
sys.path.insert(0, os.path.abspath('../../..'))
from precon.plan_distribution.plan_distribution import (
    DrawingPackage, PackageStatus, LinkStatus, AccessAction
)

def pkg():
    p = DrawingPackage(project_id="proj-001", company_id="trias-construction",
                       name="Langley Pharmacy Drawings", created_by="user-001")
    return p

# ── Package Structure ─────────────────────────────────────────────────────────
def test_create_package():
    p = pkg()
    assert p.status == PackageStatus.DRAFT
    assert len(p.documents) == 0
    assert len(p.links) == 0

def test_add_document():
    p = pkg()
    item = p.add_document("doc-001", "Electrical Drawings", 1, "abc123")
    assert item.doc_id == "doc-001"
    assert len(p.documents) == 1

def test_add_multiple_documents():
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    p.add_document("doc-002", "Plumbing", 1, "hash2")
    p.add_document("doc-003", "Architectural", 1, "hash3")
    assert len(p.documents) == 3

def test_update_existing_document():
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    p.add_document("doc-001", "Electrical - Revised", 2, "hash2")
    assert len(p.documents) == 1
    assert p.documents[0].doc_version == 2
    assert p.documents[0].display_name == "Electrical - Revised"

def test_remove_document():
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    p.add_document("doc-002", "Plumbing", 1, "hash2")
    p.remove_document("doc-001")
    assert len(p.documents) == 1
    assert p.documents[0].doc_id == "doc-002"

def test_reorder_documents():
    p = pkg()
    p.add_document("doc-001", "C", 1, "h1")
    p.add_document("doc-002", "A", 1, "h2")
    p.add_document("doc-003", "B", 1, "h3")
    p.reorder(["doc-002", "doc-003", "doc-001"])
    assert p.documents[0].doc_id == "doc-002"
    assert p.documents[1].doc_id == "doc-003"
    assert p.documents[2].doc_id == "doc-001"

# ── Link Generation ───────────────────────────────────────────────────────────
def test_generate_link():
    p = pkg()
    link = p.generate_link("vendor-001", "recipient-001")
    assert link.status == LinkStatus.ACTIVE
    assert len(link.token) > 20
    assert link.vendor_id == "vendor-001"
    assert p.status == PackageStatus.ACTIVE

def test_tokens_are_unique():
    p = pkg()
    tokens = {p.generate_link("v-001", f"r-{i}").token for i in range(20)}
    assert len(tokens) == 20

def test_bulk_generate_links():
    p = pkg()
    recipients = [
        {"vendor_id": f"v-{i}", "recipient_id": f"r-{i}"} for i in range(5)
    ]
    links = p.generate_links_for_recipients(recipients)
    assert len(links) == 5
    assert len(p.links) == 5

def test_bulk_generate_skips_existing():
    p = pkg()
    p.generate_link("v-001", "r-001")
    recipients = [
        {"vendor_id": "v-001", "recipient_id": "r-001"},
        {"vendor_id": "v-002", "recipient_id": "r-002"},
    ]
    new_links = p.generate_links_for_recipients(recipients)
    assert len(new_links) == 1
    assert len(p.links) == 2

def test_get_link_by_token():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    found = p.get_link_by_token(link.token)
    assert found.link_id == link.link_id

def test_get_link_invalid_token():
    p = pkg()
    assert p.get_link_by_token("invalid-token-xyz") is None

# ── Access ────────────────────────────────────────────────────────────────────
def test_access_document_via_token():
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    link = p.generate_link("v-001", "r-001")
    entry = p.access_document(link.token, "doc-001", AccessAction.VIEW,
                               user_agent="Mozilla/5.0", ip="1.2.3.4")
    assert entry.action == AccessAction.VIEW
    assert entry.doc_id == "doc-001"
    assert link.access_count == 1
    assert link.first_accessed_at is not None

def test_access_logs_ip_hash_not_plain():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    entry = p.access_document(link.token, "doc-001", ip="192.168.1.1")
    assert entry.ip_hash != "192.168.1.1"
    assert len(entry.ip_hash) == 64  # SHA-256

def test_access_count_increments():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    for _ in range(5):
        p.access_document(link.token, "doc-001")
    assert link.access_count == 5

def test_download_logged_separately():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    p.access_document(link.token, "doc-001", AccessAction.VIEW)
    p.access_document(link.token, "doc-001", AccessAction.DOWNLOAD)
    downloads = sum(1 for e in link.access_log if e.action == AccessAction.DOWNLOAD)
    assert downloads == 1

def test_invalid_token_raises():
    p = pkg()
    with pytest.raises(PermissionError, match="Invalid"):
        p.access_document("bad-token-xyz", "doc-001")

# ── Revocation ────────────────────────────────────────────────────────────────
def test_revoke_link():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    p.revoke_link(link.link_id)
    assert link.status == LinkStatus.REVOKED

def test_revoked_link_blocks_access():
    p = pkg()
    link = p.generate_link("v-001", "r-001")
    p.revoke_link(link.link_id)
    with pytest.raises(PermissionError):
        p.access_document(link.token, "doc-001")

def test_revoke_nonexistent_link():
    p = pkg()
    with pytest.raises(KeyError):
        p.revoke_link("nonexistent-link-id")

# ── Access Report ─────────────────────────────────────────────────────────────
def test_access_report_structure():
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    link = p.generate_link("v-001", "r-001")
    p.access_document(link.token, "doc-001", AccessAction.VIEW)
    p.access_document(link.token, "doc-001", AccessAction.DOWNLOAD)
    report = p.access_report()
    assert report["package_id"] == p.package_id
    assert report["total_accesses"] == 2
    assert len(report["vendors"]) == 1
    vendor_row = report["vendors"][0]
    assert vendor_row["downloads"] == 1
    assert "doc-001" in vendor_row["docs_accessed"]

def test_access_report_active_links():
    p = pkg()
    p.generate_link("v-001", "r-001")
    link2 = p.generate_link("v-002", "r-002")
    p.revoke_link(link2.link_id)
    report = p.access_report()
    assert report["active_links"] == 1

# ── Addendum Integration ──────────────────────────────────────────────────────
def test_new_doc_immediately_visible():
    """Adding a new doc to package doesn't require link regeneration."""
    p = pkg()
    p.add_document("doc-001", "Electrical", 1, "hash1")
    link = p.generate_link("v-001", "r-001")
    # New addendum added
    p.add_document("doc-002", "Electrical - Addendum A", 2, "hash2")
    # Vendor can access new doc via existing link
    entry = p.access_document(link.token, "doc-002")
    assert entry.doc_id == "doc-002"

if __name__ == "__main__":
    import subprocess
    subprocess.run(["python3", "-m", "pytest", __file__, "-v", "--tb=short"])
