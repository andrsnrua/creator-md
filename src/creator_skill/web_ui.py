from __future__ import annotations

import json
import threading
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .content_project import ContentProject
from .errors import CreatorSkillError

HTML = r"""<!doctype html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Creator MD</title>
  <style>
    :root{color-scheme:dark;--bg:#0b0d12;--panel:#151922;--line:#292f3e;
      --text:#f4f5f7;--muted:#9ba4b5;--accent:#61e7b6;--danger:#ff7a90}
    *{box-sizing:border-box} body{margin:0;background:radial-gradient(circle at
      20% 0,#16233a 0,transparent 34%),var(--bg);color:var(--text);
      font:15px/1.5 system-ui,sans-serif}
    main{max-width:1050px;margin:auto;padding:48px 22px 80px}
    h1{font-size:clamp(38px,7vw,72px);letter-spacing:-.06em;margin:0}
    .lead{color:var(--muted);font-size:18px;max-width:680px;margin:8px 0 32px}
    .grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}
    .card{background:color-mix(in srgb,var(--panel) 92%,transparent);
      border:1px solid var(--line);border-radius:18px;padding:22px;
      box-shadow:0 16px 50px #0005}
    label{display:block;color:var(--muted);font-size:13px;margin:14px 0 6px}
    input{width:100%;border:1px solid var(--line);border-radius:10px;
      background:#0d1119;color:var(--text);padding:12px;font:inherit}
    .row{display:grid;grid-template-columns:1fr 120px;gap:12px}
    .actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}
    button{border:0;border-radius:10px;padding:11px 16px;background:var(--accent);
      color:#07130f;font-weight:750;cursor:pointer}
    button.secondary{background:#252c39;color:var(--text)}
    button:disabled{opacity:.45;cursor:wait}
    .stats{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-top:16px}
    .stat{background:#0d1119;border:1px solid var(--line);border-radius:12px;padding:14px}
    .stat b{display:block;font-size:25px}.stat span{color:var(--muted);font-size:12px}
    #message{min-height:26px;color:var(--muted)} .error{color:var(--danger)!important}
    pre{white-space:pre-wrap;word-break:break-word;background:#090b10;
      border:1px solid var(--line);border-radius:14px;padding:20px;
      max-height:560px;overflow:auto;color:#d9deea}
    .wide{grid-column:1/-1} a{color:var(--accent)}
    @media(max-width:760px){.grid{grid-template-columns:1fr}.wide{grid-column:auto}}
  </style>
</head>
<body><main>
  <h1>Creator MD</h1>
  <p class="lead">TikTok → transcripción local → un solo Markdown. El historial
  recuerda lo procesado y continúa sin repetir videos.</p>
  <div class="grid">
    <section class="card">
      <h2>Nueva extracción</h2>
      <label>Perfil público de TikTok</label>
      <input id="profile" value="https://www.tiktok.com/@sebastian_boggiano">
      <div class="row">
        <div><label>Nombre del proyecto</label>
          <input id="project" value="sebastian-boggiano-expert"></div>
        <div><label>Videos</label><input id="count" type="number" min="1" value="3"></div>
      </div>
      <div class="actions">
        <button id="extract" onclick="startJob('extract')">Extraer videos</button>
        <button class="secondary" id="continue" onclick="startJob('continue')">Continuar</button>
        <button class="secondary" onclick="loadStatus()">Ver estado</button>
      </div>
      <p id="message">Listo para trabajar sin API.</p>
    </section>
    <section class="card">
      <h2>Estado</h2>
      <div class="stats">
        <div class="stat"><b id="completed">—</b><span>Completados</span></div>
        <div class="stat"><b id="pending">—</b><span>Pendientes</span></div>
        <div class="stat"><b id="failed">—</b><span>Fallidos</span></div>
      </div>
      <p><b>Siguiente video:</b> <span id="next">—</span></p>
      <p><b>Archivo:</b> <a id="download" href="#" target="_blank">Markdown acumulado</a></p>
    </section>
    <section class="card wide">
      <h2>Contenido generado</h2>
      <pre id="preview">Pulsa “Ver estado” para cargar el Markdown existente.</pre>
    </section>
  </div>
<script>
const $=id=>document.getElementById(id);
function values(){return {profile:$('profile').value.trim(),
  project:$('project').value.trim(),count:Number($('count').value)}}
function busy(on){$('extract').disabled=on;$('continue').disabled=on}
function message(text,error=false){$('message').textContent=text;
  $('message').className=error?'error':''}
async function request(url,options){const r=await fetch(url,options);
  const data=await r.json();if(!r.ok)throw new Error(data.error||'Error');return data}
async function startJob(action){
  busy(true);message('Procesando en segundo plano… puede tardar varios minutos.');
  try{const job=await request('/api/'+action,{method:'POST',
    headers:{'Content-Type':'application/json'},body:JSON.stringify(values())});
    poll(job.job_id)}catch(e){busy(false);message(e.message,true)}
}
async function poll(id){
  try{const job=await request('/api/job?id='+encodeURIComponent(id));
    if(job.status==='running'){setTimeout(()=>poll(id),1500);return}
    busy(false);if(job.status==='failed'){message(job.error,true);return}
    message('Listo: '+job.result.processed_this_run+' videos procesados.');
    render(job.result);loadPreview()
  }catch(e){busy(false);message(e.message,true)}
}
async function loadStatus(){
  message('Consultando estado…');
  try{const data=await request('/api/status?project='+encodeURIComponent(values().project));
    render(data);message('Estado actualizado.');loadPreview()}
  catch(e){message(e.message,true)}
}
function render(data){$('completed').textContent=data.completed;
  $('pending').textContent=data.pending;$('failed').textContent=data.failed.length;
  $('next').textContent=data.next_video_id||'ninguno';
  $('download').href='/markdown?project='+encodeURIComponent(data.project)}
async function loadPreview(){
  const r=await fetch('/markdown?project='+encodeURIComponent(values().project));
  $('preview').textContent=r.ok?await r.text():'Todavía no existe un Markdown.';
}
window.addEventListener('load',loadStatus);
</script></main></body></html>"""


