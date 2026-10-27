from app.scoring import score_job
from app.dedupe import Deduper
from app.adapters import NaukriAdapter, ManualVerificationRequired
import pytest

def test_top_match():
    m = score_job("Senior Python SDET", "Python Selenium PyTest REST API Jenkins CI/CD, 5-8 years", "Bangalore")
    assert m.score >= 90 and m.priority == "APPLY_FIRST"

def test_java_dev_is_low():
    assert score_job("Java Spring Boot Developer", "microservices, 5-8 years", "Bangalore").score < 50

def test_java_selenium_medium_not_rejected():
    assert 40 <= score_job("QA Automation Engineer", "Java Selenium TestNG 5-8 years", "Bangalore").score < 85

def test_dedupe():
    d = Deduper(); j = {"company": "Acme", "title": "SDET", "location": "Pune", "url": "u1"}
    assert not d.is_duplicate(j); d.add(j); assert d.is_duplicate({**j, "url": "u2"})

def test_naukri_stops_without_authorization():
    with pytest.raises(ManualVerificationRequired): NaukriAdapter().fetch("python")
