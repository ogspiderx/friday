# FRIDAY v1.0

Local-first, memory-powered CLI assistant.

---

## Prerequisites

- Python 3.10+
- Groq API Key — [console.groq.com](https://console.groq.com)
- Linux, fish shell

---

## Setup

```bash
cd friday
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # set GROQ_API_KEY
```

---

## Launch

```bash
python main.py
```

| Command | Description |
| :--- | :--- |
| `help` | All commands |
| `status` | Health, mode, token budget |
| `skills` | Loaded skills and triggers |
| `mode [safe\|auto\|build]` | Manual mode override |
| `exit` | Clean shutdown |

Kill switch: **"stop everything"**

---

## Modes

| Mode | Behavior |
| :--- | :--- |
| SAFE | Default. Confirms before new destructive actions |
| AUTO | Auto-runs safe/medium. Prompts for new high-risk only |
| BUILD | Full autonomy. Aggressive skill learning |

Friday switches modes autonomously. Manual override always works.

---

## Persona Files

| File | Purpose |
| :--- | :--- |
| `SOUL.md` | Identity and voice |
| `USER.md` | Preferences and environment |
| `AGENT.md` | Behavior and autonomy rules |
| `HEARTBEAT.md` | Session continuity log |

---

## Features

- Checklist before every autonomous multi-step task
- Act first, report after—no mid-task narration
- Full persistent memory via MemPalace (local, no expiry)
- Auto skill generation to `skills/`
- Full git management in codebases
- Traces logged to `logs/traces/run-<uuid>.json`

---

## Testing

```bash
python -m tests.harness      # offline replay
python eval/run_eval.py      # full eval suite
```

Behavior contract: [docs/behavior_contract.md](docs/behavior_contract.md)