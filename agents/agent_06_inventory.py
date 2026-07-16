#!/usr/bin/env python3
"""NeverX006 v2 - The Inventory Agent (Job 73 fleet).

Walks any folder you point him at and reports what is really in there.
Costs nothing to run. Pure Python. No API. No brain rented. Cable bill only.

v2 CHANGE: entry points are now found by READING THE CODE, not guessing
the filename. v1 missed doctor.py and governor.py in NorthFraim because
their names did not match a hint list. v2 looks for the real signal:
    if __name__ == "__main__":
That line is a fact. A filename is an opinion.

Usage:
    python3 agents/agent_06_inventory.py ~/some-old-job
    python3 agents/agent_06_inventory.py            (defaults to current folder)
"""
import os
import sys
import py_compile
from datetime import datetime
from pathlib import Path

SKIP_DIRS = {".git", "venv", "__pycache__", "node_modules", ".cache", "env"}

LANG_BY_EXT = {
    ".py": "Python", ".html": "HTML", ".css": "CSS", ".js": "JavaScript",
    ".md": "Docs", ".txt": "Docs", ".json": "Data", ".yml": "Config",
    ".yaml": "Config", ".sh": "Shell", ".sql": "SQL", ".pdf": "Document",
    ".mp4": "Video", ".png": "Image", ".jpg": "Image", ".db": "Database",
}

NAME_HINTS = ("main", "app", "run", "server", "pipeline", "start", "cli")


class Agent06Inventory:
    """Walks a folder. Reports the truth. Judges nothing it cannot verify."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()
        self.files = []
        self.langs = {}
        self.total_bytes = 0
        self.py_ok = []
        self.py_broken = []
        self.newest = None
        self.oldest = None

    def walk(self):
        if not self.root.is_dir():
            print("STOP: not a folder -> %s" % self.root)
            return False
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                p = Path(dirpath) / name
                try:
                    size = p.stat().st_size
                    mtime = p.stat().st_mtime
                except OSError:
                    continue
                self.files.append(p)
                self.total_bytes += size
                lang = LANG_BY_EXT.get(p.suffix.lower(), "Other")
                self.langs[lang] = self.langs.get(lang, 0) + 1
                if self.newest is None or mtime > self.newest:
                    self.newest = mtime
                if self.oldest is None or mtime < self.oldest:
                    self.oldest = mtime
        return True

    def compile_check(self):
        for p in self.files:
            if p.suffix == ".py":
                try:
                    py_compile.compile(str(p), doraise=True)
                    self.py_ok.append(p)
                except Exception:
                    self.py_broken.append(p)

    def find(self, *names):
        hits = []
        for p in self.files:
            for n in names:
                if p.name.lower().startswith(n.lower()):
                    hits.append(p)
                    break
        return hits

    def _has_main_block(self, p):
        """Read the file. Look for the real launch signal."""
        try:
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                text = f.read()
        except Exception:
            return False
        for line in text.splitlines():
            s = line.strip().replace(" ", "").replace("'", '"')
            if s.startswith('if__name__=="__main__"'):
                return True
        return False

    def entry_points(self):
        """Returns (confirmed, maybes).
        confirmed = code proves it launches.
        maybes    = filename only suggests it. Weaker. Reported separately.
        """
        confirmed = []
        maybes = []
        for p in self.py_ok:
            if self._has_main_block(p):
                confirmed.append(p)
            elif any(h in p.stem.lower() for h in NAME_HINTS):
                maybes.append(p)
        return confirmed, maybes

    def rel(self, p):
        try:
            return str(p.relative_to(self.root))
        except ValueError:
            return str(p)

    def report(self):
        line = "=" * 62
        print(line)
        print("NEVERX006 v2 - INVENTORY REPORT")
        print("FOLDER: %s" % self.root)
        print(line)

        print("\n--- SIZE ---")
        print("Files counted : %d" % len(self.files))
        print("Total size    : %.2f MB" % (self.total_bytes / 1048576.0))

        print("\n--- WHAT IT IS MADE OF ---")
        for lang, count in sorted(self.langs.items(), key=lambda x: -x[1]):
            print("  %-12s %d" % (lang, count))

        print("\n--- DOES THE PYTHON RUN ---")
        print("Compiles clean : %d" % len(self.py_ok))
        print("BROKEN         : %d" % len(self.py_broken))
        for p in self.py_broken:
            print("   !! %s" % self.rel(p))

        print("\n--- PAPERWORK ---")
        readme = self.find("readme")
        license_ = self.find("license", "licence", "copying")
        print("README  : %s" % (self.rel(readme[0]) if readme else "NONE"))
        if license_:
            print("LICENSE : %s  (right-to-sell tag present)" % self.rel(license_[0]))
        else:
            print("LICENSE : NONE  (no license = all rights reserved by default)")

        confirmed, maybes = self.entry_points()

        print("\n--- WHAT YOU ACTUALLY RUN (code-verified) ---")
        if confirmed:
            for p in confirmed:
                print("  -> %s" % self.rel(p))
        else:
            print("  none - no file has an if __name__ == \"__main__\" block")

        if maybes:
            print("\n--- MAYBE (filename hint only, unverified) ---")
            for p in maybes:
                print("  ?  %s" % self.rel(p))

        print("\n--- LAST TOUCHED ---")
        days = None
        if self.newest:
            new = datetime.fromtimestamp(self.newest)
            old = datetime.fromtimestamp(self.oldest)
            days = (datetime.now() - new).days
            print("Newest file : %s  (%d days ago)" % (new.strftime("%Y-%m-%d"), days))
            print("Oldest file : %s" % old.strftime("%Y-%m-%d"))

        print("\n--- X006 VERDICT ---")
        for v in self.verdict(days, confirmed, maybes, license_):
            print("  %s" % v)
        print("\n" + line)

    def verdict(self, days, confirmed, maybes, license_):
        out = []
        if not self.files:
            return ["EMPTY - nothing here."]
        if self.py_broken:
            out.append("BROKEN CODE - %d python file(s) do not compile." % len(self.py_broken))
        elif self.langs.get("Python", 0) > 0:
            out.append("ALL PYTHON COMPILES CLEAN - %d file(s), zero broken." % len(self.py_ok))
        if confirmed:
            out.append("RUNNABLE - %d code-verified entry point(s)." % len(confirmed))
        elif self.langs.get("Python", 0) > 0:
            out.append("NO FRONT DOOR - python here, but nothing launches itself.")
        if maybes:
            out.append("UNVERIFIED - %d file(s) look runnable by name but have no main block." % len(maybes))
        if self.langs.get("HTML", 0) > 0:
            out.append("HAS A STOREFRONT PIECE - html found. A customer could see something.")
        else:
            out.append("NO STOREFRONT - no html. Nothing a customer can look at yet.")
        if not license_:
            out.append("NO LICENSE - fine if it stays yours. Add one before anyone else touches it.")
        if days is not None and days > 180:
            out.append("COLD - untouched %d days. Likely scaffolding or parked." % days)
        elif days is not None and days > 30:
            out.append("PARKED - untouched %d days." % days)
        elif days is not None:
            out.append("WARM - worked on recently.")
        out.append("NOTE: X006 reports facts. The Governor decides what it is worth.")
        return out


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    agent = Agent06Inventory(target)
    if not agent.walk():
        sys.exit(1)
    agent.compile_check()
    agent.report()


if __name__ == "__main__":
    main()
