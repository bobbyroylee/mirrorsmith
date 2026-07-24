"""Local web UI for mirrorsmith — zero-dependency (stdlib http.server).

Serves a single page that lists your characters, imports one on demand, and
renders the full build sheet (tree totals + gear + gems). Data loads (tree,
stat translations) happen once at first use and are cached for the process.

Run via ``scripts/serve.py``. Binds to 127.0.0.1 only — it reads your local
POESESSID and must never be exposed off-machine.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .build import _CATEGORIES, analyze_full
from .data import account
from .data.stats import StatTranslator
from .data.tree import PassiveTree

CATEGORY_ORDER = [c for c, _ in _CATEGORIES] + ["Other"]


@lru_cache(maxsize=1)
def _tree() -> PassiveTree:
    return PassiveTree.load()


@lru_cache(maxsize=1)
def _translator() -> StatTranslator:
    return StatTranslator.load()


def _poesessid() -> str | None:
    if os.environ.get("POESESSID"):
        return os.environ["POESESSID"].strip()
    f = Path.home() / ".mirrorsmith" / "poesessid"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def _categorized(rendered: dict[str, list[str]]) -> list[dict[str, object]]:
    return [{"name": c, "lines": rendered[c]} for c in CATEGORY_ORDER if rendered.get(c)]


def build_payload(acct: str, character: str) -> dict[str, object]:
    """Import + analyze one character into the JSON the frontend renders."""
    imported = account.fetch_character(acct, character, "pc", _poesessid())
    fb = analyze_full(imported, _tree(), _translator())
    meta = (imported.get("items", {}) or {}).get("character", {})
    a = fb.tree
    return {
        "character": {
            "name": meta.get("name", character),
            "class": meta.get("class"),
            "level": meta.get("level"),
            "league": meta.get("league"),
        },
        "tree": {
            "nodes": a.points_counted,
            "stats": len(a.totals),
            "categories": _categorized(a.rendered),
            "cluster": a.cluster_lines,
        },
        "gear": {"categories": _categorized(fb.gear)},
        "gems": {
            "active": [{"name": g.name, "level": g.level, "quality": g.quality}
                       for g in fb.gems if not g.support],
            "support": [{"name": g.name, "level": g.level, "quality": g.quality}
                        for g in fb.gems if g.support],
        },
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_a):  # keep the console quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: object, code: int = 200) -> None:
        self._send(code, json.dumps(obj).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/":
            self._send(200, INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            return
        if url.path == "/api/characters":
            try:
                chars = account.get_characters("", "pc", _poesessid())
                self._json([{"name": c.get("name"), "level": c.get("level"),
                             "class": c.get("class"), "league": c.get("league")}
                            for c in chars])
            except account.AccountError as exc:
                self._json({"error": str(exc)}, 502)
            return
        if url.path == "/api/analyze":
            q = parse_qs(url.query)
            acct = (q.get("account", [""])[0]).strip()
            char = (q.get("character", [""])[0]).strip()
            if not char:
                self._json({"error": "character required"}, 400)
                return
            try:
                self._json(build_payload(acct, char))
            except account.AccountError as exc:
                self._json({"error": str(exc)}, 502)
            except Exception as exc:  # noqa: BLE001
                self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
            return
        self._send(404, b"not found", "text/plain")


INDEX_HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mirrorsmith</title>
<style>
:root{
  --bg:#0e1014; --panel:#161a22; --panel2:#1c212b; --line:#262c38;
  --text:#dce1ea; --muted:#8790a1; --gold:#c8a24a; --accent:#6ea8ff;
}
@media (prefers-color-scheme:light){:root{
  --bg:#f4f5f7; --panel:#ffffff; --panel2:#f0f2f5; --line:#e2e6ec;
  --text:#1c2129; --muted:#5d6572; --gold:#a6802f; --accent:#2f6fe0;}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);
  font:14px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif}
header{position:sticky;top:0;background:var(--panel);border-bottom:1px solid var(--line);
  display:flex;gap:14px;align-items:center;padding:12px 20px;z-index:5;flex-wrap:wrap}
.brand{font-weight:700;letter-spacing:.5px}
.brand b{color:var(--gold)}
.brand span{color:var(--muted);font-weight:400;margin-left:8px;font-size:12px}
input,select,button{font:inherit;color:var(--text);background:var(--panel2);
  border:1px solid var(--line);border-radius:8px;padding:7px 10px}
button{cursor:pointer}
button:hover,select:hover{border-color:var(--accent)}
input{width:150px}
.spacer{flex:1}
main{max-width:1200px;margin:0 auto;padding:22px 20px 60px}
.hero{display:flex;align-items:baseline;gap:14px;margin:6px 0 20px;flex-wrap:wrap}
.hero h1{margin:0;font-size:24px}
.hero .cls{color:var(--gold);font-weight:600}
.hero .meta{color:var(--muted);font-size:13px}
.cols{display:grid;grid-template-columns:2fr 2fr 1fr;gap:16px}
@media(max-width:900px){.cols{grid-template-columns:1fr}}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;overflow:hidden}
.card>h2{margin:0;padding:12px 16px;font-size:13px;letter-spacing:.6px;text-transform:uppercase;
  color:var(--muted);border-bottom:1px solid var(--line);background:var(--panel2)}
.card .body{padding:6px 16px 14px}
.cat{margin-top:12px}
.cat h3{margin:0 0 4px;font-size:12px;color:var(--gold);font-weight:600}
.cat ul{list-style:none;margin:0;padding:0}
.cat li{padding:2px 0;border-bottom:1px dashed transparent}
.cat li:hover{border-color:var(--line)}
.count{color:var(--accent);font-variant-numeric:tabular-nums}
.gem{display:flex;justify-content:space-between;gap:8px;padding:4px 0;border-bottom:1px solid var(--line)}
.gem:last-child{border:0}
.gem .lv{color:var(--muted);font-variant-numeric:tabular-nums;font-size:12px}
.gem.sup .nm{color:var(--muted)}
.pill{display:inline-block;background:var(--panel2);border:1px solid var(--line);border-radius:20px;
  padding:2px 10px;margin:2px 4px 2px 0;font-size:12px;color:var(--muted)}
.note{color:var(--muted);font-size:12px;margin-top:22px;padding:12px 14px;border:1px dashed var(--line);border-radius:10px}
#status{color:var(--muted);padding:40px 0;text-align:center}
.err{color:#e06a6a}
</style></head>
<body>
<header>
  <div class="brand"><b>mirror</b>smith <span>PoE build analyzer</span></div>
  <input id="account" placeholder="account#1234" title="your PoE account name">
  <select id="chars"><option value="">— loading characters —</option></select>
  <button id="go">Analyze</button>
  <div class="spacer"></div>
  <button id="reload" title="reload character list">↻</button>
</header>
<main>
  <div id="status">Enter your account name, pick a character, and hit Analyze.</div>
  <div id="out" hidden>
    <div class="hero">
      <h1 id="cName"></h1><div class="cls" id="cCls"></div><div class="meta" id="cMeta"></div>
    </div>
    <div class="cols">
      <div class="card"><h2 id="treeH">Passive Tree</h2><div class="body" id="tree"></div></div>
      <div class="card"><h2>Gear</h2><div class="body" id="gear"></div></div>
      <div class="card"><h2>Gems</h2><div class="body" id="gems"></div></div>
    </div>
    <div class="note">Sources are shown separately — real fused EHP/DPS totals need a
      calculation engine (item mods are local vs global), the next milestone.</div>
  </div>
</main>
<script>
const $=s=>document.querySelector(s);
const acc=$('#account'), sel=$('#chars'), out=$('#out'), status=$('#status');
acc.value=localStorage.getItem('ms_account')||'';
acc.addEventListener('change',()=>localStorage.setItem('ms_account',acc.value.trim()));

function catBlock(cat){
  const lines=cat.lines.map(l=>{
    const m=l.match(/^(\d+)×\s+(.*)$/);
    return m?`<li><span class="count">${m[1]}×</span> ${esc(m[2])}</li>`:`<li>${esc(l)}</li>`;
  }).join('');
  return `<div class="cat"><h3>${esc(cat.name)}</h3><ul>${lines}</ul></div>`;
}
function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}

async function loadChars(){
  sel.innerHTML='<option value="">— loading —</option>';
  try{
    const r=await fetch('/api/characters'); const d=await r.json();
    if(d.error){sel.innerHTML='<option value="">(session error)</option>';status.innerHTML='<span class="err">'+esc(d.error)+'</span>';status.hidden=false;out.hidden=true;return;}
    d.sort((a,b)=>b.level-a.level);
    sel.innerHTML='<option value="">— pick a character —</option>'+
      d.map(c=>`<option value="${esc(c.name)}">${esc(c.name)} · ${c.class} · lvl ${c.level}</option>`).join('');
  }catch(e){sel.innerHTML='<option value="">(no session)</option>';}
}
async function analyze(){
  const character=sel.value; const account=acc.value.trim();
  if(!character){status.textContent='Pick a character first.';status.hidden=false;out.hidden=true;return;}
  status.textContent='Importing '+character+'…';status.hidden=false;out.hidden=true;
  try{
    const r=await fetch('/api/analyze?account='+encodeURIComponent(account)+'&character='+encodeURIComponent(character));
    const d=await r.json();
    if(d.error){status.innerHTML='<span class="err">'+esc(d.error)+'</span>';return;}
    render(d);
  }catch(e){status.innerHTML='<span class="err">'+esc(e)+'</span>';}
}
function render(d){
  $('#cName').textContent=d.character.name;
  $('#cCls').textContent=d.character.class||'';
  $('#cMeta').textContent=`lvl ${d.character.level||'?'} · ${d.character.league||''}`;
  $('#treeH').textContent=`Passive Tree · ${d.tree.nodes} nodes · ${d.tree.stats} stats`;
  let t=d.tree.categories.map(catBlock).join('');
  if(d.tree.cluster&&d.tree.cluster.length) t+=catBlock({name:'Cluster Jewels',lines:d.tree.cluster});
  $('#tree').innerHTML=t||'<p class="meta">no data</p>';
  $('#gear').innerHTML=d.gear.categories.map(catBlock).join('')||'<p class="meta">no gear mods</p>';
  const gem=g=>`<div class="gem"><span class="nm">${esc(g.name)}</span><span class="lv">${g.level?('lv '+g.level):''}${g.quality?(' '+g.quality):''}</span></div>`;
  $('#gems').innerHTML=
    `<div class="cat"><h3>Active (${d.gems.active.length})</h3>${d.gems.active.map(gem).join('')}</div>`+
    `<div class="cat"><h3>Support (${d.gems.support.length})</h3>${d.gems.support.map(g=>gem(g).replace('gem','gem sup')).join('')}</div>`;
  status.hidden=true;out.hidden=false;
}
$('#go').onclick=analyze; $('#reload').onclick=loadChars;
sel.onchange=()=>{if(sel.value)analyze();};
loadChars();
</script>
</body></html>
"""
