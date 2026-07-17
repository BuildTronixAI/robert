"""
LITTLE VOICE v1.1 — Inner Conscience / Strategic-Risk Evaluator for Robert
Asks: "Should I be doing this at all?"

Watches the intent and consequence of actions and flags appropriateness issues.
Returns flags with source_type field:
  - structured_external: timing check (clock is external), actual threshold check with real data
  - structured_memory: sensitive entity flag in subject memory, prior rejection marker
  - watcher_inference: consequence inference, strategic assessment without external data

CRITICAL: Only structured_external or structured_memory can trigger BLOCKING_REVIEW_REQUIRED
or HUMAN_APPROVAL_REQUIRED. watcher_inference is log-only.

Special rule:
- Timing check (0-6 UTC) + irreversible action = structured_external (clock is external source)
- Financial threshold check = structured_external ONLY if actual amount in context AND exceeds threshold
- Otherwise = watcher_inference
"""

import json
import logging
import logging.handlers
import os
import sys
import time
import datetime
from typing import List, Dict, Any, Optional
import anthropic


# ── Setup Logging ──────────────────────────────────────────────────
try:
    os.makedirs("/var/log/robert", exist_ok=True)
    _handler = logging.handlers.RotatingFileHandler(
        "/var/log/robert/little_voice.log",
        maxBytes=5*1024*1024,
        backupCount=5
    )
    _handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    _lv_logger = logging.getLogger("little_voice")
    _lv_logger.setLevel(logging.INFO)
    _lv_logger.addHandler(_handler)
    _lv_logger.propagate = False
except Exception as e:
    _lv_logger = None
    print(f"[LittleVoice] Failed to setup logging: {e}", file=sys.stderr)


def _log(msg: str):
    """Log to little_voice.log (JSON lines) + stderr."""
    if _lv_logger:
        _lv_logger.info(msg)
    print(f"[LittleVoice] {msg}", file=sys.stderr)


