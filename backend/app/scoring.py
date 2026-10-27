"""Job match scoring (0-100) using the weights from the spec."""
import re
from dataclasses import dataclass, field

WEIGHTS = dict(python=20, selenium=20, api=20, sdet=15, experience=10, framework=5, cicd=5, location=5)
KW = {
    "python": ["python"],
    "selenium": ["selenium", "webdriver", "ui automation", "web automation", "selenide", "page object", "xpath"],
    "api": ["rest api", "api testing", "api automation", "rest assured", "restassured", "requests", "httpx",
            "postman", "json schema", "oauth", "jwt", "api"],
    "sdet": ["sdet", "qa automation", "test automation", "automation engineer", "software engineer in test",
             "automation test", "quality engineer"],
    "framework": ["pytest", "unittest", "robot framework", "bdd", "page object", "data-driven", "keyword-driven"],
    "cicd": ["jenkins", "ci/cd", "github actions", "git"],
}
CANDIDATE_YEARS = 6
LOCATIONS = {"bangalore": 5, "bengaluru": 5, "remote": 4, "hyderabad": 3, "pune": 3, "chennai": 3,
             "mumbai": 3, "gurugram": 3, "gurgaon": 3, "noida": 3, "delhi": 3}


@dataclass
class Match:
    score: int
    priority: str
    matched: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    breakdown: dict = field(default_factory=dict)
    resume: str = ""
    concerns: list = field(default_factory=list)


def _has(text, words):
    return [w for w in words if re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", text)]


def _experience_fit(text):
    m = re.search(r"(\d+)\s*(?:-|–|to)\s*(\d+)\s*(?:years|yrs|yr)", text)
    if not m:
        m2 = re.search(r"(\d+)\+?\s*(?:years|yrs)", text)
        if not m2:
            return 0.6
        lo, hi = int(m2.group(1)), int(m2.group(1)) + 3
    else:
        lo, hi = int(m.group(1)), int(m.group(2))
    if lo <= CANDIDATE_YEARS <= hi + 1: return 1.0
    if lo - 1 <= CANDIDATE_YEARS <= hi + 2: return 0.7
    if hi >= 3 and hi < CANDIDATE_YEARS: return 0.5  # underestimated JDs
    return 0.1


def priority(score):
    return ("APPLY_FIRST" if score >= 90 else "HIGH" if score >= 80
            else "REVIEW" if score >= 70 else "LOW")


def pick_resume(has):
    if "python" in has and ("selenium" in has or "api" in has): return "A: Python + Selenium + API Automation"
    if "selenide" in has.get("_raw", []) or "java" in has.get("_raw", []): return "C: Java + Selenide + API Automation"
    if "sdet" in has: return "B: SDET + QA Automation"
    return "D: Senior QA Automation"


def score_job(title, description, location="", experience=""):
    text = f"{title} {description} {experience}".lower()
    hits = {k: _has(text, v) for k, v in KW.items()}
    f = {
        "python": 1.0 if hits["python"] else (0.35 if "java" in text and (hits["selenium"] or hits["sdet"]) else 0),
        "selenium": min(1, 0.6 + 0.2 * (len(hits["selenium"]) - 1)) if hits["selenium"] else 0,
        "api": min(1, 0.6 + 0.2 * (len(hits["api"]) - 1)) if hits["api"] else 0,
        "sdet": 1.0 if hits["sdet"] else 0,
        "experience": _experience_fit(text),
        "framework": min(1, len(hits["framework"]) / 2),
        "cicd": min(1, len(hits["cicd"]) / 2),
        "location": max([v for k, v in LOCATIONS.items() if k in location.lower()] + [0]) / 5,
    }
    base = sum(WEIGHTS[k] * f[k] for k in WEIGHTS)
    py, se, api, pt = f["python"] == 1, bool(hits["selenium"]), bool(hits["api"]), "pytest" in text
    bonus = 0
    if py and se and pt: bonus += 4
    if py and se and api: bonus += 6
    if py and api and pt: bonus += 6
    if "sdet" in text and py and se and api: bonus += 8
    if py and "robot framework" in text and se: bonus += 8
    if py and api and "jenkins" in text and "ci/cd" in text: bonus += 6
    score = min(100, round(base + bonus))
    # Non-automation roles (e.g. plain dev) must not score high.
    if not (hits["sdet"] or se or api):
        score = min(score, 45)
    matched = sorted({w for k in ("python", "selenium", "api", "framework", "cicd") for w in hits[k]})
    wanted = ["python", "selenium", "pytest", "rest api", "jenkins", "robot framework"]
    missing = [w for w in wanted if w not in matched and w in text]  # required by JD, not on candidate list
    concerns = []
    if not py: concerns.append("No Python mentioned")
    if f["experience"] < 0.5: concerns.append("Experience range mismatch")
    flags = {"python": py, "selenium": se, "api": api, "sdet": bool(hits["sdet"]), "_raw": ["java"] if "java" in text else []}
    return Match(score, priority(score), matched, missing,
                 {k: round(WEIGHTS[k] * f[k], 1) for k in WEIGHTS} | {"combo_bonus": bonus},
                 pick_resume({k: v for k, v in flags.items() if v}), concerns)
