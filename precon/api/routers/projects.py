"""
PRECON API — Project routes
GET  /projects/{project_id}/review-state
GET  /projects/{project_id}/bid-confidence
"""
from fastapi import APIRouter, HTTPException
from precon.api.models import ProjectReviewStateOut, BidConfidenceOut, VectorScoreOut
from precon.api.store import get_or_create_store

router = APIRouter(prefix="/projects/{project_id}", tags=["project"])


def _vector_out(v) -> VectorScoreOut:
    return VectorScoreOut(
        name=v.name, raw_score=v.raw_score, weight=v.weight,
        weighted_score=v.weighted_score, components=v.components, notes=v.notes,
    )


def _bid_confidence_out(score) -> BidConfidenceOut:
    return BidConfidenceOut(
        project_id=score.project_id,
        composite_score=score.composite_score,
        confidence_tier=score.confidence_tier,
        coverage_vector=_vector_out(score.coverage_vector),
        quantity_vector=_vector_out(score.quantity_vector),
        review_integrity_vector=_vector_out(score.review_integrity_vector),
        pricing_vector=_vector_out(score.pricing_vector),
        profile_used=score.profile_used,
        weights_used=score.weights_used,
        submittable=score.submittable,
        submission_threshold=score.submission_threshold,
    )


@router.get("/review-state", response_model=ProjectReviewStateOut)
def get_review_state(project_id: str):
    store = get_or_create_store(project_id)
    rs = store.review_state
    return ProjectReviewStateOut(
        project_id=rs.project_id,
        screen1=rs.screen_1, screen2=rs.screen_2,
        screen25=rs.screen_2_5, screen3=rs.screen_3,
        engine2b_run=rs.engine_2b_run, a10_complete=rs.a10_complete,
        proposal_ready=rs.proposal_ready,
        screen1_total=rs.screen_1_total, screen1_decided=rs.screen_1_decided,
        screen2_total=rs.screen_2_total, screen2_decided=rs.screen_2_decided,
        screen25_blocking_total=rs.screen_2_5_blocking_total,
        screen25_blocking_resolved=rs.screen_2_5_blocking_resolved,
        screen3_total=rs.screen_3_total, screen3_decided=rs.screen_3_decided,
        session_batch_approved_count=rs.session_batch_approved_count,
        session_batch_ceiling=rs.session_batch_ceiling,
        updated_at=rs.updated_at,
    )


@router.get("/bid-confidence", response_model=BidConfidenceOut)
def get_bid_confidence(project_id: str):
    store = get_or_create_store(project_id)
    return _bid_confidence_out(store.compute_bid_confidence())