class LittleVoice:
    """
    Strategic-risk evaluator module. Watches for consequences and appropriateness of actions.
    
    API:
        check(action: str, context: dict, timing: str = None) -> list[dict]
        Returns flags or empty list.
        
    Flag schema v1.1:
    {
        "type": "little_voice",
        "severity": "INFO|CAUTION|BLOCKING_REVIEW_REQUIRED|HUMAN_APPROVAL_REQUIRED",
        "confidence": "low|medium|high",
        "evidence": "what was found",
        "source_type": "structured_external|structured_memory|watcher_inference",
        "trigger": "1-8 enumerated item",
        "recommended_action": "log|escalate|block|human_gate"
    }
    """
    
    def __init__(self, timeout_sec: int = 5):
        self.timeout_sec = timeout_sec
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not self.api_key:
            _log("WARNING: ANTHROPIC_API_KEY not set. LittleVoice will fail-open on all checks.")
        
        # Chris's known sensitive relationships and stressed periods (loaded from context)
        self.sensitive_people = set()
        self.stressed_periods = []
    
    def check(
        self,
        action: str,
        context: Dict[str, Any],
        timing: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Check action for appropriateness and consequence.
        
        Args:
            action: Description of the action being considered
                Example: "send email to finance@client.com with budget proposal"
            context: Dict with context about action
                Expected keys: 'is_external', 'is_irreversible', 'involves_money',
                              'people_involved', 'chris_values', 'chris_priorities',
                              'memory_entries', 'financial_amount', 'threshold', etc.
            timing: Optional timing string, e.g., "03:45 UTC"
        
        Returns:
            List of flags with v1.1 schema (includes source_type)
            Empty list if clean.
        """
        if not self.api_key:
            _log("WARN: No API key. Failing open (returning []).")
            return []
        
        try:
            # Pre-check: timing rule
            timing_flags = self._check_timing(action, context, timing)
            
            # Pre-check: financial threshold rule
            threshold_flags = self._check_financial_threshold(action, context)
            
            # Main check via Haiku
            haiku_flags = self._check_via_haiku(action, context, timing)
            
            # Aggregate
            all_flags = timing_flags + threshold_flags + haiku_flags
            
            if all_flags:
                _log(json.dumps({
                    "type": "little_voice",
                    "flags": all_flags,
                    "timestamp": context.get("timestamp", time.time()),
                    "action": action[:100]
                }))
            
            return all_flags
        
        except Exception as e:
            _log(f"ERROR in little_voice check (fail-open): {e}")
            return []
    
    def _check_timing(
        self,
        action: str,
        context: Dict[str, Any],
        timing: Optional[str]
    ) -> List[Dict[str, Any]]:
        """
        Timing rule: if hour is 0-6 UTC and action is external/irreversible → structured_external flag.
        """
        flags = []
        
        if not timing:
            # Try to extract from context
            ts = context.get("timestamp")
            if ts:
                dt = datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
                hour = dt.hour
            else:
                hour = datetime.datetime.now(datetime.timezone.utc).hour
        else:
            # Parse timing string "HH:MM UTC"
            try:
                parts = timing.split(":")
                hour = int(parts[0])
            except (ValueError, IndexError):
                hour = -1
        
        # Check if late night (0-6 UTC) AND action is external/irreversible
        if 0 <= hour <= 6:
            is_external = context.get("is_external", False)
            is_irreversible = context.get("is_irreversible", False)
            
            if is_external or is_irreversible:
                flags.append({
                    "type": "little_voice",
                    "severity": "BLOCKING_REVIEW_REQUIRED" if is_irreversible else "CAUTION",
                    "confidence": "high",
                    "trigger": 4,  # High-stakes timing
                    "evidence": f"Late-night action at {hour}:XX UTC",
                    "source_type": "structured_external",  # Clock is external source
                    "recommended_action": "escalate" if is_irreversible else "log",
                    "message": f"Late-night action ({hour}:XX UTC): {'irreversible' if is_irreversible else 'external'} action at unusual hour. Verify Chris is aware."
                })
        
        return flags
    
    def _check_financial_threshold(
        self,
        action: str,
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Financial threshold rule: if actual amount in context AND exceeds threshold → structured_external flag.
        Otherwise not flagged here (delegated to haiku_flags).
        """
        flags = []
        
        financial_amount = context.get("financial_amount")
        threshold = context.get("financial_threshold")
        
        if financial_amount is not None and threshold is not None:
            try:
                amount = float(financial_amount)
                thresh = float(threshold)
                
                if amount >= thresh:
                    flags.append({
                        "type": "little_voice",
                        "severity": "HUMAN_APPROVAL_REQUIRED",
                        "confidence": "high",
                        "trigger": 2,  # Financial commitment
                        "evidence": f"Financial amount ${amount:.2f} exceeds threshold ${thresh:.2f}",
                        "source_type": "structured_external",  # Actual amount in context
                        "recommended_action": "human_gate",
                        "message": f"Financial commitment of ${amount:.2f} exceeds approval threshold ${thresh:.2f}. Requires Chris approval."
                    })
            except (ValueError, TypeError):
                pass  # Not numeric, skip
        
        return flags
    
    def _check_via_haiku(
        self,
        action: str,
        context: Dict[str, Any],
        timing: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Call Anthropic Haiku 4.5 to evaluate the action's appropriateness with v1.1 schema."""
        
        client = anthropic.Anthropic(api_key=self.api_key)
        
        # Prepare context
        chris_values = json.dumps(context.get("chris_values", {}), indent=2)
        chris_priorities = json.dumps(context.get("chris_priorities", []), indent=2)
        people_involved = json.dumps(context.get("people_involved", []), indent=2)
        memory_entries = json.dumps(context.get("memory_entries", []), indent=2)
        
        system_prompt = """You are LITTLE VOICE v1.1, Robert's strategic-risk evaluator.
Your job: examine the action below and flag anything that would be wrong, inappropriate, 
embarrassing, or harmful if Robert executed it without Chris's awareness.

CHECK FOR THESE 8 ITEMS:

1. **External action without approval**: Sending emails, posting, sending messages under Chris's name 
   without explicit approval.

2. **Financial commitment**: Committing Chris or Buildtronix to money, contracts, or obligations 
   to third parties without his say-so. (NOTE: May be pre-checked via threshold rule — only flag if 
   not already caught by structured_external threshold flag.)

3. **Production change outside scope**: System changes to live systems outside authorized review request scope.

4. **High-stakes timing**: Late night (0-6 UTC), before important meetings, during known stress periods.
   (NOTE: Timing 0-6 UTC + irreversible is pre-checked as structured_external. Only flag other timing issues here.)

5. **Irreversible action**: Deletes, published posts, sent emails, or other actions that cannot be undone.

6. **Sensitive relationship**: Actions involving people Chris has flagged as sensitive.

7. **Embarrassment risk**: Anything that would embarrass Chris if it became public.

8. **Value/priority mismatch**: Action deviates from Chris's stated values or contradicts his explicit priorities.

IMPORTANT: For each flag, determine source_type:
- structured_external: if based on actual external data (calendar conflict verified via API, real threshold check, 
  actual timing from clock, documented prior rejection).
- structured_memory: if based on actual memory entries (sensitive entity flag in subject memory, documented prior 
  rejection, memory entry about Chris's values).
- watcher_inference: if this is your (Haiku's) own reasoning (consequence inference, strategic assessment, 
  heuristic pattern without external data).

RESPOND with a JSON list:
[
  {
    "severity": "INFO|CAUTION|BLOCKING_REVIEW_REQUIRED|HUMAN_APPROVAL_REQUIRED",
    "confidence": "low|medium|high",
    "trigger": 1-8,
    "evidence": "what was found",
    "source_type": "structured_external|structured_memory|watcher_inference",
    "recommended_action": "log|escalate|block|human_gate",
    "message": "specific issue and why it matters"
  },
  ...
]

If NONE of the 8 items apply, respond: []

CRITICAL RULE:
- structured_external and structured_memory sources CAN trigger BLOCKING_REVIEW_REQUIRED or HUMAN_APPROVAL_REQUIRED
- watcher_inference ONLY triggers INFO or CAUTION severity, never gates
- Be direct. No explanations outside the JSON."""
        
        user_prompt = f"""ACTION TO EVALUATE:
{action}

TIMING: {timing or 'unknown'}

CHRIS'S STATED VALUES (use to check item 8):
{chris_values}

CHRIS'S CURRENT PRIORITIES (use to check item 8):
{chris_priorities}

PEOPLE INVOLVED (use to check item 6):
{people_involved}

MEMORY ENTRIES (use to check items 6, 8):
{memory_entries}

IS_EXTERNAL (affects items 1, 4, 5): {context.get('is_external', False)}
IS_IRREVERSIBLE (affects items 5, 7): {context.get('is_irreversible', False)}
INVOLVES_MONEY (affects item 2): {context.get('involves_money', False)}
AUTHORIZED_BY_RR (affects item 3): {context.get('authorized_by_rr', False)}

Check the action against all 8 items and return the JSON list with source_type and all v1.1 fields."""
        
        try:
            response = client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=1024,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ],
                timeout=self.timeout_sec
            )
            
            text = response.content[0].text if response.content else "[]"
            
            # Try to parse JSON
            result = json.loads(text)
            
            # Normalize to little_voice v1.1 format with validation
            flags = []
            if isinstance(result, list):
                for item in result:
                    # Validate source_type rule: watcher_inference cannot gate
                    source_type = item.get("source_type", "watcher_inference")
                    severity = item.get("severity", "CAUTION")
                    
                    if source_type == "watcher_inference" and severity in ["BLOCKING_REVIEW_REQUIRED", "HUMAN_APPROVAL_REQUIRED"]:
                        # Force watcher_inference flags to CAUTION (logging only)
                        severity = "CAUTION"
                    
                    flags.append({
                        "type": "little_voice",
                        "severity": severity,
                        "confidence": item.get("confidence", "medium"),
                        "trigger": item.get("trigger"),
                        "evidence": item.get("evidence", ""),
                        "source_type": source_type,
                        "recommended_action": item.get("recommended_action", "log"),
                        "message": item.get("message", "")
                    })
            
            return flags
        
        except json.JSONDecodeError as e:
            _log(f"JSON parse error from Haiku: {e}")
            return []
        except anthropic.APIError as e:
            _log(f"Anthropic API error: {e}")
            return []
