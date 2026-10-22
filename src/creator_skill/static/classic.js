const byId = (id) => document.getElementById(id);

const state = {
  bootstrap: null,
  preview: null,
  previewSignature: null,
  activeJob: null,
  projectWasEdited: false,
};

function slug(value) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 64);
}

function projectFromUrl(value) {
  try {
    const url = new URL(value);
    const match = url.pathname.match(/@([^/?#]+)/);
    if (match) return slug(match[1]);
    const last = url.pathname.split("/").filter(Boolean).pop();
    return slug(last || "");
  } catch {
    return "";
  }
}

async function request(url, options) {
  const response = await fetch(url, options);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error("La aplicación recibió una respuesta inválida.");
  }
  if (!response.ok) {
    const problem = new Error(data.error || "No se pudo completar la solicitud.");
    problem.status = response.status;
    throw problem;
  }
  return data;
}

function setTab(name) {
  document.querySelectorAll(".tab").forEach((button) => {
    const active = button.dataset.tab === name;
    button.classList.toggle("active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".view").forEach((view) => {
    const active = view.id === `view-${name}`;
    view.classList.toggle("active", active);
    view.hidden = !active;
  });
}

function showError(target, message) {
  target.textContent = message;
  target.hidden = !message;
}

let toastTimer;
function toast(message, error = false) {
  const element = byId("toast");
  element.textContent = message;
  element.classList.toggle("error", error);
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    element.hidden = true;
  }, 4500);
}

function profilePayload() {
  return {
    profile: byId("profileUrl").value.trim(),
    category: byId("profileCategory").value.trim(),
    project: byId("profileProject").value.trim(),
    date_from: byId("dateFrom").value || null,
    date_to: byId("dateTo").value || null,
    scan_limit: Number(byId("scanLimit").value),
  };
}

function profileSignature(payload) {
  return JSON.stringify(payload);
}

function validateProfile(payload) {
  if (!payload.profile) return "Pega la URL de un perfil de TikTok o canal de YouTube.";
  if (!payload.category) return "Escribe o selecciona una categoría.";
  if (!payload.project) return "Escribe el nombre del creador o proyecto.";
  if (!Number.isInteger(payload.scan_limit) || payload.scan_limit < 1 || payload.scan_limit > 1000) {
    return "La cantidad a revisar debe estar entre 1 y 1000.";
  }
  if (payload.date_from && payload.date_to && payload.date_from > payload.date_to) {
    return "La fecha inicial no puede ser posterior a la fecha final.";
  }
  const isTikTok = payload.profile.toLowerCase().includes("tiktok.com");
  const apifyReady = Boolean(state.bootstrap?.integrations?.apify?.configured);
  if (isTikTok && !apifyReady && payload.scan_limit > 10) {
    return "Para revisar más de 10 videos de TikTok, activa el historial en Integraciones.";
  }
  return "";
}

function validateSingle(payload) {
  if (!payload.single_url) return "Pega el enlace de un video de TikTok o YouTube.";
  if (!payload.category) return "Escribe o selecciona una categoría.";
  if (!payload.project) return "Escribe el nombre del creador o proyecto.";
  return "";
}

function resetPreview() {
  state.preview = null;
  state.previewSignature = null;
  byId("selectionEmpty").hidden = false;
  byId("selectionResult").hidden = true;
}

function updatePlatformLimits() {
  const isTikTok = byId("profileUrl").value.toLowerCase().includes("tiktok.com");
  const apifyReady = Boolean(state.bootstrap?.integrations?.apify?.configured);
  const input = byId("scanLimit");
  const notice = byId("tiktokHistoryNotice");
  input.max = isTikTok && !apifyReady ? "10" : "1000";
  if (isTikTok && !apifyReady && Number(input.value) > 10) input.value = "10";
  notice.hidden = !isTikTok || apifyReady;
  byId("scanHelp").textContent = isTikTok
    ? apifyReady
      ? "historial y fechas mediante Apify"
      : "10 recientes · conecta Apify para historial"
    : "publicaciones recientes";
}

function setFormBusy(form, busy) {
  form.querySelectorAll("button, input").forEach((element) => {
    element.disabled = busy;
  });
}

function openJob(title) {
  const panel = byId("jobPanel");
  panel.hidden = false;
  panel.classList.remove("failed");
  byId("jobState").textContent = "Procesando";
  byId("jobTitle").textContent = title;
  byId("jobPercent").textContent = "0%";
  byId("jobBar").style.width = "0%";
  byId("jobLog").textContent = "Preparando tarea…";
}

function renderJob(job) {
  const percent = Math.max(0, Math.min(100, Number(job.percent || 0)));
  byId("jobPercent").textContent = `${percent}%`;
  byId("jobBar").style.width = `${percent}%`;
  byId("jobState").textContent = job.stage === "failed" ? "Error" : job.stage || "Procesando";
  const logs = job.logs || [];
  byId("jobLog").textContent = logs.slice(-6).map((item) => `[${item.time}] ${item.message}`).join("\n");
  byId("jobPanel").classList.toggle("failed", job.status === "failed");
}

async function startJob(action, payload, title) {
  if (state.activeJob) throw new Error("Ya hay una tarea en curso.");
  openJob(title);
  const created = await request(`/api/${action}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  state.activeJob = created.job_id;
  localStorage.setItem("creator-md-active-job", created.job_id);
  return pollJob(created.job_id);
}

async function pollJob(jobId) {
  let retries = 0;
  while (true) {
    let job;
    try {
      job = await request(`/api/job?id=${encodeURIComponent(jobId)}`);
      retries = 0;
    } catch (problem) {
      if (problem.status === 404) {
        state.activeJob = null;
        localStorage.removeItem("creator-md-active-job");
        throw new Error("No se encontró la tarea. Revisa la biblioteca antes de iniciarla de nuevo.");
      }
      retries += 1;
      byId("jobState").textContent = "Reconectando";
      byId("jobLog").textContent = "Se perdió la conexión. Conservamos la tarea y estamos recuperando su estado.";
      await new Promise((resolve) => setTimeout(resolve, Math.min(1000 * 2 ** Math.min(retries, 4), 10000)));
      continue;
    }
    renderJob(job);
    if (job.status === "running") {
      await new Promise((resolve) => setTimeout(resolve, 850));
      continue;
    }
    state.activeJob = null;
    localStorage.removeItem("creator-md-active-job");
    if (job.status === "failed" || job.status === "interrupted") {
      byId("jobState").textContent = job.status === "interrupted" ? "Interrumpido" : "Error";
      byId("jobLog").textContent = job.error || "La tarea falló.";
      throw new Error(job.error || "La tarea falló.");
    }
    byId("jobState").textContent = "Completado";
    setTimeout(() => {
      if (!state.activeJob) byId("jobPanel").hidden = true;
    }, 5000);
    return job.result;
  }
}

function formatDuration(seconds) {
  if (!seconds) return "";
  const value = Math.round(seconds);
  const minutes = Math.floor(value / 60);
  const rest = value % 60;
  return `${minutes}:${String(rest).padStart(2, "0")}`;
}

function renderPreview(result) {
  state.preview = result;
  byId("selectionEmpty").hidden = true;
  byId("selectionResult").hidden = false;
  byId("metricPending").textContent = result.pending;
  byId("metricCompleted").textContent = result.completed;
  byId("metricFound").textContent = result.total;
  byId("discoveryBadge").textContent =
    result.discovery_method === "apify"
      ? "Apify · búsqueda histórica"
      : result.discovery_method === "tiktok_embed"
        ? "TikTok · canal oficial"
        : "YouTube · índice del canal";
  const start = result.first_date || "sin fecha";
  const end = result.last_date || "sin fecha";
  byId("selectionRange").textContent = `${start} a ${end}`;
  if (result.without_date) {
    byId("selectionNote").textContent =
      `${result.without_date} publicaciones no tenían fecha y quedaron fuera del intervalo.`;
  } else if (result.source_limit) {
    byId("selectionNote").textContent =
      `TikTok entregó sus ${result.known} publicaciones públicas más recientes (máximo ${result.source_limit}).`;
  } else {
    byId("selectionNote").textContent =
      `Se revisaron ${result.known} publicaciones del perfil.`;
  }
  const list = byId("videoList");
  list.replaceChildren();
  result.videos.forEach((video) => {
    const row = document.createElement("div");
    row.className = `video-item${video.already_completed ? " done" : ""}`;
    const choice = document.createElement("input");
    choice.type = "checkbox";
    choice.checked = !video.already_completed;
    choice.disabled = video.already_completed;
    choice.setAttribute("aria-label", `Seleccionar ${video.title}`);
    choice.addEventListener("change", () => {
      const selected = new Set(state.preview.selected_ids);
      if (choice.checked) selected.add(video.id);
      else selected.delete(video.id);
      state.preview.selected_ids = [...selected];
      updateSelectionButton();
    });
    const date = document.createElement("time");
    date.textContent = video.published_at || "sin fecha";
    const title = document.createElement("a");
    title.textContent = video.title;
    title.title = video.title;
    title.href = video.url;
    title.target = "_blank";
    title.rel = "noopener noreferrer";
    const status = document.createElement("span");
    status.textContent = video.already_completed ? "guardado" : formatDuration(video.duration) || "nuevo";
    row.append(choice, date, title, status);
    list.append(row);
  });
  byId("selectionNote").textContent += " Cobertura: " + (result.coverage?.status || "desconocida") + ".";
  updateSelectionButton();
}

function updateSelectionButton() {
  const count = state.preview?.selected_ids.length || 0;
  byId("extractButton").disabled = count < 1;
  byId("extractButton").textContent = count
    ? `Transcribir ${count} ${count === 1 ? "video" : "videos"}`
    : "No hay videos seleccionados";
}

function resultMessage(result) {
  if (result.kind === "sync") return `${result.discovered_new} novedades; ${result.pending} pendientes. Cobertura ${result.coverage?.status || "desconocida"}.`;
  return `${result.processed_this_run || 0} guardados; ${result.failed_this_run?.length || 0} fallidos; ${result.needs_review_this_run?.length || 0} para revisar.`;
}

async function analyzeProfile(event) {
  event.preventDefault();
  const form = byId("profileForm");
  updatePlatformLimits();
  const payload = profilePayload();
  const error = validateProfile(payload);
  showError(byId("profileError"), error);
  if (error) return;
  setFormBusy(form, true);
  try {
    const result = await startJob("preview", payload, "Analizando publicaciones");
    state.previewSignature = profileSignature(payload);
    renderPreview(result);
    toast(`Se encontraron ${result.pending} videos pendientes.`);
  } catch (problem) {
    showError(byId("profileError"), problem.message);
  } finally {
    setFormBusy(form, false);
  }
}

async function extractSelection() {
  const payload = profilePayload();
  if (!state.preview || state.previewSignature !== profileSignature(payload)) {
    resetPreview();
    showError(byId("profileError"), "Los datos cambiaron. Analiza el perfil nuevamente.");
    return;
  }
  payload.selected_ids = state.preview.selected_ids;
  payload.preview_id = state.preview.preview_id;
  payload.count = state.preview.selected_ids.length;
  if (!payload.count) return;
  byId("extractButton").disabled = true;
  try {
    const result = await startJob("extract", payload, "Transcribiendo selección");
    toast(resultMessage(result));
    await loadBootstrap();
    resetPreview();
    setTab("library");
  } catch (problem) {
    showError(byId("profileError"), problem.message);
  } finally {
    byId("extractButton").disabled = false;
  }
}

async function transcribeSingle(event) {
  event.preventDefault();
  const form = byId("singleForm");
  const payload = {
    single_url: byId("singleUrl").value.trim(),
    category: byId("singleCategory").value.trim(),
    project: byId("singleProject").value.trim(),
    count: 1,
  };
  const error = validateSingle(payload);
  showError(byId("singleError"), error);
  if (error) return;
  setFormBusy(form, true);
  try {
    const result = await startJob("single", payload, "Transcribiendo video");
    toast(result.duplicate ? "Ese video ya estaba guardado." : resultMessage(result));
    await loadBootstrap();
    form.reset();
    setTab("library");
  } catch (problem) {
    showError(byId("singleError"), problem.message);
  } finally {
    setFormBusy(form, false);
  }
}

async function runProjectAction(project, action) {
  const count = action === "retry" ? Math.max(1, project.failed + (project.needs_review || 0)) : 20;
  try {
    const result = await startJob(
      action,
      { category: project.category, project: project.name, count },
      { retry: "Reintentando videos", sync: "Consultando novedades",
        pending: "Procesando pendientes", history: "Recopilando anteriores" }[action],
    );
    toast(resultMessage(result));
    await loadBootstrap();
  } catch (problem) {
    toast(problem.message, true);
  }
}

function projectCard(project) {
  const article = document.createElement("article");
  article.className = "project-card";
  const category = document.createElement("span");
  category.className = "category";
  category.textContent = project.category;
  const title = document.createElement("h3");
  title.textContent = project.name;
  const source = document.createElement("p");
  source.className = "source";
  source.textContent = project.profile || "Proyecto local";
  const stats = document.createElement("div");
  stats.className = "project-stats";
  stats.innerHTML = `<span><strong>${project.completed}</strong> guardados</span><span><strong>${project.pending}</strong> pendientes</span><span><strong>${project.failed}</strong> fallidos</span><span><strong>${project.needs_review || 0}</strong> para revisar</span>`;
  const freshness = document.createElement("p");
  freshness.className = "freshness";
  freshness.textContent = project.last_checked_at
    ? `Consultado: ${new Date(project.last_checked_at).toLocaleString("es-PE")}. Cobertura ${project.coverage?.status || "desconocida"}.`
    : "Sin una consulta reciente verificada.";
  if (project.last_discovery_error) freshness.textContent += " La última consulta falló.";
  const actions = document.createElement("div");
  actions.className = "project-actions";
  const update = document.createElement("button");
  update.className = "button quiet";
  update.type = "button";
  update.textContent = "Buscar nuevos";
  update.disabled = project.source_type === "single_video";
  update.addEventListener("click", () => runProjectAction(project, "sync"));
  const pending = document.createElement("button");
  pending.className = "button quiet";
  pending.type = "button";
  pending.textContent = "Procesar pendientes";
  pending.disabled = project.pending < 1;
  pending.addEventListener("click", () => runProjectAction(project, "pending"));
  const history = document.createElement("button");
  history.className = "button quiet";
  history.type = "button";
  history.textContent = "Traer anteriores";
  history.disabled = project.source_type === "single_video";
  history.addEventListener("click", () => runProjectAction(project, "history"));
  const retry = document.createElement("button");
  retry.className = "button quiet";
  retry.type = "button";
  retry.textContent = "Reintentar";
  retry.disabled = project.failed + (project.needs_review || 0) < 1;
  retry.addEventListener("click", () => runProjectAction(project, "retry"));
  const markdown = document.createElement("a");
  markdown.className = "button primary";
  markdown.textContent = "Abrir MD";
  markdown.target = "_blank";
  markdown.href = `/markdown?category=${encodeURIComponent(project.category)}&project=${encodeURIComponent(project.name)}`;
  actions.append(update, pending, history, retry, markdown);
  article.append(category, title, source, stats, freshness, actions);
  return article;
}

function renderLibrary(library) {
  const grid = byId("libraryGrid");
  grid.replaceChildren();
  library.projects.forEach((project) => grid.append(projectCard(project)));
  byId("libraryEmpty").hidden = library.projects.length > 0;
  byId("libraryCount").textContent = library.projects.length;
  const categoryList = byId("categoryOptions");
  const projectList = byId("projectOptions");
  categoryList.replaceChildren();
  projectList.replaceChildren();
  library.categories.forEach((category) => {
    const option = document.createElement("option");
    option.value = category.name;
    categoryList.append(option);
  });
  [...new Set(library.projects.map((project) => project.name))].forEach((name) => {
    const option = document.createElement("option");
    option.value = name;
    projectList.append(option);
  });
}

function renderHealth(dependencies) {
  const health = byId("health");
  const missing = Object.entries(dependencies)
    .filter(([, value]) => !value.available)
    .map(([name]) => name);
  health.classList.toggle("ready", missing.length === 0);
  health.classList.toggle("error", missing.length > 0);
  health.lastElementChild.textContent = missing.length
    ? `Falta: ${missing.join(", ")}`
    : "Sistema listo";
}

function renderIntegrations(integrations) {
  const configured = Boolean(integrations?.apify?.configured);
  const status = byId("apifyStatus");
  status.classList.toggle("ready", configured);
  status.classList.toggle("offline", !configured);
  status.querySelector("strong").textContent = configured
    ? "Apify conectado"
    : "Modo gratuito activo";
  status.querySelector("p").textContent = configured
    ? "Las búsquedas históricas y por intervalo están disponibles."
    : "TikTok oficial permite revisar hasta 10 videos recientes.";
  byId("removeApify").disabled = !configured;
  updatePlatformLimits();
}

async function saveApify(event) {
  event.preventDefault();
  const form = byId("apifyForm");
  const token = byId("apifyToken").value.trim();
  showError(byId("apifyError"), "");
  if (token.length < 16) {
    showError(byId("apifyError"), "Pega un token de API válido.");
    return;
  }
  setFormBusy(form, true);
  try {
    await request("/api/settings/apify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    });
    byId("apifyToken").value = "";
    await loadBootstrap();
    toast("Apify quedó conectado de forma segura.");
  } catch (problem) {
    showError(byId("apifyError"), problem.message);
  } finally {
    setFormBusy(form, false);
  }
}

async function removeApify() {
  showError(byId("apifyError"), "");
  try {
    await request("/api/settings/apify", { method: "DELETE" });
    await loadBootstrap();
    toast("Apify fue desconectado.");
  } catch (problem) {
    showError(byId("apifyError"), problem.message);
  }
}

async function loadBootstrap() {
  try {
    const data = await request("/api/bootstrap");
    state.bootstrap = data;
    renderLibrary(data.library);
    renderHealth(data.dependencies);
    renderIntegrations(data.integrations);
  } catch (problem) {
    toast(problem.message, true);
    byId("health").classList.add("error");
    byId("health").lastElementChild.textContent = "No se pudo leer el sistema";
  }
}

function wireEvents() {
  document.querySelectorAll(".tab").forEach((button) => {
    button.addEventListener("click", () => setTab(button.dataset.tab));
  });
  byId("profileForm").addEventListener("submit", analyzeProfile);
  byId("singleForm").addEventListener("submit", transcribeSingle);
  byId("extractButton").addEventListener("click", extractSelection);
  byId("refreshLibrary").addEventListener("click", loadBootstrap);
  byId("openIntegrations").addEventListener("click", () => setTab("settings"));
  byId("apifyForm").addEventListener("submit", saveApify);
  byId("removeApify").addEventListener("click", removeApify);
  byId("resetProfile").addEventListener("click", () => {
    byId("profileForm").reset();
    state.projectWasEdited = false;
    showError(byId("profileError"), "");
    resetPreview();
    updatePlatformLimits();
  });
  byId("profileProject").addEventListener("input", () => {
    state.projectWasEdited = Boolean(byId("profileProject").value.trim());
    resetPreview();
  });
  byId("profileUrl").addEventListener("input", () => {
    if (!state.projectWasEdited) {
      byId("profileProject").value = projectFromUrl(byId("profileUrl").value);
    }
    updatePlatformLimits();
    resetPreview();
  });
  ["profileCategory", "dateFrom", "dateTo", "scanLimit"].forEach((id) => {
    byId(id).addEventListener("input", resetPreview);
  });
  byId("singleUrl").addEventListener("input", () => {
    if (!byId("singleProject").value.trim()) {
      byId("singleProject").value = projectFromUrl(byId("singleUrl").value);
    }
  });
}

wireEvents();
updatePlatformLimits();
loadBootstrap();

const savedJob = localStorage.getItem("creator-md-active-job");
if (savedJob) {
  state.activeJob = savedJob;
  openJob("Recuperando tarea");
  pollJob(savedJob)
    .then((result) => toast(resultMessage(result)))
    .catch((problem) => toast(problem.message, true))
    .finally(loadBootstrap);
}
