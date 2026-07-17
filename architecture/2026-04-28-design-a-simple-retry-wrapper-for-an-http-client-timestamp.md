# Design: Design a simple retry wrapper for an HTTP client. Timestamp:1777343717

Generated: 2026-04-28T02:36:26.273924

# Design Document: HTTP Client Retry Wrapper

**Author:** Robert  
**Phase:** Architecture  
**Timestamp:** 1777343717

---

## Problem Restatement

We need a retry wrapper for a Python HTTP client that handles transient failures from external APIs — specifically HTTP 429 (Too Many Requests) and 503 (Service Unavailable) responses. The wrapper must implement configurable retry logic with backoff, and either return a successful response or raise a well-defined exception after exhausting all attempts. The wrapper must be reusable across multiple API call sites without duplicating retry logic.

---

## Success Criteria

1. A successful response (non-retryable status code) is returned transparently on the first or any subsequent attempt.
2. On 429/503, the wrapper retries up to `max_attempts` times before raising.
3. Backoff delay between retries is configurable (exponential with optional jitter).
4. `Retry-After` header on 429 responses is respected when present.
5. Non-retryable HTTP errors (e.g., 400, 401, 404, 500) are **not** retried — they raise immediately.
6. Network-level exceptions (`ConnectionError`, `Timeout`) are retried under the same policy.
7. After `max_attempts` exhaustion, a single well-typed exception is raised containing attempt count and last error.
8. The wrapper is callable as both a function decorator and a direct call wrapper.
9. All retry behavior is unit-testable without real network I/O.
10. Zero external dependencies beyond `requests` (or `httpx` if async is needed).

---

## Proposed Approach

### Architecture Overview

A single `RetryWrapper` class encapsulates all retry policy state. It exposes:
- A `call(func, *args, **kwargs)` method for direct wrapping.
- A `__call__` decorator interface.

The retry loop is synchronous. An async variant (`AsyncRetryWrapper`) is structurally identical but uses `asyncio.sleep`.

### Retry Decision Logic

```
attempt = 1
loop:
    response = make_request()
    if response is success → return response
    if response.status in RETRYABLE_STATUSES → compute delay, sleep, retry
    if response.status is non-retryable → raise immediately
    if attempt == max_attempts → raise MaxRetriesExceeded
    attempt++
```

### Backoff Strategy

**Exponential backoff with full jitter** (recommended by AWS):

```
delay = min(cap, base * 2^attempt) * random(0, 1)
```

- `base`: initial delay in seconds (default: `1.0`)
- `cap`: maximum delay ceiling (default: `60.0`)
- Jitter prevents thundering herd when many clients retry simultaneously.
- `Retry-After` header overrides computed delay when present and larger.

### Retryable Conditions

| Condition | Retryable | Reason |
|---|---|---|
| HTTP 429 | ✅ | Rate limited, transient |
| HTTP 503 | ✅ | Service unavailable, transient |
| HTTP 502, 504 | ✅ | Gateway errors, configurable |
| `requests.Timeout` | ✅ | Network transient |
| `requests.ConnectionError` | ✅ | Network transient |
| HTTP 400, 401, 403, 404 | ❌ | Client error, not transient |
| HTTP 500 | ❌ | Server logic error (default off) |
| HTTP 200–299 | ❌ (success) | Return immediately |

Retryable status codes are **configurable** at construction time.

---

## Key Interfaces & Data Structures

### Configuration Dataclass

```python
from dataclasses import dataclass, field
from typing import Set

@dataclass
class RetryConfig:
    max_attempts: int = 3                          # Total attempts (not retries)
    base_delay: float = 1.0                        # Seconds, base for exponential backoff
    max_delay: float = 60.0                        # Seconds, ceiling on delay
    jitter: bool = True                            # Enable full jitter
    retryable_status_codes: Set[int] = field(
        default_factory=lambda: {429, 503, 502, 504}
    )
    retry_on_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
    )
    respect_retry_after: bool = True               # Honor Retry-After header
```

### Custom Exceptions

```python
class RetryError(Exception):
    """Raised when all retry attempts are exhausted."""
    def __init__(
        self,
        message: str,
        attempts: int,
        last_exception: Exception | None = None,
        last_status_code: int | None = None,
    ):
        super().__init__(message)
        self.attempts = attempts
        self.last_exception = last_exception
        self.last_status_code = last_status_code


class NonRetryableError(Exception):
    """Raised immediately when a non-retryable HTTP status is received."""
    def __init__(self, message: str, status_code: int, response: object):
        super().__init__(message)
        self.status_code = status_code
        self.response = response
```

