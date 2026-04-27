"""
Catalyst — AI-Powered Skill Assessment Agent
Supports: Ollama (local) + Groq (free cloud API)
Run locally:  python app.py
Deploy free:  Railway / Render with GROQ_API_KEY env var
"""

import json
import re
import httpx
import io
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Config ───────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL = "http://localhost:11434"
GROQ_API_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "")   # set this env var for cloud deploy
TEMPLATES_DIR   = Path(__file__).parent / "templates"

# ─── File Parsers ─────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
        return "\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except Exception as e:
        return f"[PDF parse error: {e}]"

def extract_text_from_docx(file_bytes: bytes) -> str:
    try:
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
    except Exception as e:
        return f"[DOCX parse error: {e}]"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class SkillAssessment:
    skill: str
    required_level: str
    assessed_level: str
    confidence: int
    evidence: str
    gap_score: int
    priority: str

@dataclass
class LearningResource:
    title: str
    type: str
    url: str
    duration: str
    level: str
    free: bool
    description: str

@dataclass
class LearningMilestone:
    week: int
    goal: str
    resources: list
    deliverable: str

@dataclass
class AssessmentResult:
    job_title: str
    candidate_name: str
    overall_match_score: int
    skills: list
    strengths: list
    critical_gaps: list
    learning_plan: list
    total_weeks: int
    summary: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

# ─── LLM Client (Ollama + Groq) ───────────────────────────────────────────────

