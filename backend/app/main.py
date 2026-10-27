from dataclasses import asdict
from fastapi import FastAPI
from .adapters import ManualImportAdapter
from .dedupe import Deduper
from .pipeline import run_daily
from .scoring import score_job

app = FastAPI(title="JobPilot - authorized job search assistant")
STATE = {"deduper": Deduper(), "jobs": [], "stats": {}, "paused": False, "auto_submit": False}


@app.post("/jobs/import")
def import_jobs(jobs: list[dict]):
    res, stats = run_daily([ManualImportAdapter(jobs)], STATE["deduper"])
    STATE["jobs"] += res; STATE["stats"] = stats
    return stats


@app.get("/jobs")
def list_jobs(min_score: int = 70):
    return [{**{k: v for k, v in j.items() if k != "match"}, "match": asdict(j["match"])}
            for j in STATE["jobs"] if j["match"].score >= min_score]


@app.get("/report")
def report():
    s = [j["match"].score for j in STATE["jobs"]]
    return {**STATE["stats"], "90+": sum(x >= 90 for x in s), "80-89": sum(80 <= x < 90 for x in s),
            "70-79": sum(70 <= x < 80 for x in s), "auto_submit": STATE["auto_submit"]}


@app.post("/score")
def score(job: dict):
    return asdict(score_job(job["title"], job.get("description", ""), job.get("location", ""), job.get("experience", "")))


@app.post("/automation/{action}")
def control(action: str):
    STATE["paused"] = action == "pause"
    return {"paused": STATE["paused"]}  # auto_submit stays OFF unless explicitly enabled
