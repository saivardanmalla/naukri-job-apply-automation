"""Replaceable job sources. Only legitimate/authorized access; never bypass CAPTCHA/OTP/login."""
from abc import ABC, abstractmethod


class ManualVerificationRequired(Exception):
    """Raised when a site asks for CAPTCHA/OTP/login. We STOP and tell the user."""
    message = "Manual verification required."


class JobSource(ABC):
    name = "base"

    @abstractmethod
    def fetch(self, query: str, location: str = "") -> list[dict]: ...


class ManualImportAdapter(JobSource):
    name = "manual"

    def __init__(self, jobs=None): self.jobs = jobs or []

    def fetch(self, query, location=""): return list(self.jobs)


class NaukriAdapter(JobSource):
    """Plug in only an authorized channel (official API/partner feed, or user-exported job alerts).
    No scraping that evades protections is implemented here by design."""
    name = "naukri"

    def __init__(self, client=None): self.client = client  # inject an authorized client

    def fetch(self, query, location=""):
        if self.client is None:
            raise ManualVerificationRequired("No authorized Naukri channel configured. Use ManualImportAdapter "
                                             "or open Naukri yourself and import the jobs.")
        resp = self.client.search(query, location)
        if resp.get("challenge"):  # CAPTCHA / OTP / login
            raise ManualVerificationRequired(ManualVerificationRequired.message)
        return resp["jobs"]


class CompanyCareerAdapter(JobSource):
    name = "career"
    def fetch(self, query, location=""): return []  # implement per-company public feeds


class APIAdapter(JobSource):
    name = "api"
    def fetch(self, query, location=""): return []
