"""Resend email tool for Robert - urllib-based, no SDK dependency."""

import os
import json
import urllib.request
import urllib.error
from typing import Optional

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")  # Must be set in environment
RESEND_BASE_URL = "https://api.resend.com/emails"


def send_email(
    to: str, 
    subject: str, 
    body: str, 
    html: Optional[str] = None,
    from_email: str = "robert@buildtronix.ai"
) -> bool:
    """
    Send an email via Resend API using urllib (no SDK dependency).
    
    Args:
        to: Recipient email address
        subject: Email subject
        body: Email body (plain text, used as fallback if html not provided)
        html: HTML email body (optional, preferred over plain text)
        from_email: Sender email address
    
    Returns:
        True if successful, False otherwise
    """
    try:
        if not RESEND_API_KEY:
            raise ValueError("RESEND_API_KEY not configured")
        
        # Prepare email payload
        payload = {
            "from": from_email,
            "to": to,
            "subject": subject,
        }
        
        # Use HTML if provided, otherwise plain text
        if html:
            payload["html"] = html
        else:
            payload["text"] = body
        
        # Convert to JSON
        payload_json = json.dumps(payload).encode('utf-8')
        
        # Create HTTP request
        req = urllib.request.Request(
            RESEND_BASE_URL,
            data=payload_json,
            headers={
                "Authorization": f"Bearer {RESEND_API_KEY}",
                "Content-Type": "application/json"
            },
            method="POST"
        )
        
        # Send request
        with urllib.request.urlopen(req, timeout=10) as response:
            response_data = json.loads(response.read().decode('utf-8'))
            status_code = response.status
            
            if status_code in [200, 201]:
                print(f"[Resend] Email sent to {to}. ID: {response_data.get('id', 'unknown')}")
                return True
            else:
                print(f"[Resend] Unexpected status {status_code}: {response_data}")
                return False
                
    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8')
        print(f"[Resend] HTTP Error {e.code}: {error_body}")
        return False
    except Exception as e:
        print(f"[Resend] Failed to send email to {to}: {str(e)}")
        return False
