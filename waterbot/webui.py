"""瀏覽器控制頁。只用標準函式庫，不需要安裝任何東西。

主迴圈留在主執行緒，HTTP 伺服器跑在背景執行緒，兩邊只透過一個
Control 物件溝通（幾個旗標和狀態欄位）。這樣 bot 的邏輯一行都不用改成
非同步，也不會有 macOS GUI 必須在主執行緒的限制。

只綁 127.0.0.1，不對外。寫入類的請求要帶自訂標頭，這樣別的網站
就算知道埠號也沒辦法用一個表單把你的程式停掉。
"""
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

GUARD_HEADER = "X-Waterbot"      # 寫入請求要帶這個，擋掉跨站表單


class Control:
    """主迴圈和網頁共用的狀態。兩邊都只碰這個物件。"""

    def __init__(self):
        self.lock = threading.Lock()
        self.paused = False
        self.stop_requested = False
        self.started_at = time.time()
        self.state = "啟動中"
        self.stage = None
        self.attempts = 0
        self.cleared = []            # [(關卡, 耗時秒, 嘗試次數, 時間字串)]
        self.last_action = ""
        self.last_action_at = None
        self.window = ""
        self.note = ""

    # --- 主迴圈這邊用的 ---
    def update(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)

    def add_clear(self, stage, seconds, attempts):
        with self.lock:
            self.cleared.append({
                "stage": stage, "seconds": round(seconds),
                "attempts": attempts,
                "at": time.strftime("%m/%d %H:%M:%S"),
            })

    def toggle_pause(self):
        with self.lock:
            self.paused = not self.paused
            return self.paused

    # --- 網頁這邊用的 ---
    def snapshot(self):
        with self.lock:
            return {
                "paused": self.paused,
                "stopping": self.stop_requested,
                "state": self.state,
                "stage": self.stage,
                "attempts": self.attempts,
                "cleared": list(self.cleared),
                "last_action": self.last_action,
                "last_action_at": self.last_action_at,
                "window": self.window,
                "note": self.note,
                "uptime": int(time.time() - self.started_at),
            }


