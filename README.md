# Poly AI Coworker 🤖

> Multi-Agent AI Sales & Support System — Built with LangGraph.
> Now with **Corporate OS** (Multi-Role Identity Management).

---

## What is this?

**Poly** is a production-grade AI Coworker designed for conversational commerce. She handles the full customer lifecycle — from casual discovery conversations through to confirmed orders — across multiple channels and multiple products.

This repository is a **reusable template** that can be adapted to any product catalog and business.

---

## 🏛️ Corporate OS Architecture

Poly is no longer just a sales bot; she is an organizational intelligent entity that recognizes roles and adjusts her purpose accordingly:

1.  **Owner Mode (Strategist)**: Business intelligence, KPI reporting, and strategic advice for the founder.
2.  **Agent Mode (AI-to-AI)**: Protocol-based, technical, and assertive communication for other AI agents.
3.  **Employee Mode (Operational)**: Task coordination and operational support for the team.
4.  **Customer Mode (Sales)**: Empathy-driven sales and support (the classic Poly).

---

## 🧬 Cloneability & Customization

Poly is designed to be easily "cloned" and personalized for any business using a Seed-based approach.

### 1. The Owner Seed (`config/owner_seed.yaml`)
Use this file to define the initial "DNA" of the clone:
- Owner name and role.
- Primary and secondary business goals.
- Preferred tone and working style.
- Initial instructions for the AI.

### 2. Personality Evolution
Poly's "Soul" is dynamic. While core traits are defined in `config/personality.yaml`, she **learns and evolves** based on your feedback. If you tell her "Be more direct", she updates her long-term memory and adjusts her tone permanently for you.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Framework | FastAPI + LangGraph |
| Orchestration | LangGraph (Multi-Agent State Machine) |
| Identity | Multi-Role Corporate OS (Owner, Employee, Agent, Customer) |
| Memory (Short) | LangGraph Checkpointers (PostgreSQL) |
| Memory (Long) | PostgreSQL via SQLAlchemy |
| RAG / Catalog | Qdrant Vector DB |
| Audio | OpenAI Whisper (STT) |
| Admin Hub | Telegram Bot |
| Containerization | Docker + Docker Compose |

---

## 🚀 Getting Started

### 1. Clone and Configure
```bash
cp .env.example .env
# Fill in your API keys
```

### 2. Personalize your Clone
Edit `config/owner_seed.yaml` with your own information and business goals.

### 3. Start the Ecosystem
```bash
docker compose up
```

### 4. Initialize Poly (Telegram)
Go to your Telegram Admin Bot and run:
- `/init`: This loads the `owner_seed.yaml` into Poly's memory and officially registers you as the **Owner**.
- `/status`: Check that all services (DB, Qdrant, LLM) are active.

---

## 📋 Project Structure

```
.
├── api/               # FastAPI entry point (Webhooks)
├── core/
│   ├── brain/         # LangGraph agents, router & corporate prompts
│   ├── memory/        # DB models, repository & persistent checkpointers
│   └── knowledge/     # RAG (product catalog indexer)
├── channels/          # WhatsApp (Twilio) & Telegram gateways
├── config/            # owner_seed.yaml, personality.yaml, products.yaml
├── infrastructure/    # Dockerfile, docker-compose.yml
└── telegram_runner.py # Standalone runner for the Admin Hub
```

---

## 📈 Roadmap

- [x] **Phase 1**: Project structure, Docker, persistent memory (Postgres).
- [x] **Phase 2**: Multi-agent Sales Flow, RAG catalog (Qdrant).
- [x] **Phase 3**: Corporate OS (Owner/Agent/Employee roles), Identity management.
- [ ] **Phase 4**: Automated analytics reports, broadcast campaigns, Droppi v2 integration.
