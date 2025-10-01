# Copilot Instructions (Python) — SocketCAN Traffic Shaper & Analyzer

You are GitHub Copilot assisting on a Python project that shapes, analyzes, and replays SocketCAN traffic. Priorities: **correctness**, **clarity**, **testability**, and **Linux/WSL2 compatibility**.

## 1) Project context
- **Purpose**: Read/shape CAN frames (SocketCAN), apply filters/rate limits, record/annotate traces, and export metrics.
- **Runtime**: Linux & WSL2. Assume `socketcan` interface (e.g., `can0`, `vcan0`).
- **Core libs**: Prefer `python-can`, `asyncio`, `typer` (CLI), `pydantic` (configs), `rich` (pretty logs/CLI), `uvloop` (optional), `structlog` or std `logging`.
- **Artifacts**: CSV/JSONL exports, rolling logs, optional PCAP (if supported).

## 2) Architecture & layout
- **Dirs**
  - `src/socketcan_sa/` – package root (to match your actual project structure)
    - `io/` – adapters for CAN (python-can), files, PCAP/CSV
    - `core/` – shaping rules, filters, schedulers, pipelines
    - `cli.py` – Typer entrypoints
    - `config.py` – Pydantic models & defaults
    - `logging.py` – logging setup
    - `version.py` – `__version__`
  - `tests/` – pytest (unit first, integration with `vcan` allowed)
  - `scripts/` – dev helpers (bring up/down `vcan`, lint, fmt)
  - `docs/` – usage notes, diagrams
- **Design**
  - Separate **pure logic** (in `core/`) from **side effects** (in `io/`).
  - Use small, composable functions. Enforce dependency injection (pass adapters/clients in).
  - Prefer **pipelines**: `source -> filters -> shaper -> sink`.
  - Keep global state out; prefer instance state or function params.

## 3) Coding style & quality
- **Standards**: PEP 8 + type hints (PEP 484). All public funcs/classes documented.
- **Formatting**: `black` (line length 100) + `isort`.  
- **Lint**: `ruff` (enable flakes, pycodestyle, pyupgrade). Fix before suggesting cleverness.
- **Docstrings**: Google style.
- **Types**: Be strict; use `typing` (`Final`, `Literal`, `TypedDict`, `Protocol`) as helpful.

## 4) Testing & examples
- **Framework**: `pytest` + `pytest-asyncio`.
- **Coverage**: target ≥ 90% for `core/`.
- **Guidance**:
  - Unit tests **mock** CAN bus (`python-can` interfaces).
  - Provide a **tiny sample** `*.csv` trace under `tests/data/`.
  - Include property-based tests where simple (e.g., rate-limiter).
- **When suggesting code**: also suggest a minimal test.

## 5) Error handling & logging
- Fail **fast** on config/CLI errors with helpful messages.
- Wrap CAN I/O errors with context; avoid silent retries unless explicitly configured.
- Use `logging` (or `structlog`) with levels: DEBUG (dev), INFO (normal), WARNING/ERROR as needed.
- No prints in library code; prints allowed only in CLI for UX, but prefer `rich`.

## 6) Performance & async
- Prefer `asyncio` for readers/writers and timers; avoid blocking calls inside async tasks.
- If CPU-bound shaping emerges, hint at moving hot paths to Cython/NumPy or a worker pool.
- Avoid premature micro-optimizations; keep complexity low.

## 7) Security & safety
- Never run shell commands without validation.
- Validate all configs with Pydantic; disallow unknown fields.
- Treat captured traces as potentially sensitive; default redact VIN-like IDs on export when option enabled.

## 8) Config & CLI
- Config with Pydantic models; support `--config path.yml` and CLI flags that override config.
- Typer CLI patterns:
  - Subcommands: `capture`, `shape`, `replay`, `analyze`, `export`.
  - Common options: `--iface`, `--rules`, `--rate`, `--filter-id`, `--out`.

## 9) Data formats
- **Input**: SocketCAN live, CSV, JSONL (one frame per line).
- **Output**: CSV/JSONL, optional PCAP if feasible.
- Include schemas/examples in docstrings; keep field names snake_case.

## 10) What to **prefer**
- Small pure functions in `core`, thin I/O wrappers in `io`.
- Clear names (`tx_scheduler`, `rate_limiter`, `frame_filter`).
- `@dataclass(slots=True)` or Pydantic models for small records.
- Early returns over deep nesting.

## 11) What to **avoid**
- No global singletons; no hidden state.
- No platform-specific code outside `io/` adapters.
- Don’t introduce heavy deps without justification.
- Avoid recursion for stream processing.

## 12) Completion examples (patterns)

**Rate limiter (token bucket) skeleton**
```python
from dataclasses import dataclass
import time

@dataclass(slots=True)
class TokenBucket:
    capacity: int
    refill_per_sec: float
    _tokens: float = 0
    _last: float = 0

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        if self._last == 0:
            self._last = now
            self._tokens = self.capacity
        elapsed = now - self._last
        self._last = now
        self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_sec)
        if self._tokens >= 1:
            self._tokens -= 1
            return True
        return False

Async CAN reader interface (mockable)

from typing import Protocol, AsyncIterator

class AsyncCanSource(Protocol):
    async def frames(self) -> AsyncIterator[dict]:  # {id:int, data:bytes, ts:float}
        ...

class AsyncCanSink(Protocol):
    async def write(self, frame: dict) -> None: ...


Pytest for a filter

def test_id_filter_allows_whitelist():
    from traffic_shaper.core.filters import id_whitelist
    f = id_whitelist({0x100, 0x101})
    assert f({"id": 0x100, "data": b"", "ts": 0.0})
    assert not f({"id": 0x123, "data": b"", "ts": 0.0})


## 13) Snippets Copilot should generate
- Typer command with help, options, and examples.
- Pydantic config with env/file loading.
- Async pipeline: `source → filters[] → shaper → sink`.
- Tests with mocks and fixture data.

## 14) Repository conventions
- Use `pyproject.toml` (poetry or hatch). Expose console script `socketcan-sa` .
- Keep public API under `traffic_shaper/__init__.py`.
- Re-export stable types and functions; avoid leaking I/O internals.

## 15) Commit / PR guidance
- Conventional commits (`feat:`, `fix:`, `refactor:`).
- Include tests for new logic and update docs/examples.
- Keep PRs small and focused.

## 16) CAN Protocol Specifics
- Use hex format for CAN IDs in logs: `0x{id:X}`
- Standard vs Extended frame handling
- DLC validation (0-8 bytes for CAN 2.0)