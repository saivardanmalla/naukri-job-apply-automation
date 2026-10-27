# JobPilot – authorized job search assistant (Python/Selenium/API/SDET focus)
Run: `cd backend && pip install -r requirements.txt && pytest && uvicorn app.main:app --reload`
or `docker compose up`. Docs at http://localhost:8000/docs.
Safety: never bypasses CAPTCHA/OTP/login; auto-submit is OFF; no fabricated data. Naukri access needs an
authorized channel injected into `NaukriAdapter`, otherwise it stops with "Manual verification required."
