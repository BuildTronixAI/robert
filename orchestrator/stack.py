"""
orchestrator/stack.py — Witness + Little Voice integration
Runs both monitors concurrently before Robert acts.
Returns combined flag context to inject into task processing.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import logging

logger = logging.getLogger(__name__)

ORCHESTRATOR_TIMEOUT = 5  # seconds max wait for both monitors


def run_orchestrator_stack(text: str, identity_profile: dict, context: str = "") -> dict:
    """
    Run Witness + Little Voice concurrently.
    Returns combined result dict with flags, blocks, and recommended_action.
    Max wait: 5 seconds. Fail-open on timeout or error.

    source_type enforcement:
    - Only structured_external or structured_memory flags can trigger HUMAN_APPROVAL_REQUIRED
    - watcher_inference flags are logged only, never gate
    """
    results = {
        "witness": None,
        "little_voice": None,
        "combined_flags": [],
        "should_block": False,
        "block_reason": "",
        "error": None
    }

    try:
        from orchestrator.witness import run_witness
        from orchestrator.little_voice import run_little_voice
    except ImportError as e:
        logger.warning(f"[orchestrator] Import failed — fail-open: {e}")
        results["error"] = str(e)
        return results

    executor = ThreadPoolExecutor(max_workers=2)
    try:
        futures = {
            executor.submit(run_witness, text, context): "witness",
            executor.submit(run_little_voice, text, identity_profile, context): "little_voice"
        }
        try:
            for future in as_completed(futures, timeout=ORCHESTRATOR_TIMEOUT):
                key = futures[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    logger.warning(f"[orchestrator] {key} error — fail-open: {e}")
                    results[key] = {"flags": [], "error": str(e)}
        except FuturesTimeoutError:
            logger.warning(f"[orchestrator] Timeout after {ORCHESTRATOR_TIMEOUT}s — fail-open")
            results["error"] = "timeout"
            for future in futures:
                future.cancel()
    finally:
        # Do not wait forever for stuck monitors — bound orchestrator wall time.
        executor.shutdown(wait=False, cancel_futures=True)

    # Aggregate flags
    witness_flags = (results.get("witness") or {}).get("flags", [])
    lv_flags = (results.get("little_voice") or {}).get("flags", [])
    all_flags = witness_flags + lv_flags
    results["combined_flags"] = all_flags

    # Hard block check — ONLY structured_external or structured_memory can gate
    blocks = [
        f for f in all_flags
        if f.get("severity") == "HUMAN_APPROVAL_REQUIRED"
        and f.get("source_type") in ("structured_external", "structured_memory")
    ]
    if blocks:
        results["should_block"] = True
        results["block_reason"] = blocks[0].get("evidence", "Human approval required before proceeding.")

    # Log summary
    if all_flags:
        flag_summary = [(f.get("trigger"), f.get("severity"), f.get("source_type")) for f in all_flags]
        logger.info(f"[orchestrator] {len(all_flags)} flags: {flag_summary}")

    return results