### Core Class Interface

```python
import time
import random
import logging
from typing import Callable, Any
from requests import Response, RequestException

logger = logging.getLogger(__name__)


class RetryWrapper:
    def __init__(self, config: RetryConfig | None = None):
        self.config = config or RetryConfig()

    def call(
        self,
        func: Callable[..., Response],
        *args: Any,
        **kwargs: Any,
    ) -> Response:
        """
        Execute func(*args, **kwargs) with retry logic applied.
        Returns Response on success.
        Raises RetryError after max_attempts exhaustion.
        Raises NonRetryableError on non-retryable HTTP status.
        """
        ...

    def __call__(self, func: Callable) -> Callable:
        """Decorator interface."""
        import functools

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return self.call(func, *args, **kwargs)

        return wrapper

    def _compute_delay(self, attempt: int, response: Response | None) -> float:
        """
        Returns sleep duration in seconds for this attempt.
        Respects Retry-After header if present and config allows.
        """
        ...

    def _is_retryable_response(self, response: Response) -> bool:
        """Returns True if response status code warrants a retry."""
        return response.status_code in self.config.retryable_status_codes

    def _is_success(self, response: Response) -> bool:
        """Returns True if response is a 2xx success."""
        return 200 <= response.status_code < 300
```

### `_compute_delay` Contract

```python
def _compute_delay(self, attempt: int, response: Response | None) -> float:
    # 1. Check Retry-After header first (if response exists and config allows)
    if self.config.respect_retry_after and response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return max(0.0, float(retry_after))
            except ValueError:
                pass  # Ignore malformed header, fall through to computed delay

    # 2. Exponential backoff: base * 2^(attempt-1), capped
    exponential = self.config.base_delay * (2 ** (attempt - 1))
    capped = min(self.config.max_delay, exponential)

    # 3. Apply full jitter
    if self.config.jitter:
        return random.uniform(0, capped)
    return capped
```

### `call` Method Contract

```python
def call(self, func, *args, **kwargs) -> Response:
    last_exception = None
    last_status_code = None

    for attempt in range(1, self.config.max_attempts + 1):
        try:
            response = func(*args, **kwargs)
        except self.config.retry_on_exceptions as exc:
            last_exception = exc
            logger.warning("Attempt %d/%d failed with exception: %s",
                           attempt, self.config.max_attempts, exc)
            if attempt == self.config.max_attempts:
                raise RetryError(
                    f"All {self.config.max_attempts} attempts failed.",
                    attempts=attempt,
                    last_exception=exc,
                ) from exc
            delay = self._compute_delay(attempt, None)
            logger.info("Retrying in %.2fs...", delay)
            time.sleep(delay)
            continue

        last_status_code = response.status_code

        if self._is_success(response):
            return response

        if self._is_retryable_response(response):
            logger.warning("Attempt %d/%d got status %d.",
                           attempt, self.config.max_attempts, response.status_code)
            if attempt == self.config.max_attempts:
                raise RetryError(
                    f"All {self.config.max_attempts} attempts failed.",
                    attempts=attempt,
                    last_status_code=response.status_code,
                )
            delay = self._compute_delay(attempt, response)
            logger.info("Retrying in %.2fs...", delay)
            time.sleep(delay)
            continue

        # Non-retryable HTTP status
        raise NonRetryableError(
            f"Non-retryable status {response.status_code} received.",
            status_code=response.status_code,
            response=response,
        )

    # Unreachable, but satisfies type checkers
    raise RetryError("Retry loop exited unexpectedly.", attempts=self.config.max_attempts)
```

### Usage Examples

```python
# Direct call
config = RetryConfig(max_attempts=5, base_delay=0.5)
wrapper = RetryWrapper(config)
response = wrapper.call(requests.get, "https://api.example.com/data")

# Decorator
retry = RetryWrapper(RetryConfig(max_attempts=3))

@retry
def fetch_user(user_id: int) -> Response:
    return requests.get(f"https://api.example.com/users/{user_id}")

# Async variant (same interface, uses asyncio.sleep)
async_wrapper = AsyncRetryWrapper(config)
response = await async_wrapper.call(httpx_client.get, url)
```

---

## Failure Modes & Mitigations