class LLMClient:
    """
    Unified client that uses Groq if GROQ_API_KEY is set, otherwise Ollama.
    """

    def _use_groq(self):
        return bool(GROQ_API_KEY)

    async def chat_stream(self, model, messages, system=""):
        if self._use_groq():
            async for token in self._groq_stream(messages, system):
                yield token
        else:
            async for token in self._ollama_stream(model, messages, system):
                yield token

    async def chat_complete(self, model, messages, system=""):
        full = ""
        async for token in self.chat_stream(model, messages, system):
            full += token
        return full

    # ── Groq ────────────────────────────────────────────────────────────────

    def _trim_messages(self, messages, system="", max_chars=1500):
        """Trim message content so total chars stay within Groq limits."""
        msgs = []
        if system:
            msgs.append({"role": "system", "content": system[:500]})
        for m in messages:
            content = m.get("content", "")
            if len(content) > max_chars:
                content = content[:max_chars] + "\n\n[truncated]"
            msgs.append({"role": m["role"], "content": content})
        return msgs

    async def _groq_stream(self, messages, system=""):
        msgs = self._trim_messages(messages, system)
        payload = {
            "model": "llama-3.1-8b-instant",
            "messages": msgs,
            "stream": True,
            "temperature": 0.1,
            "max_tokens": 512,
        }
        headers = {
            "Authorization": f"Bearer {GROQ_API_KEY}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", GROQ_API_URL, json=payload, headers=headers) as resp:
                if resp.status_code != 200:
                    error_body = await resp.aread()
                    raise Exception(f"Groq {resp.status_code}: {error_body.decode()[:300]}")
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line or line == "data: [DONE]":
                        continue
                    if line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            token = data["choices"][0]["delta"].get("content", "")
                            if token:
                                yield token
                        except Exception:
                            continue

    # ── Ollama ──────────────────────────────────────────────────────────────

    async def _ollama_stream(self, model, messages, system=""):
        payload = {"model": model, "messages": messages, "stream": True, "options": {"temperature": 0.1}}
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=300) as client:
            async with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.strip():
                        try:
                            data = json.loads(line)
                            if token := data.get("message", {}).get("content", ""):
                                yield token
                            if data.get("done"):
                                break
                        except Exception:
                            continue

    async def list_models(self):
        if self._use_groq():
            return ["llama3-8b-8192 (Groq)", "llama3-70b-8192 (Groq)", "mixtral-8x7b-32768 (Groq)"]
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
                return [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            return ["tinyllama"]

    def backend_name(self):
        return "Groq (cloud)" if self._use_groq() else "Ollama (local)"

# ─── Agent ────────────────────────────────────────────────────────────────────

class SkillAssessmentAgent:
    def __init__(self):
        self.llm = LLMClient()
        self.sessions = {}

    def _extract_json(self, text):
        text = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        for attempt in [text, re.sub(r",\s*([}\]])", r"\1", text).replace("'", '"')]:
            try:
                return json.loads(attempt)
            except Exception:
                pass
            try:
                m = re.search(r"\{.*\}", attempt, re.DOTALL)
                if m:
                    return json.loads(m.group())
            except Exception:
                pass
        return None

    def _fallback_skills_from_jd(self, jd):
        known = ["Python","JavaScript","TypeScript","React","Node.js","FastAPI","Django","Flask",
                 "PostgreSQL","MySQL","MongoDB","Redis","Docker","Kubernetes","AWS","Azure","GCP",
                 "Git","REST","GraphQL","Microservices","CI/CD","Linux","Machine Learning","SQL",
                 "HTML","CSS","Java","C++","Go","Vue","Angular","System Design","Agile"]
        found = [{"skill": s, "category": "technical", "required_level": "intermediate", "mandatory": True}
                 for s in known if s.lower() in jd.lower()]
        m = re.search(r"(senior|junior|lead)?\s*(software|full.?stack|backend|frontend|data|devops)?\s*(engineer|developer|scientist|architect)", jd, re.IGNORECASE)
        return {"job_title": m.group(0).strip().title() if m else "Software Engineer", "skills": found[:10]}

    def _fallback_skills_from_resume(self, resume):
        known = ["Python","JavaScript","TypeScript","React","Node.js","FastAPI","Django","Flask",
                 "PostgreSQL","MySQL","MongoDB","Redis","Docker","Kubernetes","AWS","Git","SQL","HTML","CSS"]
        found = [{"skill": s, "level": "intermediate", "evidence": "Mentioned in resume"}
                 for s in known if s.lower() in resume.lower()]
        lines = [l.strip() for l in resume.strip().split("\n") if l.strip()]
        return {"candidate_name": lines[0] if lines else "Candidate", "years_experience": 2,
                "skills": found, "education": [], "highlights": []}

    async def list_models(self):
        return await self.llm.list_models()

    async def extract_required_skills(self, jd, model):
        prompt = f"""Extract required skills from this job description as JSON only.

{jd[:1500]}

Reply ONLY with JSON like this:
{{"job_title": "Role Name", "skills": [{{"skill": "Python", "category": "technical", "required_level": "advanced", "mandatory": true}}]}}"""
        response = await self.llm.chat_complete(model, [{"role": "user", "content": prompt}])
        result = self._extract_json(response)
        return result if result and "skills" in result else self._fallback_skills_from_jd(jd)

    async def parse_resume(self, resume, model):
        prompt = f"""Extract candidate skills from this resume as JSON only.

{resume[:1500]}

Reply ONLY with JSON like this:
{{"candidate_name": "Full Name", "years_experience": 2, "skills": [{{"skill": "Python", "level": "intermediate", "evidence": "used at job"}}], "education": ["B.Tech CS"], "highlights": ["achievement"]}}"""
        response = await self.llm.chat_complete(model, [{"role": "user", "content": prompt}])
        result = self._extract_json(response)
        return result if result and "skills" in result else self._fallback_skills_from_resume(resume)

    async def assess_gaps(self, required_skills, candidate_skills, model):
        req  = {s["skill"].lower(): s for s in required_skills}
        cand = {s["skill"].lower(): s for s in candidate_skills}
        lvl  = {"none": 0, "beginner": 1, "intermediate": 2, "advanced": 3, "expert": 4}
        assessments, scores = [], []

        for rk, rv in req.items():
            found = next((c for ck, c in cand.items() if rk in ck or ck in rk), None)
            rl = rv.get("required_level", "intermediate")
            rn = lvl.get(rl, 2)
            if found:
                cl  = found.get("level", "beginner")
                cn  = lvl.get(cl, 1)
                gap = max(0, (rn - cn) * 2)
                ev  = found.get("evidence", "Listed in resume")
            else:
                cl, gap, ev = "none", min(10, rn * 2 + 2), "Not found in resume"

            pri = "high" if gap >= 6 else "medium" if gap >= 3 else "low"
            scores.append(max(0, 100 - gap * 10))
            assessments.append(SkillAssessment(skill=rv["skill"], required_level=rl,
                assessed_level=cl, confidence=80 if found else 95,
                evidence=ev, gap_score=gap, priority=pri))

        overall = int(sum(scores) / len(scores)) if scores else 50
        return assessments, {
            "overall_match_score": overall,
            "strengths":     [a.skill for a in assessments if a.gap_score <= 2][:3],
            "critical_gaps": [a.skill for a in assessments if a.gap_score >= 6][:4],
        }

    async def run_full_assessment(self, job_description, resume, model):
        yield {"type": "progress", "step": 1, "message": f"Extracting skills via {self.llm.backend_name()}..."}
        try:
            jd_data = await self.extract_required_skills(job_description, model)
        except Exception as e:
            yield {"type": "error", "message": f"LLM error: {e}"}
            return

        required_skills = jd_data.get("skills", [])
        job_title       = jd_data.get("job_title", "Software Engineer")
        if not required_skills:
            yield {"type": "error", "message": "Could not extract skills."}
            return
        yield {"type": "skills_extracted", "job_title": job_title, "skills": required_skills, "count": len(required_skills)}

        yield {"type": "progress", "step": 2, "message": "Parsing resume..."}
        try:
            candidate_data = await self.parse_resume(resume, model)
        except Exception as e:
            yield {"type": "error", "message": f"Resume parse error: {e}"}
            return
        yield {"type": "resume_parsed",
               "candidate_name":  candidate_data.get("candidate_name", "Candidate"),
               "years_experience": candidate_data.get("years_experience", 0),
               "skills_found":    len(candidate_data.get("skills", []))}

        yield {"type": "progress", "step": 3, "message": "Assessing skill gaps..."}
        try:
            assessments, gap_data = await self.assess_gaps(
                required_skills, candidate_data.get("skills", []), model)
        except Exception as e:
            yield {"type": "error", "message": f"Gap assessment error: {e}"}
            return
        yield {"type": "assessment_complete",
               "overall_match_score": gap_data["overall_match_score"],
               "strengths":     gap_data["strengths"],
               "critical_gaps": gap_data["critical_gaps"],
               "assessments":   [asdict(a) for a in assessments]}

        yield {"type": "progress", "step": 4, "message": "Generating personalised learning plan..."}
        gaps      = [a for a in assessments if a.gap_score > 2][:5]
        gap_list  = ", ".join(g.skill for g in gaps) or "core skills"
        first     = gaps[0].skill if gaps else "core skills"
        prompt = f"""Learning plan JSON for {job_title}. Top gaps: {gap_list[:200]}.
Reply ONLY with JSON:
{{"total_weeks":4,"summary":"Plan to bridge gaps","milestones":[{{"week":1,"goal":"Learn {first}","resources":[{{"title":"Docs","type":"tutorial","url":"https://google.com","duration":"5 hours","level":"beginner","free":true,"description":"Start here"}}],"deliverable":"Small project"}}]}}"""

        plan_text = ""
        async for token in self.llm.chat_stream(model, [{"role": "user", "content": prompt}]):
            plan_text += token
            yield {"type": "plan_token", "token": token}

        plan_data  = self._extract_json(plan_text)
        milestones = []

        if plan_data and "milestones" in plan_data:
            for m in plan_data["milestones"]:
                resources = []
                for r in m.get("resources", []):
                    try:
                        resources.append(LearningResource(
                            title=r.get("title","Resource"), type=r.get("type","tutorial"),
                            url=r.get("url","https://google.com"), duration=r.get("duration","5 hours"),
                            level=r.get("level","beginner"), free=r.get("free", True),
                            description=r.get("description",""),
                        ))
                    except Exception:
                        pass
                milestones.append(LearningMilestone(week=m.get("week",1), goal=m.get("goal",""),
                                                    resources=resources, deliverable=m.get("deliverable","")))
        else:
            for i, a in enumerate(gaps, 1):
                milestones.append(LearningMilestone(
                    week=i, goal=f"Improve {a.skill} from {a.assessed_level} to {a.required_level}",
                    resources=[LearningResource(
                        title=f"Learn {a.skill}", type="tutorial",
                        url=f"https://www.google.com/search?q=learn+{a.skill.replace(' ','+')}+tutorial",
                        duration="8 hours", level="beginner", free=True,
                        description=f"Focus on {a.skill} to close the gap.")],
                    deliverable=f"Build a small project using {a.skill}"))

        result = AssessmentResult(
            job_title=job_title,
            candidate_name=candidate_data.get("candidate_name","Candidate"),
            overall_match_score=gap_data["overall_match_score"],
            skills=assessments, strengths=gap_data["strengths"],
            critical_gaps=gap_data["critical_gaps"], learning_plan=milestones,
            total_weeks=len(milestones),
            summary=(plan_data.get("summary","") if plan_data else "") or f"Plan to become {job_title}",
        )
        yield {"type": "final_result", "result": asdict(result)}
        yield {"type": "done", "message": "Assessment complete!"}

    async def chat(self, session_id, message, model):
        if session_id not in self.sessions:
            self.sessions[session_id] = {"history": [],
                "system": "You are Catalyst, an expert AI career coach. Help candidates understand skill gaps and create learning plans."}
        session = self.sessions[session_id]
        session["history"].append({"role": "user", "content": message})
        response = ""
        async for token in self.llm.chat_stream(model, session["history"], session["system"]):
            response += token
            yield {"type": "token", "token": token}
        session["history"].append({"role": "assistant", "content": response})
        yield {"type": "done", "session_id": session_id}

# ─── FastAPI App ──────────────────────────────────────────────────────────────

app   = FastAPI(title="Catalyst")
agent = SkillAssessmentAgent()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class AssessmentRequest(BaseModel):
    job_description: str
    resume: str
    model: str = "tinyllama"

class ConversationRequest(BaseModel):
    session_id: str
    message: str
    model: str = "tinyllama"

@app.get("/", response_class=HTMLResponse)
async def root():
    return HTMLResponse(content=(TEMPLATES_DIR / "index.html").read_text(encoding="utf-8"))

@app.get("/health")
async def health():
    return {"status": "ok", "backend": agent.llm.backend_name()}

@app.get("/api/models")
async def list_models():
    return {"models": await agent.list_models(), "backend": agent.llm.backend_name()}

@app.post("/api/parse-resume")
async def parse_resume_file(file: UploadFile = File(...)):
    content  = await file.read()
    filename = (file.filename or "").lower()
    if filename.endswith(".pdf"):
        text = extract_text_from_pdf(content)
    elif filename.endswith(".docx"):
        text = extract_text_from_docx(content)
    elif filename.endswith(".txt"):
        text = content.decode("utf-8", errors="ignore")
    else:
        return JSONResponse({"error": "Use PDF, DOCX, or TXT."}, status_code=400)
    if not text or len(text.strip()) < 20:
        return JSONResponse({"error": "Could not extract text."}, status_code=400)
    return {"text": text, "filename": file.filename, "chars": len(text)}

@app.post("/api/assess")
async def assess_skills(request: AssessmentRequest):
    async def stream():
        try:
            async for event in agent.run_full_assessment(request.job_description, request.resume, request.model):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache"})

@app.post("/api/chat")
async def chat(request: ConversationRequest):
    async def stream():
        try:
            async for event in agent.chat(request.session_id, request.message, request.model):
                yield f"data: {json.dumps(event)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type':'error','message':str(e)})}\n\n"
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control":"no-cache"})

if __name__ == "__main__":
    backend = "Groq (cloud)" if GROQ_API_KEY else "Ollama (local)"
    print(f"""
╔═══════════════════════════════════════════════╗
║     ⚡ CATALYST — Skill Assessment Agent       ║
║     Backend: {backend:<33}║
╠═══════════════════════════════════════════════╣
║  Then open: http://localhost:8000             ║
╚═══════════════════════════════════════════════╝
""")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")