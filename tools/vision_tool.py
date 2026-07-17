"""
Vision and image processing tool for Robert COO Agent.

Handles:
- Telegram photo downloads
- Base64 encoding for Claude API
- Multimodal vision analysis via OpenRouter
- Construction image classification
- Error handling with credential scrubbing
"""

import base64
import json
import logging
import urllib.request
import urllib.error
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class VisionError(Exception):
    pass

class VisionAPIError(VisionError):
    pass

class ImageValidationError(VisionError):
    pass


def _validate_image(image_bytes: bytes, mime_type: str) -> None:
    MAX_SIZE = 20 * 1024 * 1024
    if len(image_bytes) > MAX_SIZE:
        raise ImageValidationError(f"Image too large: {len(image_bytes)} bytes (max {MAX_SIZE})")
    if len(image_bytes) < 100:
        raise ImageValidationError("Image too small to be valid")
    valid_types = {"image/jpeg", "image/png", "image/gif", "image/webp"}
    if mime_type not in valid_types:
        raise ImageValidationError(f"Unsupported image type: {mime_type}")


def _call_claude_vision_api(image_base64: str, mime_type: str,
                             caption: str = "", task_context: str = "") -> str:
    """Call Claude Sonnet vision API via OpenRouter."""
    import os
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise VisionAPIError("OPENROUTER_API_KEY not configured")

    prompt_parts = ["Analyze this image from a construction/project management context."]
    if caption:
        prompt_parts.append(f'User caption: "{caption}"')
    if task_context:
        prompt_parts.append(f"Project context: {task_context[:300]}")
    prompt_parts.extend([
        "",
        "Provide analysis covering:",
        "1. Image type (floor plan, site photo, material sample, document scan, elevation, section, etc.)",
        "2. Key visible elements or text",
        "3. Technical observations relevant to construction/project management",
        "4. Any warnings, issues, or concerns visible",
        "5. Recommended next actions or follow-up items",
        "",
        "Be concise but specific. Reference actual details from the image."
    ])
    prompt = "\n".join(prompt_parts)

    payload = {
        "model": "anthropic/claude-sonnet-4-6",
        "max_tokens": 2000,
        "system": (
            "You are Robert, a construction and project management AI analyzing images for Buildtronix AI. "
            "Be technical, specific, and actionable. Reference actual visible details."
        ),
        "messages": [{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_base64
                    }
                },
                {"type": "text", "text": prompt}
            ]
        }]
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://buildtronix.ai",
        "X-Title": "Robert COO Agent",
    }

    # Try OpenRouter proxy first, fall back to direct API
    urls = [
        "http://localhost:7777/openrouter/v1/messages",
        "https://openrouter.ai/api/v1/chat/completions",
    ]

    last_error = None
    for url in urls:
        try:
            # OpenRouter chat completions format for non-proxy
            if "openrouter.ai" in url:
                payload_to_send = {
                    "model": "anthropic/claude-sonnet-4-6",
                    "max_tokens": 2000,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}"
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }]
                }
            else:
                payload_to_send = payload

            req = urllib.request.Request(
                url,
                data=json.dumps(payload_to_send).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                # Handle Anthropic-style response
                if "content" in result:
                    for block in result.get("content", []):
                        if block.get("type") == "text":
                            return block["text"]
                # Handle OpenRouter chat completions style
                if "choices" in result:
                    return result["choices"][0]["message"]["content"]
                return "Vision analysis completed."
        except urllib.error.HTTPError as e:
            last_error = f"HTTP {e.code}: {e.read().decode('utf-8', errors='ignore')[:200]}"
            if e.code == 401:
                raise VisionAPIError("Vision API authentication failed")
            continue
        except urllib.error.URLError:
            continue  # Try next URL

    raise VisionAPIError(f"All vision API endpoints failed. Last: {last_error}")


def classify_construction_image(analysis_text: str) -> Dict[str, Any]:
    keywords = {
        "floor_plan": ["floor", "plan", "layout", "room", "dimension", "scale", "area", "walls"],
        "site_photo": ["site", "construction", "progress", "scaffolding", "workers", "equipment"],
        "material_sample": ["material", "sample", "finish", "color", "texture", "tile", "paint"],
        "document_scan": ["document", "scan", "page", "text", "specification", "form", "printed"],
        "elevation": ["elevation", "facade", "front", "side", "exterior", "architectural"],
        "section": ["section", "cross-section", "detail", "structure", "cut", "vertical"],
    }
    analysis_lower = analysis_text.lower()
    scores = {t: sum(1 for kw in kws if kw in analysis_lower) for t, kws in keywords.items()}
    best_type = max(scores, key=scores.get) if scores else "unknown"
    confidence = min(scores.get(best_type, 0) / max(len(keywords.get(best_type, [1])), 1), 1.0)
    return {"type": best_type, "confidence": confidence, "all_scores": scores}


def process_image_with_context(image_bytes: bytes, mime_type: str = "image/jpeg",
                                caption: str = "", task_context: str = "") -> str:
    """Process image bytes and return analysis string."""
    try:
        _validate_image(image_bytes, mime_type)
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        return _call_claude_vision_api(image_base64, mime_type, caption, task_context)
    except ImageValidationError as e:
        return f"Image validation error: {str(e)}"
    except VisionAPIError as e:
        return f"Image analysis failed: {str(e)[:200]}"
    except Exception as e:
        try:
            from tools.base import sanitize_error
            return f"Image analysis failed: {sanitize_error(str(e))[:200]}"
        except Exception:
            return f"Image analysis failed: {str(e)[:200]}"


def process_image(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    return process_image_with_context(image_bytes, mime_type)
