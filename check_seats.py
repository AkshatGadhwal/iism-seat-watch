#!/usr/bin/env python3
"""Check the IISM form for open seats, without a browser. Never submits anything.

  .venv/bin/python check_seats.py              check once: list the schedules offered and their seats
  .venv/bin/python check_seats.py --every 300  check every 5 minutes; stop with a sound + Mac
                                               notification as soon as any schedule has seats

Uses course, level, state and mobile from profile.json. It does what you'd do by hand: open the
form, pick course and level, then each schedule (and your state) and read "Available Seats".
Only Python's standard library is needed.
"""
import argparse
import http.cookiejar
import json
import os
import ssl
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
URL = "https://admission.iismgulmarg.in/admission_form.aspx?mobile={mobile}"


class Form(HTMLParser):
    """Collects the form's fields: inputs (name -> value), selects (name -> selected, options)."""

    def __init__(self, html):
        super().__init__()
        self.fields, self.options, self.ids, self._sel = {}, {}, {}, None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "input" and a.get("name"):
            t = a.get("type", "text").lower()
            if t in ("file", "submit", "button", "image", "reset") or \
                    (t in ("checkbox", "radio") and "checked" not in a):
                return
            self.fields[a["name"]] = a.get("value", "")
            if a.get("id"):
                self.ids[a["id"]] = a.get("value", "")
        elif tag == "select" and a.get("name"):
            self._sel = a["name"]
            self.options[self._sel] = []
            self.fields.setdefault(self._sel, "")
        elif tag == "option" and self._sel:
            self.options[self._sel].append([a.get("value", ""), ""])
            if "selected" in a or len(self.options[self._sel]) == 1:
                self.fields[self._sel] = a.get("value", "")

    def handle_data(self, data):
        if self._sel and self.options[self._sel] and data.strip():
            self.options[self._sel][-1][1] += data.strip()

    def handle_endtag(self, tag):
        if tag == "select":
            self._sel = None

    def real(self, name):  # options except the "Select ..." placeholder
        return [(v, t) for v, t in self.options.get(name, []) if v != "0"]


def tls():
    """python.org Python on a Mac doesn't trust common certificates without certifi."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


class Site:
    def __init__(self, url):
        self.url = url
        self.http = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
            urllib.request.HTTPSHandler(context=tls()))

    def get(self):
        return Form(self._open(urllib.request.Request(self.url)))

    def postback(self, form, name, value):
        """Change one dropdown, the way the page's own onchange does."""
        data = dict(form.fields, **{name: value, "__EVENTTARGET": name, "__EVENTARGUMENT": ""})
        body = urllib.parse.urlencode(data).encode()
        return Form(self._open(urllib.request.Request(self.url, data=body)))

    def _open(self, req):
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh) seat-check")
        with self.http.open(req, timeout=90) as r:
            return r.read().decode("utf-8", "replace")


def match(form, name, wanted):
    w = str(wanted).strip().lower()
    for v, t in form.real(name):
        if t.lower() == w or v.lower() == w:
            return v
    hits = [v for v, t in form.real(name) if w in t.lower()]
    return hits[0] if len(hits) == 1 else None


def check(p):
    """[(schedule text, seats, fee)] for the profile's course + level (+ state)."""
    site = Site(URL.format(mobile=p.get("mobile", "")))
    f = site.get()
    if "ddlCourse" not in f.fields:
        raise RuntimeError("form not on the page (site down or changed)")
    for name, key in (("ddlCourse", "course"), ("ddlCourseLevel", "level")):
        v = match(f, name, p[key])
        if v is None:
            raise RuntimeError(f"{key} {p[key]!r} not offered (options: {[t for _, t in f.real(name)]})")
        f = site.postback(f, name, v)
    results = []
    for sv, st in f.real("ddlScheduleCourse"):
        g = site.postback(f, "ddlScheduleCourse", sv)
        state = match(g, "ddlState", p.get("state", "")) if p.get("state") else None
        if state:
            g = site.postback(g, "ddlState", state)
        results.append((st, g.ids.get("txtAvailableSeat", "?"), g.ids.get("txtCourseFee", "?")))
    return results


def alert(msg):
    """WhatsApp via CallMeBot (if CALLMEBOT_PHONE + CALLMEBOT_APIKEY are set), phone push via
    ntfy (if NTFY_TOPIC is set), and a Mac notification + sound (on a Mac)."""
    phone, key = os.environ.get("CALLMEBOT_PHONE"), os.environ.get("CALLMEBOT_APIKEY")
    if phone and key:
        q = urllib.parse.urlencode({"phone": phone, "text": "IISM: " + msg, "apikey": key})
        try:
            urllib.request.urlopen(f"https://api.callmebot.com/whatsapp.php?{q}", timeout=60,
                                   context=tls())
        except Exception as e:
            print(f"whatsapp failed: {str(e)[:80]}")
    topic = os.environ.get("NTFY_TOPIC")
    if topic:
        req = urllib.request.Request(f"https://ntfy.sh/{topic}", data=msg.encode(), headers={
            "Title": "IISM seats", "Priority": "urgent", "Tags": "rotating_light"})
        try:
            urllib.request.urlopen(req, timeout=30, context=tls())
        except Exception as e:
            print(f"push failed: {e}")
    if sys.platform == "darwin":
        print("\a", end="")
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "IISM seats" '
                        'sound name "Glass"'], capture_output=True)
        subprocess.run(["afplay", "/System/Library/Sounds/Glass.aiff"], capture_output=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--every", type=int, metavar="SEC", help="keep checking (min 120 s) until seats open")
    ap.add_argument("--profile", default=str(ROOT / "profile.json"))
    ap.add_argument("--test-alert", action="store_true", help="send a test notification and exit")
    a = ap.parse_args()
    if a.test_alert:
        alert("Test: IISM seat alerts are working.")
        return 0
    # Settings: profile.json if present; IISM_COURSE / IISM_LEVEL / IISM_STATE / IISM_MOBILE
    # environment variables override it (that's how the GitHub Actions run is configured).
    p = json.loads(Path(a.profile).read_text()) if Path(a.profile).exists() else {}
    for key in ("course", "level", "state", "mobile"):
        p[key] = os.environ.get(f"IISM_{key.upper()}") or p.get(key, "")
    print(f"Checking: {p['course']} / {p['level']} / state {p.get('state') or '(none)'}")

    while True:
        now = f"{datetime.now():%H:%M:%S}"
        try:
            res = check(p)
            open_ = [(s, n) for s, n, _ in res if n.strip().isdigit() and int(n) > 0]
            if not res:
                print(f"{now}  no schedules offered")
            else:
                print(f"{now}  " + "  |  ".join(f"{s}: {n} seats" for s, n, _ in res))
            if open_:
                alert("Seats open: " + ", ".join(f"{s} ({n})" for s, n in open_) + ". Apply now!")
                print(f"\n>>> SEATS OPEN: run ./run.sh now")
                return 3  # non-zero on purpose: a "failed" GitHub run also emails you
        except Exception as e:  # site busy / down: just try again next round
            print(f"{now}  couldn't check: {str(e)[:100]}")
        if not a.every:
            return 0
        time.sleep(max(a.every, 120))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
