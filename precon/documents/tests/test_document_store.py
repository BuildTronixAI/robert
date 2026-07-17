"""Document Store Tests — Phase 1"""
import pytest, sys, os
sys.path.insert(0, os.path.abspath('../../..'))
from precon.documents.document_store import DocumentStore, DocType, DocStatus, DetectionMethod

PROJ = "proj-001"
CO   = "trias-construction"

def store():
    return DocumentStore(PROJ, CO)

def make_content(text: str) -> bytes:
    return text.encode()

# ── Hash ──────────────────────────────────────────────────────────────────────

def test_hash_is_sha256():
    h = DocumentStore.compute_hash(b"hello")
    assert len(h) == 64
    assert all(c in "0123456789abcdef" for c in h)

def test_same_content_same_hash():
    h1 = DocumentStore.compute_hash(b"test content")
    h2 = DocumentStore.compute_hash(b"test content")
    assert h1 == h2

def test_different_content_different_hash():
    h1 = DocumentStore.compute_hash(b"v1 content")
    h2 = DocumentStore.compute_hash(b"v2 content")
    assert h1 != h2

# ── Upload ────────────────────────────────────────────────────────────────────

def test_upload_creates_document():
    s = store()
    doc, det = s.upload("drawings_A1.pdf", make_content("v1"), "user-001")
    assert doc.project_id == PROJ
    assert doc.company_id == CO
    assert doc.filename == "drawings_A1.pdf"
    assert doc.version == 1
    assert doc.status == DocStatus.ACTIVE
    assert not det.is_addendum

def test_upload_computes_hash():
    s = store()
    content = b"test file content"
    doc, _ = s.upload("test.pdf", content, "user-001")
    assert doc.file_hash == DocumentStore.compute_hash(content)

def test_upload_detects_exact_filename_addendum():
    s = store()
    doc1, _ = s.upload("electrical.pdf", make_content("v1"), "user-001")
    doc2, det = s.upload("electrical.pdf", make_content("v2 — changed"), "user-001")
    assert det.is_addendum
    assert det.detection_method == DetectionMethod.FILENAME_MATCH
    assert det.prior_doc_id == doc1.doc_id
    assert det.prior_doc_version == 1
    assert det.confidence == 0.9

def test_addendum_supersedes_prior():
    s = store()
    doc1, _ = s.upload("electrical.pdf", make_content("v1"), "user-001")
    doc2, _ = s.upload("electrical.pdf", make_content("v2"), "user-001")
    assert s.get(doc1.doc_id).status == DocStatus.SUPERSEDED
    assert s.get(doc1.doc_id).superseded_by == doc2.doc_id
    assert doc2.status == DocStatus.ACTIVE

def test_addendum_increments_version():
    s = store()
    doc1, _ = s.upload("spec.pdf", make_content("v1"), "user-001")
    doc2, _ = s.upload("spec.pdf", make_content("v2"), "user-001")
    assert doc2.version == 2

def test_addendum_sets_doc_type():
    s = store()
    s.upload("spec.pdf", make_content("v1"), "user-001")
    doc2, _ = s.upload("spec.pdf", make_content("v2"), "user-001")
    assert doc2.doc_type == DocType.ADDENDUM

def test_same_content_not_addendum():
    s = store()
    content = make_content("same content")
    s.upload("spec.pdf", content, "user-001")
    _, det = s.upload("spec.pdf", content, "user-001")
    assert not det.is_addendum

def test_base_filename_match_detection():
    s = store()
    doc1, _ = s.upload("electrical_v1.pdf", make_content("original"), "user-001")
    _, det = s.upload("electrical_v2.pdf", make_content("revised"), "user-001")
    assert det.is_addendum
    assert det.prior_doc_id == doc1.doc_id
    assert det.confidence == 0.7

def test_manual_supersede():
    s = store()
    doc1, _ = s.upload("drawings.pdf", make_content("original"), "user-001")
    doc2, _ = s.upload("drawings_addendum_A.pdf", make_content("new version"), "user-001")
    det = s.mark_superseded(doc1.doc_id, doc2.doc_id)
    assert det.is_addendum
    assert det.detection_method == DetectionMethod.MANUAL
    assert det.confidence == 1.0
    assert s.get(doc1.doc_id).status == DocStatus.SUPERSEDED

# ── Query ─────────────────────────────────────────────────────────────────────

def test_list_active_excludes_superseded():
    s = store()
    doc1, _ = s.upload("elec.pdf", make_content("v1"), "user-001")
    doc2, _ = s.upload("elec.pdf", make_content("v2"), "user-001")
    active = s.list_active()
    assert doc2 in active
    assert doc1 not in active

def test_list_all_includes_superseded():
    s = store()
    s.upload("elec.pdf", make_content("v1"), "user-001")
    s.upload("elec.pdf", make_content("v2"), "user-001")
    assert len(s.list_all()) == 2

def test_get_version_history():
    s = store()
    s.upload("arch.pdf", make_content("v1"), "user-001")
    s.upload("arch.pdf", make_content("v2"), "user-001")
    s.upload("arch.pdf", make_content("v3"), "user-001")
    history = s.get_version_history("arch.pdf")
    assert len(history) == 3
    assert [d.version for d in history] == [1, 2, 3]

def test_multiple_independent_docs():
    s = store()
    s.upload("electrical.pdf", make_content("elec v1"), "user-001")
    s.upload("plumbing.pdf", make_content("plumb v1"), "user-001")
    s.upload("electrical.pdf", make_content("elec v2"), "user-001")
    active = s.list_active()
    assert len(active) == 2  # latest electrical + plumbing
    names = {d.filename for d in active}
    assert "plumbing.pdf" in names

if __name__ == "__main__":
    import subprocess
    subprocess.run(["python3", "-m", "pytest", __file__, "-v", "--tb=short"])
