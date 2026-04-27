
## 🎥 Demo Video

[▶️ Watch Demo Video]([https://drive.google.com/your-video-link-here](https://drive.google.com/file/d/1F6FJCrYjFKNlKI1lk9PazDQKcah6OWHW/view?usp=sharing))

# SkillMind — AI-Powered Skill Assessment & Personalised Learning Plan Agent

> Submitted for the **Deccan AI SkillMind Hackathon** by **Sai Krishna Kodam**


---

## 🎯 What Is SkillMind?

A resume tells you what someone *claims* to know — not how well they actually know it.

**SkillMind** is an AI agent that takes a **Job Description** and a **Candidate Resume**, assesses real proficiency on each required skill, identifies gaps, and generates a **personalised learning plan** focused on adjacent skills the candidate can realistically acquire — with curated resources and time estimates.

---

## ✨ Features

- 📋 **Smart JD Parsing** — Extracts all required skills and proficiency levels from any job description
- 👤 **Resume Analysis** — Supports pasting text or uploading **PDF / DOCX / TXT** files
- 🔍 **Gap Assessment** — Scores each skill gap (0–10) with priority ranking
- 📊 **Match Score** — Overall % match between candidate and role
- 🗺️ **Learning Plan** — Week-by-week roadmap with real resources and project deliverables
- 💬 **Chat Interface** — Ask follow-up questions about your results
- 🔄 **Dual LLM Backend** — Works with **Ollama** (local, free) or **Groq** (cloud, free API key)
- 🌐 **Deployable** — One-click deploy to Render or Railway (free tier)

---

## 🖥️ Demo

```
Job Description  +  Resume (PDF/DOCX/text)
                 ↓
         ⚡ SkillMind Agent
                 ↓
  ✅ Match Score: 62%
  🔴 Critical Gaps: Kubernetes, System Design, Redis
  📅 8-Week Personalised Learning Plan
```

---

## 🏗️ Architecture

```
┌──────────────────────────────────────────┐
│           Browser UI                      │
│   Vanilla HTML + CSS + JavaScript         │
│   Real-time streaming via SSE             │
└─────────────────┬────────────────────────┘
                  │ HTTP
┌─────────────────▼────────────────────────┐
│         FastAPI Backend (app.py)          │
│                                          │
│  POST /api/assess      → Full pipeline   │
│  POST /api/parse-resume → PDF/DOCX       │
│  POST /api/chat        → Chat follow-up  │
│  GET  /api/models      → Model list      │
└──────────┬───────────────────┬───────────┘
           │                   │
┌──────────▼──────┐  ┌────────▼────────────┐
│  Ollama (local) │  │   Groq API (cloud)  │
│  tinyllama etc  │  │  llama-3.1-8b-inst  │
│  No key needed  │  │  Free tier          │
└─────────────────┘  └─────────────────────┘
```

### 4-Step Assessment Pipeline

| Step | What Happens | Method |
|------|-------------|--------|
| 1️⃣ Extract Skills | Parse JD → skill list with levels | LLM + regex fallback |
| 2️⃣ Parse Resume | Extract candidate skills + evidence | LLM + keyword fallback |
| 3️⃣ Assess Gaps | Score each skill gap (0–10) | Programmatic comparison |
| 4️⃣ Learning Plan | Week-by-week roadmap + resources | LLM + auto fallback |

### Gap Scoring

```
0–2  → Meets requirement        → priority: low   ✅
3–5  → Partial gap              → priority: medium ⚠️
6–10 → Significant gap          → priority: high  ❌

Match Score = average(100 - gap × 10) across all required skills
```

---

## 🚀 Local Setup

### Prerequisites
- Python 3.11+
- [Ollama](https://ollama.com) installed

### Steps

```bash
# 1. Clone
git clone https://github.com/YOUR_USERNAME/SkillMind.git
cd SkillMind

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start Ollama (separate terminal)
ollama serve
ollama pull tinyllama

# 4. Run
python app.py
```

Open **http://localhost:8000** 🎉

---

## ☁️ Free Cloud Deployment

### Render (Recommended — no credit card)

1. Push code to GitHub
2. Go to [render.com](https://render.com) → **New Web Service**
3. Connect your GitHub repo
4. Set these:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app:app --host 0.0.0.0 --port $PORT`
5. Add environment variable → `GROQ_API_KEY = gsk_...`
6. Click **Deploy** → live URL in ~2 minutes ✅

### Railway

1. Go to [railway.app](https://railway.app) → **Deploy from GitHub**
2. Select repo → Add `GROQ_API_KEY` in Variables
3. Auto-deploys on every push ✅

---

## 🔑 Groq API Setup (Free Cloud LLM)

1. Sign up free at [console.groq.com](https://console.groq.com)
2. Create an API Key (starts with `gsk_`)
3. Create `.env` in project root:

```env
GROQ_API_KEY=gsk_your_key_here
```

The app automatically uses **Groq if the key is set**, otherwise falls back to **Ollama**.

---

## 📁 Project Structure

```
SkillMind/
├── app.py                  # FastAPI backend + AI agent (single file)
├── requirements.txt        # Python dependencies
├── Procfile                # Render / Railway deploy config
├── railway.json            # Railway specific config
├── .gitignore              # Keeps .env out of GitHub
├── .env                    # API keys — never committed ⚠️
└── templates/
    └── index.html          # Full frontend (single file)
```

---

## 🔌 API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web UI |
| `GET` | `/health` | Health check |
| `GET` | `/api/models` | List LLM models |
| `POST` | `/api/assess` | Full assessment (SSE stream) |
| `POST` | `/api/parse-resume` | Upload PDF/DOCX → text |
| `POST` | `/api/chat` | Chat follow-up (SSE stream) |

**POST `/api/assess` payload:**
```json
{
  "job_description": "Senior Full Stack Engineer...",
  "resume": "Candidate resume text...",
  "model": "tinyllama"
}
```

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|-----------|
| AI / LLM | Ollama (local) or Groq API (cloud) |
| Backend | Python 3.11 + FastAPI |
| Streaming | Server-Sent Events (SSE) |
| File Parsing | PyPDF2, python-docx |
| Frontend | Vanilla HTML / CSS / JS |
| HTTP Client | httpx (async) |
| Deployment | Render / Railway (free) |

---

## 📊 Sample Input & Output

**Scenario:** Junior Python engineer applying for Senior FinTech Full Stack role

**Result:**
```
Overall Match Score: 62%

Skill          Candidate → Required     Gap    Priority
─────────────────────────────────────────────────────────
Python         intermediate → advanced   4/10   high
React/TS       intermediate → advanced   5/10   high
Kubernetes     none → intermediate       8/10   high
System Design  beginner → advanced       7/10   high
PostgreSQL     beginner → intermediate   4/10   medium

Strengths:     Python backend, AWS certified, React experience
Critical Gaps: Kubernetes, System Design, Redis, TypeScript

Week 1: TypeScript fundamentals  → Build: Convert project to TS
Week 2: FastAPI async patterns   → Build: Async microservice
Week 3: PostgreSQL deep dive     → Build: Optimised queries app
Week 4: Docker + Kubernetes      → Build: Containerise app
...
```

---

## 🤝 Contributing

Pull requests are welcome. For major changes, open an issue first to discuss.

---

## 👤 Author

**Sai Krishna Kodam**
- GitHub: [@saikrishnakodam](https://github.com/saikrishnakodam)
- Hackathon: [Deccan AI SkillMind](https://github.com/hackathon-deccan-ai)