| Failure Mode | Likelihood | Mitigation |
|---|---|---|
| `Retry-After` header is a date string (RFC 7231 format), not seconds | Medium | Parse `http.cookiejar.http2time` or `email.utils.parsedate`; fall back to computed delay on parse failure |
| `random.uniform` returns near-zero, causing rapid retry storm | Low | Enforce a minimum floor: `max(0.1, computed_delay)` |
| `max_attempts=1` means no retries — caller confusion | Medium | Document clearly; consider `min_attempts` validation in `__post_init__` |
| Caller passes a function that raises non-`RequestException` exceptions | High | Only catch explicitly listed exception types; let others propagate naturally |
| `time.sleep` in tests causes slow test suite | High | Inject `sleep_func` as a constructor parameter (default `time.sleep`); tests inject `lambda s: None` |
| Infinite delay from malformed `Retry-After: 999999` | Low | Cap `Retry-After` value at `max_delay` |
| Thread safety of shared `RetryWrapper` instance | Low | `RetryWrapper` holds no mutable state after construction; safe to share |
| 3xx redirects not followed | Low | Delegate to `requests` session which handles redirects by default |

---

## Alternatives Considered

### 1. `urllib3.Retry` / `requests.adapters.HTTPAdapter`

**Pros:** Battle-tested, built into the stack.  
**Cons:** Tightly coupled to `requests` transport layer; cannot retry on response body content; `Retry-After` support is limited; hard to unit test without mocking adapters; no clean decorator interface.  
**Verdict:** Rejected. Our wrapper is transport-agnostic and fully testable.

### 2. `tenacity` library

**Pros:** Feature-rich, well-maintained, handles async.  
**Cons:** External dependency; more complex API than needed; overkill for this use case; adds supply-chain risk.  
**Verdict:** Rejected. The requirement is a *simple* wrapper with zero new dependencies.

### 3. Recursive retry function

**Pros:** Concise.  
**Cons:** Stack depth grows with `max_attempts`; harder to reason about state; no clean way to inject sleep for testing.  
**Verdict:** Rejected in favor of explicit loop.

### 4. Decorator-only interface (no `call` method)

**Pros:** Simpler API surface.  
**Cons:** Cannot wrap third-party callables (e.g., `requests.get`) without defining a wrapper function first.  
**Verdict:** Rejected. Both interfaces are needed.

---

## Implementation Plan

Each step is independently verifiable via unit tests.

| Step | Task | Verification |
|---|---|---|
| 1 | Define `RetryConfig` dataclass with `__post_init__` validation (`max_attempts >= 1`, `base_delay > 0`) | `pytest` on config construction edge cases |
| 2 | Define `RetryError` and `NonRetryableError` exception classes | Instantiate and inspect attributes |
| 3 | Implement `_is_success` and `_is_retryable_response` | Unit test with mock responses for all status code categories |
| 4 | Implement `_compute_delay` with exponential + jitter, no `Retry-After` yet | Assert delay is within `[0, max_delay]` for attempts 1–10; seed `random` for determinism |
| 5 | Add `Retry-After` header parsing to `_compute_delay` (seconds and date formats) | Unit test with header values: `"30"`, `"0"`, `"invalid"`, RFC date string |
| 6 | Implement `call` loop — success path only | Mock func returning 200; assert returned immediately, no sleep called |
| 7 | Implement `call` loop — retryable status path | Mock func returning 503 × N then 200; assert correct sleep calls and final return |
| 8 | Implement `call` loop — exhaustion path | Mock func always returning 429; assert `RetryError` raised with correct `attempts` count |
| 9 | Implement `call` loop — non-retryable status path | Mock func returning 404; assert `NonRetryableError` raised on first attempt, no sleep |
| 10 | Implement `call` loop — exception retry path | Mock func raising `ConnectionError` then succeeding; assert retry and return |
| 11 | Implement `__call__` decorator interface | Decorate a test function; verify behavior matches `call` |
| 12 | Integration test with `responses` library (mocked HTTP) | Full end-to-end: 429 → 429 → 200 with `Retry-After: 2` header |
| 13 | Implement `AsyncRetryWrapper` with `asyncio.sleep` | Mirror all sync tests using `pytest-asyncio` |
| 14 | Add logging at WARNING (retryable failure) and INFO (delay) levels | Assert log output with `caplog` fixture |

---

## Confidence Score

**9 / 10**

**Rationale:**  
- The design is complete, self-contained, and covers all specified requirements plus realistic edge cases.  
- Interfaces are fully specified; implementation is mechanical from this document.  
- The `-1` is for the `Retry-After` date-format parsing (RFC 7231 HTTP-date), which has minor ambiguity around timezone handling in Python's stdlib — this is a known rough edge that Step 5 must address explicitly with a tested fallback path.  
- Async variant is structurally sound but not fully detailed; if async is in scope, it warrants a brief addendum before implementation begins.