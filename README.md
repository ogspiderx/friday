# FRIDAY v1.0

Local-first, memory-powered CLI assistant. Sharp, autonomous, context-aware.

---

## Prerequisites

- Python 3.10+
- Groq API Key — [console.groq.com](https://console.groq.com)
- Linux environment (fish shell preferred)

---

## Installation

```bash
cd friday
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

## Configuration

```bash
cp .env.example .env
# Set GROQ_API_KEY=your_key_here inside .env
```

Model routing is pre-configured via `groq_api_complete.json`—fast tasks go to Llama 8B, heavy tasks to Llama 70B.

---

## Launch

```bash
python main.py
```

---

## Commands

| Command | Description |
| :--- | :--- |
| `help` | All available commands |
| `status` | Agent health, mode, token budget |
| `skills` | Loaded shell skills and triggers |
| `mode [safe\|auto\|build]` | Override operational mode manually |
| `exit` | Shutdown cleanly |

Kill switch: say **"stop everything"** at any point to halt all active operations.

---

## Operational Modes

| Mode | Behavior |
| :--- | :--- |
| **SAFE** | Default on launch. Confirms before new destructive actions |
| **AUTO** | Auto-runs safe/medium commands. Prompts only for new high-risk ops |
| **BUILD** | Full autonomy. Aggressive skill learning, traversal permitted |

Friday switches modes autonomously based on task context. Manual override always works.

---

## Persona Files

| File | Purpose |
| :--- | :--- |
| `SOUL.md` | Identity, voice, and personality |
| `USER.md` | User preferences, environment, memory rules |
| `AGENT.md` | Operational behavior, autonomy, safety rules |
| `HEARTBEAT.md` | Session continuity log |

Friday may update these files as she learns. You can edit them directly at any time.

---

## Key Behaviors

- Builds a checklist before any autonomous multi-step task
- Acts first, reports at the end—no mid-task narration
- Asks one clarifying question when input is ambiguous
- Warns once on first encounter with a risky command; skips warning on repeat runs
- Tracks project health, habits, and session context across restarts
- Learns and writes new skills automatically to `skills/`
- Full git management when working in a codebase

---

## Memory

Uses **MemPalace** for persistent memory. Stores everything locally. No expiry. Friday tracks preferences, habits, project state, and energy patterns across sessions.

---

## Logs & Traces

Every decision is recorded:
```
logs/traces/run-<uuid>.json
```

---

## Testing

```bash
python -m tests.harness        # offline replay against fixtures
python eval/run_eval.py        # full scenario eval suite
```

Full architectural details: [docs/behavior_contract.md](docs/behavior_contract.md)