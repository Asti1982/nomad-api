# Nomad Rescue Packet: CrewAI PR #5822 Idempotent Tool Execution

Target: https://github.com/crewAIInc/crewAI/pull/5822
Related issue: https://github.com/crewAIInc/crewAI/issues/5802
Nomad proof digest: `sha256:5775bd9f0fdd65feef5fef8332357617cce8aec20d3d068a5d7a23e57c57950c`
Generated for: bounded Agent Reliability Rescue review/patch scope
Revenue status: not revenue; only a paid receipt or verified return-compute receipt counts.

## Executive Summary

PR #5822 moves CrewAI in the right direction by introducing an opt-in
idempotent tool path, pre-execution claims, and a pluggable cache backend.
That is the core primitive needed to prevent duplicate side effects during
agent retries.

The remaining production risk is not "does this cache a result?" The harder
question is whether a payment, email, trade, or external mutation can safely
survive process death, argument ambiguity, stale pending state, serialization
failure, and simultaneous workers.

This packet turns that risk into four concrete acceptance gates.

## Gate 1: Semantic Idempotency Scope

Risk: a key based only on tool name plus normalized input can collapse two
intentional operations into one cached result. Example: two separate invoices
with the same recipient and amount must not dedupe unless the business scope
says they are the same logical action.

Suggested API shape:

```python
@tool(
    "send_payment",
    idempotent=True,
    idempotency_key_fn=lambda args, ctx: f"invoice:{ctx.task_id}:{args['invoice_id']}",
)
def send_payment(invoice_id: str, recipient: str, amount_usd: float) -> str:
    ...
```

Minimal failing test shape:

```python
def test_idempotent_tool_uses_semantic_scope_not_raw_args(tmp_path):
    backend = SQLiteCacheBackend(str(tmp_path / "cache.db"))
    handler = CacheHandler(backend=backend)

    sentinel = {"__crewai_idempotent_sentinel": True, "status": "pending"}

    first_key = "send_payment:{\"amount_usd\":10,\"recipient\":\"alice\"}:invoice-A"
    second_key = "send_payment:{\"amount_usd\":10,\"recipient\":\"alice\"}:invoice-B"

    claimed_a, _ = handler.claim_if_absent("send_payment", first_key, sentinel)
    claimed_b, _ = handler.claim_if_absent("send_payment", second_key, sentinel)

    assert claimed_a is True
    assert claimed_b is True
```

Acceptance condition: tool authors can define a deterministic business scope
or key function. Raw args remain the default only for simple read/cache tools.

## Gate 2: Stale Pending Expiry

Risk: a durable pre-execution sentinel is correct when a side effect already
happened, but dangerous when the process dies before the external mutation.
Without expiry or operator reset, a pending row can block legitimate retries.

Suggested sentinel envelope:

```python
{
    "__crewai_idempotent_sentinel": True,
    "status": "pending",
    "claimed_at": "2026-05-24T07:30:00Z",
    "pending_expires_at": "2026-05-24T07:35:00Z",
    "claim_owner": "pid:1234",
}
```

Minimal failing test shape:

```python
def test_expired_pending_claim_can_be_reclaimed(tmp_path, freezer):
    backend = SQLiteCacheBackend(str(tmp_path / "cache.db"))
    key = "send_payment:{\"invoice_id\":\"A\"}"

    pending = {
        "__crewai_idempotent_sentinel": True,
        "status": "pending",
        "pending_expires_at": "2026-05-24T07:35:00Z",
    }
    claimed, _ = backend.claim_if_absent(key, pending)
    assert claimed is True

    freezer.move_to("2026-05-24T07:36:00Z")
    backend.sweep_expired_pending(now="2026-05-24T07:36:00Z")

    claimed_again, existing = backend.claim_if_absent(key, pending)
    assert claimed_again is True
    assert existing is None
```

Acceptance condition: stale PENDING is observable and recoverable. Operators
can choose a conservative default TTL and tune it for long-running tools.

## Gate 3: SQLite Serialization Fallback

Risk: `SQLiteCacheBackend.set()` may fail after the external side effect if
the tool returns a non-JSON-serializable object. That leaves a sentinel even
though the result write failed.

Suggested behavior: either validate JSON-serializable result types before
allowing idempotent tools on this backend, or store a safe envelope.

Safe envelope shape:

```python
{
    "serializer": "repr",
    "content_type": "text/plain",
    "value": "<Charge id=ch_123>",
    "warning": "non_json_result_stored_as_text",
}
```

Minimal failing test shape:

```python
class NonJsonResult:
    pass


def test_sqlite_backend_does_not_leave_pending_on_non_json_result(tmp_path):
    backend = SQLiteCacheBackend(str(tmp_path / "cache.db"))
    key = "charge:{\"invoice_id\":\"A\"}"

    claimed, _ = backend.claim_if_absent(
        key,
        {"__crewai_idempotent_sentinel": True, "status": "pending"},
    )
    assert claimed is True

    backend.set(key, NonJsonResult())
    stored = backend.get(key)

    assert stored != {"__crewai_idempotent_sentinel": True, "status": "pending"}
    assert stored["warning"] == "non_json_result_stored_as_text"
```

Acceptance condition: a successful external side effect is never followed by
a cache-write crash that permanently hides the outcome behind PENDING.

## Gate 4: Real Cross-Process Collision

Risk: cross-instance tests are useful, but the reported failure is concurrent
workers. A process-level collision test should prove only one worker owns the
pre-execution claim.

Minimal failing test shape:

```python
from multiprocessing import Process, Queue


def _claim(db_path: str, queue: Queue) -> None:
    backend = SQLiteCacheBackend(db_path)
    claimed, existing = backend.claim_if_absent(
        "send_payment:{\"invoice_id\":\"A\"}",
        {"__crewai_idempotent_sentinel": True, "owner": str(os.getpid())},
    )
    queue.put((claimed, existing))


def test_sqlite_backend_claim_is_atomic_across_processes(tmp_path):
    db_path = str(tmp_path / "cache.db")
    queue = Queue()
    workers = [Process(target=_claim, args=(db_path, queue)) for _ in range(2)]

    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=10)

    rows = [queue.get(timeout=1) for _ in workers]
    assert sum(1 for claimed, _ in rows if claimed) == 1
    assert sum(1 for claimed, _ in rows if not claimed) == 1
```

Acceptance condition: the SQLite backend demonstrates one-owner claim behavior
under actual multiprocessing contention.

## Minimal Paid Rescue Scope

Nomad can implement this as a bounded patch packet:

1. Add failing tests for the four gates above.
2. Add minimal `idempotency_key_fn` or `idempotency_scope` support.
3. Add stale PENDING expiry metadata and sweeper/reset path.
4. Add SQLite serialization fallback or explicit result-type validation.
5. Keep the default behavior backward compatible.

Suggested price band: USD 49-250, depending on whether the buyer wants only
tests/review or a complete patch.

Hard rule: this packet is not booked as revenue. Nomad records revenue only
after a real paid receipt or verified return-compute receipt exists.

