/* Miser — frontend logic */

const API = "";  // same origin; change to "http://localhost:8000" for dev

// ── State ────────────────────────────────────────────────────────────────────
let currentProduct = null;

// ── DOM refs ─────────────────────────────────────────────────────────────────
const urlInput      = document.getElementById("amazon-url");
const btnExtract    = document.getElementById("btn-extract");
const extractError  = document.getElementById("extract-error");

const section1      = document.getElementById("section-1");
const section2      = document.getElementById("section-2");
const section3      = document.getElementById("section-3");

const confirmImage  = document.getElementById("confirm-image");
const fieldTitle    = document.getElementById("field-title");
const fieldBrand    = document.getElementById("field-brand");
const fieldModel    = document.getElementById("field-model");
const fieldQuery    = document.getElementById("field-query");

const optAmazon     = document.getElementById("opt-amazon");
const optGeizhals   = document.getElementById("opt-geizhals");
const optIdealo     = document.getElementById("opt-idealo");

const btnBack       = document.getElementById("btn-back");
const btnCompare    = document.getElementById("btn-compare");
const btnNewSearch  = document.getElementById("btn-new-search");

const loadingResults = document.getElementById("loading-results");
const resultsError  = document.getElementById("results-error");
const resultsList   = document.getElementById("results-list");
const resultsSummary = document.getElementById("results-summary");
const vatBanner     = document.getElementById("vat-banner");

// ── Step helpers ──────────────────────────────────────────────────────────────
function setStep(n) {
  [section1, section2, section3].forEach((s, i) => s.classList.toggle("hidden", i + 1 !== n));
  for (let i = 1; i <= 3; i++) {
    const dot = document.getElementById(`step-dot-${i}`);
    dot.classList.remove("active", "done");
    if (i < n)  dot.classList.add("done");
    if (i === n) dot.classList.add("active");
  }
  window.scrollTo({ top: 0, behavior: "smooth" });
}

// ── Step 1: Extract ───────────────────────────────────────────────────────────
btnExtract.addEventListener("click", handleExtract);
urlInput.addEventListener("keydown", e => { if (e.key === "Enter") handleExtract(); });

async function handleExtract() {
  const url = urlInput.value.trim();
  extractError.classList.add("hidden");

  if (!url) {
    showError(extractError, "Please paste an Amazon product URL.");
    return;
  }
  if (!url.includes("amazon")) {
    showError(extractError, "This doesn't look like an Amazon URL. Please use an amazon.com, .de, .fr, etc. link.");
    return;
  }

  setLoading(btnExtract, true, "Extracting…");

  try {
    const res = await fetch(`${API}/api/extract`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();
    if (!res.ok) {
      showError(extractError, data.detail || "Failed to extract product. Try again.");
      return;
    }

    currentProduct = data;
    populateConfirmForm(data);
    setStep(2);
  } catch (err) {
    showError(extractError, "Network error. Is the backend running?");
  } finally {
    setLoading(btnExtract, false, "Extract →");
  }
}

function populateConfirmForm(p) {
  fieldTitle.value  = p.title        || "";
  fieldBrand.value  = p.brand        || "";
  fieldModel.value  = p.model        || "";
  fieldQuery.value  = p.search_query || p.title || "";

  if (p.image_url) {
    confirmImage.src = p.image_url;
    confirmImage.style.display = "block";
  } else {
    confirmImage.style.display = "none";
  }
}

// ── Auto-update search query when brand/model changes ─────────────────────────
function autoUpdateQuery() {
  const brand = fieldBrand.value.trim();
  const model = fieldModel.value.trim();
  const title = fieldTitle.value.trim();
  if (brand && model) {
    fieldQuery.value = `${brand} ${model}`;
  } else if (brand && title) {
    fieldQuery.value = `${brand} ${title.split(" ").slice(0, 5).join(" ")}`;
  }
}

fieldBrand.addEventListener("change", autoUpdateQuery);
fieldModel.addEventListener("change", autoUpdateQuery);

// ── Step 2: Back ──────────────────────────────────────────────────────────────
btnBack.addEventListener("click", () => setStep(1));

// ── Step 2: Compare ───────────────────────────────────────────────────────────
btnCompare.addEventListener("click", handleCompare);

async function handleCompare() {
  resultsError.classList.add("hidden");
  resultsList.innerHTML = "";
  vatBanner.classList.add("hidden");
  loadingResults.style.display = "block";

  setStep(3);

  const product = {
    title:        fieldTitle.value.trim() || null,
    brand:        fieldBrand.value.trim() || null,
    model:        fieldModel.value.trim() || null,
    asin:         currentProduct?.asin || null,
    image_url:    currentProduct?.image_url || null,
    search_query: fieldQuery.value.trim() || null,
  };

  try {
    const res = await fetch(`${API}/api/compare`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        product,
        include_amazon_eu: optAmazon.checked,
        include_geizhals:  optGeizhals.checked,
        include_idealo:    optIdealo.checked,
      }),
    });

    const data = await res.json();
    loadingResults.style.display = "none";

    if (!res.ok) {
      showError(resultsError, data.detail || "Search failed. Please try again.");
      return;
    }

    renderResults(data);
  } catch (err) {
    loadingResults.style.display = "none";
    showError(resultsError, "Network error while searching. Is the backend running?");
  }
}

