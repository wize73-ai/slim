# `core/timing/` — per-request `t0..t5` instrumentation

Locked. Records six timestamps per chat handler invocation. Two are set
automatically (`t0` on context entry, `t5` on context exit), four are user-set
via `t.mark("...")` at the appropriate points in the handler.

| Marker | When | Set by |
|---|---|---|
| `t0` | Enter chat handler | **automatic** (`Instrument.__init__`) |
| `t1` | `build_request()` done | `t.mark("t1")` |
| `t2` | First byte sent to guapo | `t.mark("t2")` |
| `t3` | First SSE chunk back — **prefill done** | `t.mark("t3")` |
| `t4` | Last SSE chunk — **decode done** | `t.mark("t4")` |
| `t5` | Last byte written to the client | **automatic** (`Instrument.__exit__`) |

`TimingRecord` exposes computed duration properties for each interval:

| Property | Interval | Represents |
|---|---|---|
| `build_request_ns` | `t0 → t1` | Pre-processing on our side |
| `network_out_ns` | `t1 → t2` | Send latency to guapo |
| `prefill_ns` | `t2 → t3` | Guapo prefill (input tokens dominate) |
| `decode_ns` | `t3 → t4` | Guapo decode (output tokens dominate) |
| `network_back_ns` | `t4 → t5` | Render / send-back to client |
| `total_ns` | `t0 → t5` | End-to-end wall time |

These feed the pre-vs-post processing stacked bar, the TTFT-vs-inter-token
chart, and the projection calculator's coefficients in the metrics tab.

## Usage

```python
from core.timing import instrument

async def chat_handler(request):
    with instrument() as t:
        # t0 (handler enter) is set automatically
        messages = build_request(...)
        t.mark("t1")
        async for chunk in stream_completion(messages, t):
            yield chunk
        # t5 (handler exit) is set automatically when this block exits
```

The same `t` instance is typically threaded through downstream calls so they
can record their own markers — for example `stream_completion` would call
`t.mark("t2")` right before sending bytes to guapo and `t.mark("t3")` on the
first SSE chunk back.

`async with instrument() as t:` is also supported for async-only call sites.

## Wiring to observability

Timing has zero knowledge of `core/observability/` to avoid a circular
dependency. Instead, observability registers an emitter callback at startup:

```python
# core/observability/app.py (illustrative)
from core.observability.ring_buffer import buffer
from core.timing import set_emitter

set_emitter(buffer.append)
```

Once registered, every `Instrument` context exit pushes a `TimingRecord` to
the buffer. Until registered (e.g., in tests), records are silently discarded.

## Type safety

`TimingMark` is a `Literal["t1","t2","t3","t4"]`, so `t.mark("t9")` is a mypy
error. `t0` and `t5` are deliberately excluded from the literal so user code
can't accidentally re-mark them.
