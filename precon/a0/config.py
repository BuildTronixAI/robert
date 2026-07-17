"""
A-0 Configuration
Pre-Con Supplier Intelligence Engine
"""
import os

# Supabase — BuildTronixAI project
# Credentials must be loaded from environment variables
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Microsoft Graph — OneDrive for Business
# All credentials must be loaded from environment variables
GRAPH_TENANT_ID     = os.environ.get("GRAPH_TENANT_ID", "")
GRAPH_CLIENT_ID     = os.environ.get("GRAPH_CLIENT_ID", "")
GRAPH_CLIENT_SECRET = os.environ.get("GRAPH_CLIENT_SECRET", "")  # Must be set in environment
GRAPH_WEBHOOK_NOTIFICATION_URL = os.environ.get(
    "GRAPH_WEBHOOK_NOTIFICATION_URL", "https://buildtronix.ai/api/precon/graph-webhook"
)
GRAPH_DELTA_POLL_INTERVAL_S = int(os.environ.get("GRAPH_DELTA_POLL_INTERVAL_S", "300"))  # 5 min
GRAPH_SUBSCRIPTION_RENEW_BEFORE_S = int(os.environ.get("GRAPH_SUBSCRIPTION_RENEW_BEFORE_S", "3600"))  # 1h before expiry

# Local agent
LOCAL_AGENT_ENDPOINT = os.environ.get("LOCAL_AGENT_ENDPOINT", "https://buildtronix.ai/api/precon/agent-push")
LOCAL_AGENT_HMAC_SECRET = os.environ.get("LOCAL_AGENT_HMAC_SECRET", "")  # set per-agent in deployment
LOCAL_AGENT_NONCE_TTL_S = int(os.environ.get("LOCAL_AGENT_NONCE_TTL_S", "300"))
LOCAL_AGENT_TIMESTAMP_DRIFT_S = int(os.environ.get("LOCAL_AGENT_TIMESTAMP_DRIFT_S", "60"))
LOCAL_AGENT_MAX_SEQUENCE_GAP = int(os.environ.get("LOCAL_AGENT_MAX_SEQUENCE_GAP", "1"))

# Classifier
CLASSIFIER_MODEL = os.environ.get("CLASSIFIER_MODEL", "gpt-4o-mini")  # cheap, fast
CLASSIFIER_CONFIDENCE_THRESHOLD = float(os.environ.get("CLASSIFIER_CONFIDENCE_THRESHOLD", "0.70"))
CLASSIFIER_RETRY_ATTEMPTS = int(os.environ.get("CLASSIFIER_RETRY_ATTEMPTS", "3"))
CLASSIFIER_RETRY_BACKOFF_S = int(os.environ.get("CLASSIFIER_RETRY_BACKOFF_S", "5"))
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

# Reconciler
RECONCILE_INTERVAL_S = int(os.environ.get("RECONCILE_INTERVAL_S", "14400"))  # 4h
RECONCILE_HASH_WORKERS = int(os.environ.get("RECONCILE_HASH_WORKERS", "8"))

# Watcher health
WATCHER_HEARTBEAT_INTERVAL_S = int(os.environ.get("WATCHER_HEARTBEAT_INTERVAL_S", "30"))
WATCHER_HEARTBEAT_TIMEOUT_S  = int(os.environ.get("WATCHER_HEARTBEAT_TIMEOUT_S", "90"))
WATCHER_QUEUE_OVERFLOW_THRESHOLD = int(os.environ.get("WATCHER_QUEUE_OVERFLOW_THRESHOLD", "10000"))

# Document types
DOCUMENT_TYPES = [
    "PLANS", "SPECS", "ADDENDA", "RFI", "BID_FORM",
    "VENDOR_QUOTE", "ESTIMATE", "ARCHIVE", "UNKNOWN"
]
GATE_CRITICAL_TYPES = {"PLANS", "SPECS", "ADDENDA", "BID_FORM"}

# Folder-hint mapping (path fragment → document type hint)
FOLDER_HINT_MAP = {
    "plan": "PLANS", "draw": "PLANS", "dwg": "PLANS",
    "spec": "SPECS", "project manual": "SPECS",
    "addend": "ADDENDA", "asi": "ADDENDA",
    "rfi": "RFI",
    "bid form": "BID_FORM", "bid_form": "BID_FORM",
    "quote": "VENDOR_QUOTE", "vendor": "VENDOR_QUOTE", "pricing": "VENDOR_QUOTE",
    "estimate": "ESTIMATE",
    "archive": "ARCHIVE",
}
