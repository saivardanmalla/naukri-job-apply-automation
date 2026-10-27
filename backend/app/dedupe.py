import re
from difflib import SequenceMatcher


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def fingerprint(j):
    return f"{norm(j['company'])}|{norm(j['title'])}|{norm(j.get('location',''))}"


class Deduper:
    def __init__(self):
        self.ids, self.urls, self.fps, self.descs = set(), set(), set(), []

    def is_duplicate(self, j):
        if j.get("source_id") and j["source_id"] in self.ids: return True
        if j.get("url") and j["url"] in self.urls: return True
        if fingerprint(j) in self.fps: return True
        d = norm(j.get("description", ""))[:1500]
        return bool(d) and any(SequenceMatcher(None, d, o).ratio() > 0.92 for o in self.descs)

    def add(self, j):
        self.ids.add(j.get("source_id")); self.urls.add(j.get("url")); self.fps.add(fingerprint(j))
        self.descs.append(norm(j.get("description", ""))[:1500])
