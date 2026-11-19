// Dispora public data site: view by type + filters. No framework, no build step.
"use strict";

const PAGE_SIZE = 20;
const DAYS = ["", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];

const state = { types: [], type: null, filters: {}, page: 1, total: 0 };

const $ = (id) => document.getElementById(id);

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "onclick") node.addEventListener("click", v);
    else node.setAttribute(k, v);
  }
  for (const c of children) node.append(c instanceof Node ? c : document.createTextNode(c));
  return node;
}

async function api(path) {
  const res = await fetch(`/api/${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// ---- formatting -----------------------------------------------------------

function humanize(text) {
  const s = String(text).replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

function formatValue(value, key) {
  const isTime = key === "jam_buka" || key === "jam_tutup";
  if (isTime && (value === null || value === undefined)) return "Tutup";
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Ya" : "Tidak";
  if (key === "hari" && DAYS[value]) return DAYS[value];
  if (isTime && typeof value === "string" && /^\d{2}:\d{2}:\d{2}$/.test(value)) return value.slice(0, 5);
  if (Array.isArray(value)) {
    if (value.length === 0) return "—";
    if (typeof value[0] === "object") return value.map((v) => v.nama ?? v.nama_olahraga ?? "?").join(", ");
    return value.join(", ");
  }
  if (typeof value === "string") {
    if (/^\d{4}-\d{2}-\d{2}(T00:00:00)?/.test(value) && value.length <= 25 && key?.startsWith("tanggal")) {
      return value.slice(0, 10);
    }
    if (/^[a-z]+(_[a-z]+)+$/.test(value) || /^[a-z]+$/.test(value)) return humanize(value);
  }
  return String(value);
}

// ---- type tabs ------------------------------------------------------------

function renderTabs() {
  const nav = $("type-tabs");
  nav.replaceChildren(...state.types.map((t) =>
    el("button", {
      type: "button",
      class: t.name === state.type.name ? "tab active" : "tab",
      "aria-pressed": String(t.name === state.type.name),
      onclick: () => selectType(t.name),
    }, t.label)));
}

async function selectType(name) {
  state.type = state.types.find((t) => t.name === name);
  state.filters = {};
  state.page = 1;
  renderTabs();
  $("filter-fields").replaceChildren(el("p", { class: "muted" }, "Memuat filter…"));
  try {
    const def = await api(`${name}/filters`);
    renderFilters(def.filters);
  } catch (err) {
    $("filter-fields").replaceChildren(el("p", { class: "error" }, `Filter gagal dimuat: ${err.message}`));
  }
  loadList();
}

// ---- filters --------------------------------------------------------------

function renderFilters(filters) {
  const fields = filters.map((f) => {
    const id = `f-${f.param}`;
    let input;
    if (f.kind === "date_from" || f.kind === "date_to") {
      input = el("input", { type: "date", id, name: f.param });
    } else {
      input = el("select", { id, name: f.param }, el("option", { value: "" }, "Semua"));
      const options = f.kind === "bool"
        ? [{ value: "true", label: "Ya" }, { value: "false", label: "Tidak" }]
        : f.options || [];
      for (const o of options) {
        input.append(el("option", { value: o.value }, f.kind === "enum" ? humanize(o.label) : o.label));
      }
    }
    return el("label", { for: id, class: "field" }, el("span", {}, f.label), input);
  });
  $("filter-fields").replaceChildren(...fields);
}

$("filter-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const data = new FormData(e.target);
  state.filters = Object.fromEntries([...data.entries()].filter(([, v]) => v !== ""));
  state.page = 1;
  loadList();
});

$("filter-form").addEventListener("reset", () => {
  state.filters = {};
  state.page = 1;
  // Let the browser clear the inputs before reloading.
  setTimeout(loadList, 0);
});

// ---- results table ----------------------------------------------------------

async function loadList() {
  const type = state.type;
  const params = new URLSearchParams({ ...state.filters, page: state.page, page_size: PAGE_SIZE });
  $("status").textContent = "Memuat…";
  try {
    const data = await api(`${type.name}?${params}`);
    if (type !== state.type) return; // user switched tabs meanwhile
    state.total = data.total;
    renderTable(type, data.items);
    $("status").textContent = `${data.total} ${type.label.toLowerCase()} ditemukan`;
  } catch (err) {
    renderTable(type, []);
    $("status").textContent = `Gagal memuat data: ${err.message}`;
  }
  renderPager();
}

function renderTable(type, items) {
  const table = $("results");
  table.tHead.replaceChildren(el("tr", {}, ...type.columns.map((c) => el("th", { scope: "col" }, c.label))));
  if (items.length === 0) {
    table.tBodies[0].replaceChildren(
      el("tr", {}, el("td", { colspan: type.columns.length, class: "muted" }, "Tidak ada data.")));
    return;
  }
  table.tBodies[0].replaceChildren(...items.map((item) =>
    el("tr", { class: "row", tabindex: "0", onclick: () => openDetail(type, item.id) },
      ...type.columns.map((c) => el("td", { "data-label": c.label }, formatValue(item[c.field], c.field))))));
}

$("results").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && e.target.matches("tr.row")) e.target.click();
});

function renderPager() {
  const pages = Math.max(1, Math.ceil(state.total / PAGE_SIZE));
  $("page-info").textContent = `Halaman ${state.page} dari ${pages}`;
  $("prev").disabled = state.page <= 1;
  $("next").disabled = state.page >= pages;
}

$("prev").addEventListener("click", () => { state.page -= 1; loadList(); });
$("next").addEventListener("click", () => { state.page += 1; loadList(); });

// ---- detail dialog ----------------------------------------------------------

function renderObjectTable(rows) {
  const keys = [...new Set(rows.flatMap((r) => Object.keys(r)))].filter((k) => k !== "id" && !k.endsWith("_id"));
  return el("table", { class: "nested" },
    el("thead", {}, el("tr", {}, ...keys.map((k) => el("th", {}, humanize(k))))),
    el("tbody", {}, ...rows.map((r) => el("tr", {}, ...keys.map((k) => el("td", {}, formatValue(r[k], k)))))));
}

async function openDetail(type, id) {
  const dialog = $("detail");
  $("detail-title").textContent = "Memuat…";
  $("detail-body").replaceChildren();
  dialog.showModal();
  try {
    const item = await api(`${type.name}/${encodeURIComponent(id)}`);
    $("detail-title").textContent = item.nama || type.label;
    const list = el("dl", { class: "detail" });
    const sections = [];
    for (const [key, value] of Object.entries(item)) {
      if (key === "id" || key === "nama" || key.endsWith("_id")) continue;
      if (Array.isArray(value) && value.length && typeof value[0] === "object") {
        sections.push(el("h3", {}, humanize(key)), renderObjectTable(value));
      } else {
        list.append(el("dt", {}, humanize(key)), el("dd", {}, formatValue(value, key)));
      }
    }
    $("detail-body").replaceChildren(list, ...sections);
  } catch (err) {
    $("detail-title").textContent = "Gagal memuat";
    $("detail-body").replaceChildren(el("p", { class: "error" }, err.message));
  }
}

// ---- start ------------------------------------------------------------------

(async function init() {
  try {
    state.types = await api("types");
    await selectType(state.types[0].name);
  } catch (err) {
    $("status").textContent = `API tidak tersedia: ${err.message}`;
  }
})();
