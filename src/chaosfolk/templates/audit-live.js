/* The dashboard reads one durable session. Polling makes no model requests. */
"use strict";
const $ = id => document.getElementById(id);
const token = location.hash.slice(1) || sessionStorage.getItem("chaosfolk-token");
if (token) sessionStorage.setItem("chaosfolk-token", token);
history.replaceState(null, "", location.pathname);
let state, busy = false, page = 0, timer, lastTable = "", received = 0, stopped = false, closed = false, stopping = false, pendingPath = "", errorKind = "";
const draftKey = "chaosfolk-limits-" + token;
let draft = {};
try { draft = JSON.parse(sessionStorage.getItem(draftKey) || "{}"); } catch (_) { /* Storage may be unavailable. */ }
if (!draft || typeof draft !== "object" || Array.isArray(draft)) draft = {};
if (Object.keys(draft).length) $("limits").closest("details").open = true;
const limitFields = {minutes:"max_seconds", actions:"max_actions", tokens:"max_tokens", browsers:"max_browsers"};
function saveDraft() {
  try { sessionStorage.setItem(draftKey, JSON.stringify(draft)); } catch (_) { /* Keep edits in memory. */ }
  $("limits-note").textContent = Object.keys(draft).length ? "Modifications non enregistrées." : "";
  $("discard-limits").hidden = !Object.keys(draft).length;
}
const size = 15, ranks = {quick: 1, standard: 2, deep: 3};
const names = {pending:"À faire",running:"En cours",measured:"À confirmer",blocked:"Bloqué",passed:"Réussi",failed:"Échec observé",inconclusive:"Non concluant","needs-discovery":"À explorer","not-applicable":"Non applicable","review-context":"Contexte à revoir","excluded-by-user":"Retiré par vous","outside-depth":"Autre niveau"};
const format = n => new Intl.NumberFormat("fr-FR").format(n);
function error(message, kind = "action") { errorKind = message ? kind : ""; $("message").hidden = !message; $("message").textContent = message || ""; }
async function api(path, body) {
  const response = await fetch("/api/" + path, {method:body === undefined ? "GET":"POST", headers:{Authorization:"Bearer " + (token || ""), ...(body === undefined ? {}:{"Content-Type":"application/json"})}, body:body === undefined ? undefined:JSON.stringify(body), signal:AbortSignal.timeout(10000)});
  if (response.status === 204) return null;
  const value = await response.json();
  if (!response.ok) throw new Error(value.error || "La session ne répond pas.");
  return value;
}
function text(tag, value, cls) { const el = document.createElement(tag); el.textContent = value; if (cls) el.className = cls; return el; }
function clock() {
  if (!state) return;
  const seconds = Math.floor(state.elapsed + (state.config.state === "running" ? (Date.now() - received) / 1000 : 0));
  $("elapsed").textContent = `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2,"0")} s`;
}
function rows() {
  if (!state) return;
  const query = $("search").value.toLocaleLowerCase("fr"), filter = $("filter").value;
  const entries = state.entries.filter(e => e.configurable && (e.title + " " + e.category + " " + e.id).toLocaleLowerCase("fr").includes(query) &&
    (filter === "all" || filter === "selected" && e.selected || filter === "excluded" && e.excluded || filter === "blocked" && (e.states.blocked || e.states["needs-discovery"])));
  page = Math.max(0, Math.min(page, Math.ceil(entries.length / size) - 1));
  const visible = entries.slice(page * size, (page + 1) * size);
  const signature = JSON.stringify([visible, page, entries.length, state.config.depth, busy]);
  if (signature === lastTable) return;
  lastTable = signature;
  const focused = document.activeElement?.dataset?.check, fragment = document.createDocumentFragment();
  for (const entry of visible) {
    const row = text("div", "", "test"), label = document.createElement("label"), checkbox = document.createElement("input");
    checkbox.type = "checkbox"; checkbox.checked = entry.selected; checkbox.dataset.check = entry.id;
    checkbox.disabled = busy || Number(entry.priority.slice(1)) > ranks[state.config.depth];
    checkbox.setAttribute("aria-label", entry.title); label.append(checkbox);
    const info = document.createElement("div"); info.append(text("p", entry.title, "test-title"));
    const meta = text("div", "", "test-meta"); meta.append(text("span", entry.priority, "badge"), document.createTextNode(entry.category)); info.append(meta);
    const status = Object.entries(entry.states).map(([key, value]) => `${names[key] || key}${value > 1 ? " × " + value : ""}`).join(" · ");
    row.append(label, info, text("div", status, "test-state")); fragment.append(row);
  }
  if (!visible.length) fragment.append(text("p", "Aucun test ne correspond à ce filtre.", "test empty"));
  $("tests").replaceChildren(fragment);
  if (focused) [...$("tests").querySelectorAll("input")].find(e => e.dataset.check === focused)?.focus();
  $("page").textContent = `${entries.length ? page + 1 : 0} / ${Math.ceil(entries.length / size)}`;
  $("previous").disabled = page === 0; $("next").disabled = (page + 1) * size >= entries.length;
}
function render(value, updateRows = true) {
  if (state && value.config.revision < state.config.revision) return;
  if (value.entries_mode === "patch" && state) {
    const changes = new Map(value.entries.map(entry => [entry.id, entry]));
    value = {...value, entries_mode:"full", entries:state.entries.map(entry => ({...entry, ...changes.get(entry.id)}))};
  }
  if (value === state && state.config.state === "running") value = {...state, elapsed:state.elapsed + (Date.now() - received) / 1000};
  state = value; received = Date.now();
  const c = state.config, running = c.state === "running";
  $("state").textContent = ({ready:"Prêt",running:"En cours",stopped:"Arrêté"})[c.state] || c.state;
  $("connection").textContent = "Connecté · session locale";
  $("actions").textContent = format(c.actions) + (c.limits.max_actions ? ` / ${format(c.limits.max_actions)}` : "");
  $("tokens").textContent = c.usage.tokens === null ? "Indisponible" : format(c.usage.tokens) + (c.limits.max_tokens ? ` / ${format(c.limits.max_tokens)}` : "");
  $("usage-note").textContent = c.usage.updated ? `Mesures hôte reçues à ${new Date(c.usage.updated * 1000).toLocaleTimeString("fr-FR")}. ${c.usage.complete ? "" : "Couverture incomplète des agents."}` : "Aucune mesure de tokens reçue de l’hôte. Aucune estimation n’est affichée.";
  $("start").disabled = running || busy || stopping; $("stop").disabled = (!running && pendingPath !== "start") || stopping;
  $("stop").textContent = stopping ? "Arrêt en cours…" : "Arrêter l’audit";
  $("reset").disabled = busy; $("limits").querySelector("button[type=submit]").disabled = busy;
  $("close-dashboard").disabled = busy || stopping;
  $("start").textContent = c.state === "stopped" ? "Reprendre l’audit" : "Autoriser l’audit";
  $("progress").textContent = `${format(state.tested)} vérifications avec résultat · ${format(state.unresolved)} à terminer ou à confirmer${state.counts["not-applicable"] ? " · " + format(state.counts["not-applicable"]) + " non applicables" : ""}. ${state.completion === "complete" ? "Périmètre sélectionné couvert." : "Audit partiel."}${c.reason ? " Motif : " + c.reason + "." : ""}`;
  const configurable = state.entries.filter(e => e.configurable), selected = configurable.filter(e => e.selected).length;
  $("selection-count").textContent = `${selected} tests sélectionnés sur ${configurable.length} · ${c.excluded.length} retirés par vous`;
  document.querySelectorAll("input[name=depth]").forEach(input => {if (updateRows) input.checked = input.value === c.depth; input.disabled = busy;});
  for (const [field, key] of Object.entries(limitFields)) {
    const input = $("limits").elements[field];
    if (document.activeElement !== input) input.value = draft[field] ?? (c.limits[key] ? c.limits[key] / (field === "minutes" ? 60 : 1) : "");
  }
  saveDraft();
  if (!$("methods").children.length) {
    const methods = state.entries.filter(e => !e.configurable);
    $("methods-count").textContent = `${methods.length} méthodes, profils et outils disponibles`;
    $("methods").replaceChildren(...methods.map(e => text("li", e.title)));
  }
  if (updateRows) rows(); clock();
}
async function mutate(path, body, submitted) {
  const isStop = path === "stop";
  if (closed || (isStop ? stopping : busy || stopping)) return;
  if (isStop) stopping = true;
  else {busy = true; pendingPath = path; document.body.classList.add("busy");}
  if (state) render(state, false);
  if (!isStop) document.querySelectorAll("#tests input").forEach(input => input.disabled = true);
  $("operation").textContent = stopping ? "Arrêt demandé…" : "Enregistrement en cours…";
  error("");
  try {
    const result = await api(path, body);
    if (result.ok !== false && submitted) {
      for (const [field, value] of Object.entries(submitted)) if (draft[field] === value) delete draft[field];
      saveDraft();
    }
    render(result); if (result.ok === false) error(result.reason);
  }
  catch (e) { error(e.message); }
  finally {
    if (isStop) stopping = false;
    else {busy = false; pendingPath = ""; document.body.classList.remove("busy");}
    $("operation").textContent = stopping ? "Arrêt demandé…" : busy ? "Enregistrement en cours…" : "";
    if (state) render(state);
  }
}
async function poll() {
  clearTimeout(timer); if (stopped) return;
  try { if (!busy) {const value = await api("state" + (state ? "?after=" + state.config.revision : "")); if (!stopped) {if (value && !busy && (!state || value.config.revision >= state.config.revision)) render(value); else $("connection").textContent = "Connecté · session locale"; if (errorKind === "network") error("");}} }
  catch (e) { if (!stopped) {$("connection").textContent = "Connexion interrompue"; if (errorKind !== "action") error("Connexion interrompue. Nouvelle tentative automatique.", "network");} }
  if (!stopped) timer = setTimeout(poll, document.hidden ? 5000 : 1000);
}
document.querySelectorAll("input[name=depth]").forEach(input => input.addEventListener("change", () => mutate("selection", {depth:input.value})));
$("tests").addEventListener("change", event => {const input = event.target; if (!input.dataset.check || !state) return; mutate("selection", {test_id:input.dataset.check, enabled:input.checked});});
$("reset").addEventListener("click", () => {
  if (!state) return;
  mutate("selection", {reset:true});
});
$("start").addEventListener("click", () => {if (state) mutate("start", {expected_revision:state.config.revision});}); $("stop").addEventListener("click", () => mutate("stop", {}));
$("close-dashboard").addEventListener("click", async () => {
  if (busy || stopped) return;
  busy = true;
  $("close-dashboard").disabled = true;
  try {
    await api("shutdown", {}); stopped = true; closed = true; clearTimeout(timer); clearInterval(clockTimer);
    $("connection").textContent = "Tableau de bord fermé";
    document.querySelectorAll("button,input,select").forEach(el => el.disabled = true);
    error("Le tableau de bord est fermé. L’audit reste géré par votre assistant.");
  } catch (e) { busy = false; $("close-dashboard").disabled = false; error(e.message); }
});
$("search").addEventListener("input", () => {page = 0; rows();}); $("filter").addEventListener("change", () => {page = 0; rows();});
$("previous").addEventListener("click", () => {page--; rows();}); $("next").addEventListener("click", () => {page++; rows();});
$("limits").addEventListener("input", event => { if (limitFields[event.target.name]) {draft[event.target.name] = event.target.value; saveDraft();} });
$("limits").addEventListener("submit", event => {
  event.preventDefault();
  const submitted = {...draft}, limits = {};
  for (const [field, value] of Object.entries(submitted)) if (limitFields[field]) limits[limitFields[field]] = value ? Number(value) * (field === "minutes" ? 60 : 1) : null;
  if (Object.keys(limits).length) mutate("selection", {limits}, submitted);
});
$("discard-limits").addEventListener("click", () => {draft = {}; saveDraft(); if (state) render(state);});
window.addEventListener("pagehide", () => {stopped = true; clearTimeout(timer);});
window.addEventListener("pageshow", event => {if (event.persisted && !closed) {stopped = false; poll();}});
const clockTimer = setInterval(clock, 1000); poll();