class JobStore:
    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.jobs: dict[str, dict] = {}
        self.lock = threading.Lock()

    def start(self, action: str, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        with self.lock:
            self.jobs[job_id] = {"status": "running"}
        threading.Thread(
            target=self._run,
            args=(job_id, action, payload),
            daemon=True,
        ).start()
        return job_id

    def _run(self, job_id: str, action: str, payload: dict) -> None:
        try:
            project = str(payload.get("project", "")).strip()
            count = int(payload.get("count", 0))
            content = ContentProject(self.workspace_root, project)
            if action == "extract":
                result = content.start(str(payload.get("profile", "")), count)
            else:
                result = content.continue_from_history(count)
            record = {"status": "completed", "result": result}
        except (CreatorSkillError, OSError, TypeError, ValueError) as exc:
            record = {"status": "failed", "error": str(exc)}
        with self.lock:
            self.jobs[job_id] = record

    def get(self, job_id: str) -> dict | None:
        with self.lock:
            return self.jobs.get(job_id)


def make_handler(workspace_root: Path) -> type[BaseHTTPRequestHandler]:
    jobs = JobStore(workspace_root)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            request = urlsplit(self.path)
            query = parse_qs(request.query)
            if request.path == "/":
                body = HTML.encode()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if request.path == "/api/job":
                job = jobs.get(query.get("id", [""])[0])
                self._json(
                    job or {"error": "Trabajo no encontrado"},
                    HTTPStatus.OK if job else HTTPStatus.NOT_FOUND,
                )
                return
            project_name = query.get("project", [""])[0]
            try:
                project = ContentProject(workspace_root, project_name)
                if request.path == "/api/status":
                    self._json(project.status())
                    return
                if request.path == "/markdown":
                    project.export()
                    output = project.combined_output
                    if not output.exists():
                        raise CreatorSkillError("Todavía no existe el Markdown")
                    body = output.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/markdown; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
            except (CreatorSkillError, OSError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def do_POST(self) -> None:
            request = urlsplit(self.path)
            action = request.path.removeprefix("/api/")
            if action not in {"extract", "continue"}:
                self._json({"error": "Ruta no encontrada"}, HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                job_id = jobs.start(action, payload)
                self._json({"job_id": job_id}, HTTPStatus.ACCEPTED)
            except (json.JSONDecodeError, TypeError, ValueError) as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    return Handler


def serve(
    workspace_root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(workspace_root.resolve()))
    print(f"Creator MD disponible en http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
