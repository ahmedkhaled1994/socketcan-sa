# SocketCAN Traffic Shaper & Analyzer — Roadmap
_Last updated: 2025-10-02 (America/Vancouver)_

> **Next action:** **Step 9 — Pass-through bridge** (vcan0 → vcan1).  
> Goal: open two interfaces, forward frames 1:1, print periodic counters.

---

## Milestones
- **MVP v0.1 (Core CLI)** — Steps 1–12  
  Analyzer & Shaper work from CLI; YAML rules; CSV export; basic tests & README.
- **v0.2 (GUI Web Dashboard)** — GUI-1 … GUI-6  
  Start/stop from the browser; live metrics; rules editor; charts; packaging.
- **v0.3 (Advanced)**  
  PCAPng, latency histograms, C++ fast path, tc/netem integration.

---

## A) Environment & Repo
- [x] **Step 1:** Repo skeleton (`tools/`, `python/socketcan_sa/`, `configs/`, `examples/`), stub README, `.gitignore`.
- [x] **Step 2:** Install prereqs (WSL2/Ubuntu): `can-utils`, `python3-venv`.
- [x] **Step 3:** `tools/setup_vcan.sh` to bring up `vcan0` (optional `vcan1`).
- [x] **Step 4:** `tools/teardown_vcan.sh` to remove `vcan*`.
- [x] **Step 5:** Verify `vcan0` up.

**Acceptance:** `ip link show vcan0` shows `state UP`.

---

## B) Traffic Baseline
- [x] **Step 6:** Smoke test  
  - A: `candump vcan0`  
  - B: `cangen vcan0 -I 0x123 -L 8 -g 5`  
**Acceptance:** frames visible; stop via `Ctrl+C` or `-n`/`timeout`.

---

## C) Analyzer MVP
- [x] **Step 7:** Minimal analyzer  
  Per-ID **FPS** + **avg payload** every `--interval`.  
  **Acceptance:** stats reflect generator start/stop.

- [x] **Step 8:** Bus-load + CSV + simple jitter  
  - Rough bus-load % (assume `--bitrate`, default 500k).  
  - `--csv out.csv` writes `{ts, iface, load, id, fps, jitter_ms, avg_len, count}`.  
**Acceptance:** console + CSV lines update per window.

---

## D) Shaper MVP (Bridge & Rules)
- [ ] **Step 9 (NEXT):** Pass-through bridge  
  Open `--if-in vcan0`, `--if-out vcan1`; forward all frames; counters for rx/tx/errors.  
  **Test:** `cangen vcan0 …` → `candump vcan1` shows identical frames.

- [ ] **Step 10:** Rules YAML + parser  
  File: `configs/rules.dev.yaml`  
  ```yaml
  limits:
    "0x18FF50E5": { rate: 50, burst: 25 }
  actions:
    drop:  [ "0x123" ]
    remap: [ { from: "0x456", to: "0x457" } ]
  ```
  **Acceptance:** invalid IDs/fields produce clear errors.

- [ ] **Step 11:** Apply actions in shaper  
  - drop (suppress IDs)  
  - remap (change arbitration ID)  
  - rate-limit per-ID (token bucket)  
**Test:** cangen shows: dropped IDs disappear on out; remapped IDs change; rate-limited FPS decreases on out.

---

## E) CLI & Packaging
- [ ] **Step 12**: Unified CLI + packaging
  - python/socketcan_sa/cli.py → socketcan-sa analyze|shape
  - pyproject.toml console script entry.
**Acceptance**: commands run from venv anywhere.

---

## F) Tests & Docs

- [ ] **Step 13**: Unit tests
  - TokenBucket math
  - Rules parser edge cases
  - (Optional) Analyzer windowing math
**Acceptance**: pytest green locally.

- [ ] Step 14: README pass
  - Quick start (WSL2 + Linux)
  - Rule syntax & examples
  - Known limits (bit-stuffing ignored, 11/29-bit overhead approximation, etc.)

---

## G) GUI Track — Web UI (after Step 12, or parallel after Step 9)

- [ ] **GUI-1: Service layer (backend orchestration)**
    service.py runs analyzer/shaper as async tasks; shared state (latest window + ring buffer).
**Acceptance**: start analyzer headless; metrics accumulate.

- [ ] **GUI-2: API & WebSocket**
  - api.py (FastAPI + Uvicorn):
  - POST /api/analyzer/start|stop
  - POST /api/shaper/start|stop
  - GET/PUT /api/rules (validate & hot-apply)
  - WS /ws/metrics pushes JSON each window
**Acceptance**: REST controls work; WS streams ~1 Hz.

- [ ] **GUI-3: Frontend scaffold**
  - ui/web/ (Vite + React + Tailwind). Components:
  - Dashboard: bus-load gauge, per-ID table (sortable)
  - Controls: start/stop forms
  - Rules editor (Monaco) with validate/apply
**Acceptance**: live table updates via WS.

- [ ] **GUI-4: History & charts**
    Rolling charts (60–300s) for bus load & per-ID FPS/jitter; CSV export of view.
**Acceptance**: smooth ≤1s cadence; export works.

- [ ] **GUI-5: Packaging & DX**
  - make gui-backend (uvicorn) / make gui-frontend (Vite)
  - Production: build frontend; serve static from FastAPI at /
  - WSL2 localhost access verified
**Acceptance**: one-command start for full stack.

- [ ] **GUI-6: Validation & tests**
  - Pydantic schemas tested
  - Basic Playwright E2E: start analyzer, verify metrics, stop
**Acceptance**: tests green.

---

## H) Desktop Track (later, for learning)
  - **Option 1**: PySide6/Qt — native app using shared core; simple parity (start/stop, table, chart).
  - **Option 2**: Tauri — web tech desktop; call FastAPI or embed local service.

---

## Risks / Notes
  - Bus-load is approximate (ignores bit-stuffing, different overhead for ext IDs/RTR).
  - WSL2 kernel must support vcan; scripts assume iproute2.
  - Shaper rate limits at user-space granularity; kernel qdisc later for tighter bounds.