PAGE = """<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>瘋狂水世界 自動刷關</title>
<style>
  :root{--bg:#f6f7f9;--card:#fff;--ink:#1b1d21;--dim:#6b7280;--line:#e3e6ea;
        --ok:#0f9d58;--warn:#e8a33d;--stop:#d64545;--accent:#2f6fed}
  @media (prefers-color-scheme:dark){:root{--bg:#15171a;--card:#1e2126;
        --ink:#e8eaed;--dim:#9aa0a6;--line:#2c3037}}
  *{box-sizing:border-box}
  body{margin:0;padding:20px;background:var(--bg);color:var(--ink);
       font:15px/1.6 -apple-system,"PingFang TC","Helvetica Neue",sans-serif}
  .wrap{max-width:620px;margin:0 auto}
  h1{font-size:19px;margin:0 0 16px}
  .card{background:var(--card);border:1px solid var(--line);border-radius:12px;
        padding:18px;margin-bottom:14px}
  .big{font-size:28px;font-weight:600;letter-spacing:-.01em}
  .dim{color:var(--dim);font-size:13px}
  .row{display:flex;justify-content:space-between;align-items:baseline;gap:12px}
  .dot{display:inline-block;width:9px;height:9px;border-radius:50%;
       margin-right:7px;vertical-align:middle}
  .run{background:var(--ok)} .hold{background:var(--warn)} .off{background:var(--stop)}
  button{font:inherit;font-weight:500;padding:11px 18px;border-radius:9px;
         border:1px solid var(--line);background:var(--card);color:var(--ink);
         cursor:pointer}
  button:hover{border-color:var(--accent)}
  button.primary{background:var(--accent);border-color:var(--accent);color:#fff}
  button.danger{color:var(--stop)}
  button:disabled{opacity:.45;cursor:default}
  .btns{display:flex;gap:10px}
  table{width:100%;border-collapse:collapse;font-size:14px}
  th,td{text-align:left;padding:7px 4px;border-bottom:1px solid var(--line)}
  th{color:var(--dim);font-weight:500;font-size:12px}
  td.num{font-variant-numeric:tabular-nums}
  .empty{color:var(--dim);font-size:14px;padding:6px 0}
</style></head><body><div class="wrap">
<h1>瘋狂水世界 自動刷關</h1>

<div class="card">
  <div class="row">
    <div><span id="dot" class="dot run"></span><span id="state" class="big">—</span></div>
    <div class="dim" id="uptime"></div>
  </div>
  <div class="dim" id="detail" style="margin-top:6px"></div>
</div>

<div class="card btns">
  <button id="toggle" class="primary">暫停</button>
  <button id="stop" class="danger">結束</button>
</div>

<div class="card">
  <div class="row" style="margin-bottom:10px">
    <strong style="font-size:15px">通關紀錄</strong>
    <span class="dim" id="count"></span>
  </div>
  <div id="list"></div>
</div>

<p class="dim" id="win"></p>
</div><script>
const H={'X-Waterbot':'1','Content-Type':'application/json'};
const $=id=>document.getElementById(id);
function dur(s){if(s<60)return s+'秒';const m=Math.floor(s/60),r=s%60;
  if(m<60)return r?m+'分'+r+'秒':m+'分';const h=Math.floor(m/60);
  return (m%60)?h+'小時'+(m%60)+'分':h+'小時';}
async function send(p){await fetch('/api/'+p,{method:'POST',headers:H});refresh();}
$('toggle').onclick=()=>send($('toggle').dataset.on==='1'?'pause':'resume');
$('stop').onclick=()=>{if(confirm('確定要結束嗎？'))send('stop');};
async function refresh(){
  let d;try{d=await(await fetch('/api/state',{headers:H})).json();}
  catch(e){$('state').textContent='已離線';$('dot').className='dot off';
    $('detail').textContent='程式已經結束，可以關掉這一頁了。';
    $('toggle').disabled=$('stop').disabled=true;return;}
  const paused=d.paused, stopping=d.stopping;
  $('state').textContent=stopping?'收工中':(paused?'已暫停':(d.state||'—'));
  $('dot').className='dot '+(stopping?'off':(paused?'hold':'run'));
  $('toggle').textContent=paused?'繼續':'暫停';
  $('toggle').dataset.on=paused?'0':'1';
  $('toggle').className=paused?'primary':'';
  const bits=[];
  if(d.stage)bits.push('第 '+d.stage+' 關');
  if(d.attempts)bits.push('這一關已試 '+d.attempts+' 次');
  if(d.last_action)bits.push('剛才：'+d.last_action);
  if(paused)bits.length=0,bits.push('它完全停住了，你可以自己操作遊戲。');
  if(d.note)bits.push(d.note);
  $('detail').textContent=bits.join('　·　');
  $('uptime').textContent='已執行 '+dur(d.uptime);
  $('win').textContent=d.window?'盯著：'+d.window:'';
  const c=d.cleared||[];
  $('count').textContent=c.length?('這次通過 '+c.length+' 關'):'';
  $('list').innerHTML=c.length?
    '<table><tr><th>關卡</th><th>通過時間</th><th>花了多久</th><th>試了幾次</th></tr>'+
    c.slice().reverse().map(r=>'<tr><td class="num">'+r.stage+'</td><td class="num">'+
      r.at+'</td><td class="num">'+dur(r.seconds)+'</td><td class="num">'+
      r.attempts+' 次</td></tr>').join('')+'</table>'
    :'<div class="empty">還沒通過新的關卡。</div>';
}
refresh();setInterval(refresh,1000);
</script></body></html>"""


def _handler(ctl):
    class H(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):       # 不要把每個請求都印到終端機
            pass

        def _send(self, code, body, ctype):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self._send(200, PAGE, "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._send(200, json.dumps(ctl.snapshot()),
                                  "application/json")
            self._send(404, "not found", "text/plain; charset=utf-8")

        def do_POST(self):
            # 擋掉跨站表單：它們沒辦法帶自訂標頭
            if not self.headers.get(GUARD_HEADER):
                return self._send(403, "forbidden", "text/plain")
            if self.path == "/api/pause":
                ctl.update(paused=True)
            elif self.path == "/api/resume":
                ctl.update(paused=False)
            elif self.path == "/api/stop":
                ctl.update(stop_requested=True)
            else:
                return self._send(404, "not found", "text/plain")
            self._send(200, json.dumps({"ok": True}), "application/json")
    return H


def start(ctl, port=8777, tries=10):
    """啟動背景伺服器，回傳網址；找不到可用的埠就回 None。"""
    for p in range(port, port + tries):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", p), _handler(ctl))
        except OSError:
            continue
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{p}", srv
    return None, None
