"""Lighthouse (mobile + desktop) against a local server of the built site.

Usage (from the site dir, Python 3.12 with node/npx on PATH):  python scripts/lighthouse.py . ../_screens
Writes lighthouse-mobile.json and lighthouse-desktop.json into the output dir and prints the four scores.
"""
import functools, http.server, socketserver, threading, subprocess, json, sys, os
root = sys.argv[1]; out = sys.argv[2]
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*a): pass
h = socketserver.TCPServer(("127.0.0.1",0), functools.partial(Q, directory=root))
threading.Thread(target=h.serve_forever, daemon=True).start()
url=f"http://127.0.0.1:{h.server_address[1]}/"
res={}
for form in ("mobile","desktop"):
    f=os.path.join(out,f"lighthouse-{form}.json")
    cmd=["npx","-y","lighthouse",url,"--quiet","--output=json",f"--output-path={f}",
         "--chrome-flags=--headless=new","--only-categories=performance,accessibility,best-practices,seo"]
    if form=="desktop": cmd.append("--preset=desktop")
    subprocess.run(cmd, shell=(os.name=="nt"), timeout=300)
    d=json.load(open(f,encoding="utf-8"))
    res[form]={k:round(v["score"]*100) for k,v in d["categories"].items()}
    fails=[a["id"] for a in d["audits"].values() if a.get("score") is not None and a["score"]<0.9 and a.get("scoreDisplayMode") in ("binary","numeric")]
    res[form+"_low"]=fails
print(json.dumps(res,indent=1))
h.shutdown()
