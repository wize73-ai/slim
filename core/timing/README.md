# `core/timing/` — per-request `t0..t5` instrumentation

Locked. Tiny module (~30 lines) that records six timestamps per chat handler
invocation:

| Marker | When |
|---|---|
| `t0` | Enter chat handler |
| `t1` | `build_request()` done |
| `t2` | First byte sent to guapo |
| `t3` | First SSE chunk back from guapo — **prefill done** |
| `t4` | Last SSE chunk from guapo — **decode done** |
| `t5` | Last byte written to the client |

The intervals give us:

- `t1 - t0` — request build time
- `t2 - t1` — send latency
- `t3 - t2` — **prefill time** (TTFT minus send latency)
- `t4 - t3` — **decode time**
- `t5 - t4` — render / send-back time

These feed the pre-vs-post processing stacked bar in the metrics tab and the
TTFT-vs-inter-token-latency chart.

## Usage

```python
from core.timing import instrument

async def chat_handler(request):
    with instrument() as t:
        t.mark("t0")
        messages = build_request(...)
        t.mark("t1")
        async for chunk in stream_completion(messages, t):
            yield chunk
        t.mark("t5")
```

The instrument context automatically emits records to the observability ring
buffer on exit.