// ── Render results ────────────────────────────────────────────────────────────
function renderResults(data) {
  const { results, query, total } = data;

  if (!results || results.length === 0) {
    resultsSummary.textContent = `No results found for "${query}". Try editing the search query.`;
    return;
  }

  resultsSummary.textContent = `Found ${total} offer${total !== 1 ? "s" : ""} for "${query}" — sorted cheapest first`;
  vatBanner.classList.remove("hidden");

  results.forEach((item, i) => {
    const rank = i + 1;
    const isBest = rank === 1;
    const priceStr = formatPrice(item.price, item.currency);
    const exclVatStr = item.price_excl_vat
      ? `excl. VAT: ${formatPrice(item.price_excl_vat, item.currency)}`
      : "";
    const vatPct = item.vat_rate ? `${Math.round(item.vat_rate * 100)}% VAT` : "";

    const card = document.createElement("a");
    card.href = item.url || "#";
    card.target = "_blank";
    card.rel = "noopener noreferrer";
    card.className = `result-item${isBest ? " rank-1" : ""}`;

    card.innerHTML = `
      <div class="result-left">
        <div class="result-rank">${rank}</div>
        <div class="result-meta">
          <div class="result-retailer">
            <span>${item.flag || ""} ${escHtml(item.retailer)}</span>
            <span class="result-country">${escHtml(item.country_name || item.country)}</span>
            ${isBest ? '<span class="best-badge">BEST PRICE</span>' : ""}
          </div>
          <div class="result-source">via ${escHtml(item.source)}</div>
        </div>
      </div>
      <div class="result-right">
        <div class="result-price">${priceStr}</div>
        ${exclVatStr ? `<div class="result-excl-vat">${exclVatStr}</div>` : ""}
        ${vatPct ? `<div class="result-vat-tag">${vatPct}</div>` : ""}
      </div>
    `;

    resultsList.appendChild(card);
  });
}

function formatPrice(price, currency) {
  if (price == null) return "N/A";
  const fmt = new Intl.NumberFormat("de-CH", {
    style: "currency",
    currency: currency || "EUR",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  return fmt.format(price);
}

function escHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── New search ────────────────────────────────────────────────────────────────
btnNewSearch.addEventListener("click", () => {
  urlInput.value = "";
  currentProduct = null;
  resultsList.innerHTML = "";
  setStep(1);
});

// ── Helpers ───────────────────────────────────────────────────────────────────
function showError(el, msg) {
  el.textContent = msg;
  el.classList.remove("hidden");
}

function setLoading(btn, loading, label) {
  btn.disabled = loading;
  btn.textContent = label;
}
