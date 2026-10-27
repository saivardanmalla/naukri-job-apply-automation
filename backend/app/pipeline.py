from .adapters import JobSource, ManualVerificationRequired
from .dedupe import Deduper
from .scoring import score_job

QUERIES = ["Python Selenium Automation", "Python SDET", "Python API Automation", "Python Selenium PyTest",
           "SDET Selenium API", "Senior QA Automation Python", "Python Robot Framework", "REST API Automation"]
MIN_SCORE, PREP_SCORE = 70, 85


def run_daily(sources: list[JobSource], seen: Deduper, location="Bangalore", limit=100):
    stats = dict(discovered=0, duplicates=0, below_min=0, relevant=0, needs_manual=[])
    out = []
    for src in sources:
        for q in QUERIES:
            try:
                jobs = src.fetch(q, location)
            except ManualVerificationRequired as e:
                stats["needs_manual"].append(f"{src.name}: {e}"); break
            for j in jobs:
                stats["discovered"] += 1
                if seen.is_duplicate(j): stats["duplicates"] += 1; continue
                seen.add(j)
                m = score_job(j["title"], j.get("description", ""), j.get("location", ""), j.get("experience", ""))
                if m.score < MIN_SCORE: stats["below_min"] += 1; continue  # never pad to reach target
                out.append({**j, "match": m, "prepare": m.score >= PREP_SCORE, "status": "Discovered"})
    out.sort(key=lambda x: -x["match"].score)
    stats["relevant"] = len(out[:limit])
    return out[:limit], stats
