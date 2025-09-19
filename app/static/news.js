(function () {
  "use strict";

  const root = document.documentElement;
  const qs = (sel, el = document) => el.querySelector(sel);
  const qsa = (sel, el = document) => Array.from(el.querySelectorAll(sel));
  const themeBtn = qs("#themeToggle");
  const THEME_ICONS = {
    sun: '<span class="knob"></span><svg class="sun" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M12 4V2m0 20v-2M4.93 4.93L3.51 3.51m16.98 16.98l-1.42-1.42M4 12H2m20 0h-2M4.93 19.07l-1.42 1.42m16.98-16.98l-1.42 1.42M12 8a4 4 0 100 8 4 4 0 000-8z" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"></path></svg>',
    moon: '<span class="knob"></span><svg class="moon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path></svg>'
  };

  function paintThemeIcon() {
    if (!themeBtn) return;
    const dark = root.classList.contains("dark");
    themeBtn.innerHTML = dark ? THEME_ICONS.sun : THEME_ICONS.moon;
  }

  if (themeBtn) {
    paintThemeIcon();
    themeBtn.addEventListener("click", () => {
      root.classList.toggle("dark");
      try {
        localStorage.setItem("theme", root.classList.contains("dark") ? "dark" : "light");
      } catch (err) { }
      paintThemeIcon();
    });
    themeBtn.addEventListener("pointerdown", (ev) => ev.preventDefault(), { passive: false });
  }
  const brandLogo = qs("#brandLogo");
  let brandLogoObjectUrl = null;
  const statusEl = qs("#status");
  const lastUpdateEl = qs("#lastUpdate");
  const liveBadge = qs("#liveBadge");
  const infoPanel = qs("#infoPanel");
  const infoClose = qs("#infoClose");
  const btnInfo = qs("#btnInfo");
  const newsListEl = qs("#newsList");
  const newsLoadingEl = qs("#newsLoading");
  const newsEmptyEl = qs("#newsEmpty");
  const loadMoreBtn = qs("#loadMore");
  const symbolInput = qs("#symbolInput");
  const symbolClear = qs("#symbolClear");
  const dropdownEl = qs("#symbolDropdown");
  const kapToggle = qs("#kapToggle");
  const categoryGroup = qs("#categoryChips");
  const sentimentGroup = qs("#sentimentChips");
  const rangeGroup = qs("#quickRanges");
  const drawer = qs("#drawer");
  const btnMenu = qs("#btnMenu");
  const btnCloseDrawer = qs("#drawerClose");
  const backdrop = qs("#backdrop");
  const modalBackdrop = qs("#newsModalBackdrop");
  const modal = qs("#newsModal");
  const modalSurface = modal ? qs("[data-modal-surface]", modal) : null;
  const modalClose = modal ? qs("#newsModalClose", modal) : null;
  const modalTitle = modal ? qs("#newsModalTitle", modal) : null;
  const modalMeta = modal ? qs("#newsModalMeta", modal) : null;
  const modalRelative = modal ? qs("#newsModalRelative", modal) : null;
  const modalSource = modal ? qs("#newsModalSource", modal) : null;
  const modalBadges = modal ? qs("#newsModalBadges", modal) : null;
  const modalBody = modal ? qs("#newsModalBody", modal) : null;
  const modalAnalysis = modal ? qs("#newsModalAnalysis", modal) : null;
  const modalTags = modal ? qs("#newsModalTags", modal) : null;
  const modalLink = modal ? qs("#newsModalLink", modal) : null
  const symbolsEndpoint = window.SYMBOLS_API || "/api/sectoral-brief";
  const newsEndpoint = window.NEWS_API || "/api/news";
  const PAGE_SIZE = 5;
  const state = {
    symbol: (window.SYMBOL || "").toString().trim().toUpperCase(),
    filters: {
      kapOnly: false,
      categories: new Set(),
      sentiment: "all",
      range: "today",
    },
    page: 1,
    cursor: null,
    hasMore: true,
    loading: false,
  };
  let scrollLockCount = 0;

  function lockScroll() {
    if (scrollLockCount === 0) {
      document.documentElement.style.overflow = "hidden";
    }
    scrollLockCount += 1;
  }

  function unlockScroll() {
    scrollLockCount = Math.max(0, scrollLockCount - 1);
    if (scrollLockCount === 0) {
      document.documentElement.style.overflow = "";
    }
  }
  function normaliseFilterValue(value) {
    return (value || "").toString().trim().toUpperCase();
  }

  function buildLookup(map) {
    const lookup = {};
    Object.entries(map).forEach(([key, values]) => {
      const set = new Set([normaliseFilterValue(key)]);
      values.forEach((val) => {
        const norm = normaliseFilterValue(val);
        if (norm) set.add(norm);
      });
      lookup[key] = set;
    });
    return lookup;
  }

  const CATEGORY_LOOKUP = buildLookup({
    company: ["SIRKET", "ŞİRKET", "COMPANY"],
    economy: ["EKONOMI", "EKONOMİ", "ECONOMY", "MAKRO", "MACRO"],
    global: ["GLOBAL", "DUNYA", "DÜNYA", "INTERNATIONAL", "WORLD"],
    analysis: ["ANALIZ", "ANALİZ", "ANALYSIS", "RESEARCH", "DEGERLENDIRME", "DEĞERLENDİRME"],
  });

  const SENTIMENT_LOOKUP = buildLookup({
    positive: ["POZITIF", "POZİTİF", "POSITIVE", "OLUMLU"],
    neutral: ["NOTR", "NÖTR", "NEUTRAL"],
    negative: ["NEGATIF", "NEGATİF", "NEGATIVE", "OLUMSUZ"],
  });

  const KAP_SOURCES = new Set(["KAP", "KAMUYU AYDINLATMA PLATFORMU"].map(normaliseFilterValue));
  const DAY_MS = 86400000;

  function resolveTimestamp(item) {
    const candidates = [
      item?.timestamp,
      item?.published_at,
      item?.publishedAt,
      item?.time,
      item?.created_at,
      item?.createdAt,
      item?.date,
    ];
    for (const candidate of candidates) {
      const ms = normaliseTimestamp(candidate);
      if (ms !== null) return ms;
    }
    return null;
  }

  function normaliseTimestamp(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      if (value > 1e12) return value;
      if (value > 1e9) return value * 1000;
      return Math.round(value * 1000);
    }
    if (typeof value === "string" && value) {
      const trimmed = value.trim();
      if (!trimmed) return null;
      const numeric = Number(trimmed);
      if (Number.isFinite(numeric)) {
        return normaliseTimestamp(numeric);
      }
      const parsed = Date.parse(trimmed);
      if (!Number.isNaN(parsed)) return parsed;
    }
    if (value instanceof Date) {
      const time = value.getTime();
      return Number.isFinite(time) ? time : null;
    }
    return null;
  }

  function getRangeThreshold(range) {
    switch (range) {
      case "today": {
        const now = new Date();
        now.setHours(0, 0, 0, 0);
        return now.getTime();
      }
      case "week":
        return Date.now() - 7 * DAY_MS;
      case "month":
        return Date.now() - 30 * DAY_MS;
      default:
        return null;
    }
  }

  function getItemCategories(item) {
    if (Array.isArray(item?.categories)) return item.categories;
    if (Array.isArray(item?.category)) return item.category;
    if (item?.category != null) return [item.category];
    return [];
  }

  function getItemSources(item) {
    if (Array.isArray(item?.source)) return item.source;
    if (item?.source != null) return [item.source];
    if (Array.isArray(item?.sources)) return item.sources;
    return [];
  }

  function isKapNews(item) {
    const sources = getItemSources(item).map(normaliseFilterValue).filter(Boolean);
    if (sources.some((src) => KAP_SOURCES.has(src))) return true;
    return Boolean(item?.is_kap || item?.isKap);
  }

  function matchesCategories(item) {
    if (!state.filters.categories.size) return true;
    const categories = getItemCategories(item)
      .map(normaliseFilterValue)
      .filter(Boolean);
    if (!categories.length) return false;
    for (const key of state.filters.categories) {
      let lookup = CATEGORY_LOOKUP[key];
      if (!lookup) {
        lookup = new Set([normaliseFilterValue(key)]);
        CATEGORY_LOOKUP[key] = lookup;
      }
      if (categories.some((cat) => lookup.has(cat))) {
        return true;
      }
    }
    return false;
  }

  function matchesSentiment(item) {
    if (!state.filters.sentiment || state.filters.sentiment === "all") return true;
    const sentiment = normaliseFilterValue(item?.sentiment);
    if (!sentiment) return false;
    let lookup = SENTIMENT_LOOKUP[state.filters.sentiment];
    if (!lookup) {
      lookup = new Set([normaliseFilterValue(state.filters.sentiment)]);
      SENTIMENT_LOOKUP[state.filters.sentiment] = lookup;
    }
    return lookup.has(sentiment);
  }

  function withinRange(item, rangeStart) {
    if (!state.filters.range || state.filters.range === "all") return true;
    if (rangeStart == null) return true;
    const ts = resolveTimestamp(item);
    if (ts === null) return false;
    return ts >= rangeStart;
  }

  function shouldRenderItem(item, opts = {}) {
    const { rangeStart = null } = opts;
    if (state.filters.kapOnly && !isKapNews(item)) return false;
    if (!matchesCategories(item)) return false;
    if (!matchesSentiment(item)) return false;
    if (!withinRange(item, rangeStart)) return false;
    return true;
  }

  if (state.symbol && symbolInput) {
    symbolInput.value = state.symbol;
    symbolClear.hidden = state.symbol.length === 0;
  }

  function setStatus(text) {
    if (statusEl) statusEl.textContent = text;
  }

  function setLive(isLive) {
    liveBadge && liveBadge.classList.toggle("off", !isLive);
  }

  function setLoading(isLoading, { reset = false } = {}) {
    state.loading = isLoading;
    if (newsLoadingEl) {
      newsLoadingEl.hidden = !isLoading;
    }
    if (isLoading && reset && newsEmptyEl) {
      newsEmptyEl.hidden = true;
    }
    if (loadMoreBtn) {
      loadMoreBtn.disabled = isLoading;
    }
  }

  function updateLastUpdate(ts) {
    if (!lastUpdateEl) return;
    if (!ts) {
      lastUpdateEl.textContent = "Son güncelleme: —";
      return;
    }
    try {
      const date = ts instanceof Date ? ts : new Date(ts);
      const formatted = date.toLocaleString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        day: "2-digit",
        month: "2-digit",
      });
      lastUpdateEl.textContent = `Son güncelleme: ${formatted}`;
    } catch (err) {
      lastUpdateEl.textContent = "Son güncelleme: —";
    }
  }

  function relativeTime(ts) {
    try {
      const date = ts instanceof Date ? ts : new Date(ts);
      if (!Number.isFinite(date.getTime())) return "";
      const diffMs = Date.now() - date.getTime();
      const diffMin = Math.round(diffMs / 60000);
      if (Math.abs(diffMin) < 1) return "Şimdi";
      if (diffMin < 60) return `${diffMin} dk önce`;
      const diffHr = Math.round(diffMs / 3600000);
      if (diffHr < 24) return `${diffHr} sa önce`;
      const diffDay = Math.round(diffMs / 86400000);
      return `${diffDay} gün önce`;
    } catch (err) {
      return "";
    }
  }

  function formatDate(ts) {
    try {
      const date = ts instanceof Date ? ts : new Date(ts);
      if (!Number.isFinite(date.getTime())) return "";
      return date.toLocaleString("tr-TR", {
        hour: "2-digit",
        minute: "2-digit",
        day: "2-digit",
        month: "short",
      });
    } catch (err) {
      return "";
    }
  }

  let symbolData = [];
  let symbolPromise = null;

  function normaliseSymbol(sym) {
    return (sym || "").toString().trim().toUpperCase();
  }
  async function refreshBrandLogo(symbol) {
    if (!brandLogo) return;
    const activeSymbol = normaliseSymbol(symbol);
    if (!activeSymbol) return;
    const endpoint = `/logo/${encodeURIComponent(activeSymbol)}`;
    try {
      const response = await fetch(endpoint, { cache: "no-store" });
      if (!response.ok) return;
      const contentType = response.headers.get("content-type") || "";
      if (contentType && !contentType.startsWith("image/")) return;
      const blob = await response.blob();
      if (!blob || blob.size === 0) return;
      const objectUrl = URL.createObjectURL(blob);
      if (brandLogoObjectUrl) {
        URL.revokeObjectURL(brandLogoObjectUrl);
      }
      brandLogo.src = objectUrl;
      brandLogoObjectUrl = objectUrl;
    } catch (err) {
      console.warn("logo fetch failed", err);
    }
  }

  window.addEventListener("beforeunload", () => {
    if (brandLogoObjectUrl) {
      URL.revokeObjectURL(brandLogoObjectUrl);
      brandLogoObjectUrl = null;
    }
  });

  async function fetchSymbolsOnce() {
    if (symbolPromise) return symbolPromise;
    symbolPromise = (async () => {
      try {
        const res = await fetch(symbolsEndpoint, { credentials: "same-origin" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const payload = await res.json();
        const items = Array.isArray(payload?.items) ? payload.items : Array.isArray(payload?.symbols) ? payload.symbols : [];
        symbolData = items
          .map((item) => ({
            symbol: normaliseSymbol(item?.symbol || item?.code),
            name: (item?.name || item?.title || "").toString(),
            sector: (item?.sector || item?.group || "").toString(),
          }))
          .filter((item) => item.symbol);
      } catch (err) {
        symbolData = [];
      }
      return symbolData;
    })();
    return symbolPromise;
  }

  function renderDropdown(matches) {
    if (!dropdownEl) return;
    dropdownEl.innerHTML = "";
    if (!matches || !matches.length) {
      dropdownEl.hidden = true;
      return;
    }
    const frag = document.createDocumentFragment();
    matches.slice(0, 12).forEach((item) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.symbol = item.symbol;
      const row = document.createElement("div");
      row.className = "ac-line";
      const symSpan = document.createElement("span");
      symSpan.className = "sym";
      symSpan.textContent = item.symbol;
      const nameSpan = document.createElement("span");
      nameSpan.className = "name";
      nameSpan.textContent = item.name || "";
      row.appendChild(symSpan);
      if (nameSpan.textContent) row.appendChild(nameSpan);
      btn.appendChild(row);
      if (item.sector) {
        const sector = document.createElement("span");
        sector.className = "sector";
        sector.textContent = item.sector;
        btn.appendChild(sector);
      }
      btn.addEventListener("click", () => {
        selectSymbol(item.symbol);
        dropdownEl.hidden = true;
      });
      frag.appendChild(btn);
    });
    dropdownEl.appendChild(frag);
    dropdownEl.hidden = false;
  }

  async function handleSymbolInput(ev) {
    const value = normaliseSymbol(ev.target.value);
    symbolClear && (symbolClear.hidden = value.length === 0);
    await fetchSymbolsOnce();
    if (!value) {
      renderDropdown([]);
      return;
    }
    const matches = symbolData.filter((item) => item.symbol.includes(value) || item.name.toUpperCase().includes(value));
    renderDropdown(matches.slice(0, 10));
  }

  function clearDropdown() {
    if (dropdownEl) dropdownEl.hidden = true;
  }

  function updateNavLinks(sym) {
    qsa("[data-symbol-link]").forEach((el) => {
      const href = el.getAttribute("href");
      if (!href) return;
      try {
        const url = new URL(href, window.location.origin);
        if (sym) url.searchParams.set("symbol", sym);
        else url.searchParams.delete("symbol");
        el.setAttribute("href", url.pathname + (url.search ? `${url.search}` : ""));
      } catch (err) { }
    });
  }

  function updateUrl(sym) {
    try {
      const url = new URL(window.location.href);
      if (sym) url.searchParams.set("symbol", sym);
      else url.searchParams.delete("symbol");
      window.history.replaceState(null, document.title, url.pathname + (url.search ? `${url.search}` : ""));
    } catch (err) { }
  }

  function resetFeed() {
    state.page = 1;
    state.cursor = null;
    state.hasMore = true;
    if (newsListEl) newsListEl.innerHTML = "";
  }

  function selectSymbol(sym) {
    const norm = normaliseSymbol(sym);
    if (!norm) return;
    state.symbol = norm;
    if (symbolInput) {
      symbolInput.value = norm;
      symbolClear && (symbolClear.hidden = false);
    }
    updateNavLinks(norm);
    updateUrl(norm);
    resetFeed();
    fetchNews({ reset: true });
  }

  function toggleChip(chip, active) {
    if (!chip) return;
    if (active) chip.classList.add("active");
    else chip.classList.remove("active");
    if (chip.hasAttribute("aria-pressed")) {
      chip.setAttribute("aria-pressed", active ? "true" : "false");
    }
  }

  function gatherCategorySelections() {
    const active = new Set();
    qsa(".chip[data-cat]", categoryGroup).forEach((chip) => {
      if (chip.classList.contains("active") && chip.dataset.cat && chip.dataset.cat !== "all") {
        active.add(chip.dataset.cat);
      }
    });
    return active;
  }

  function handleCategoryClick(ev) {
    const chip = ev.target.closest(".chip[data-cat]");
    if (!chip) return;
    const cat = chip.dataset.cat;
    if (cat === "all") {
      qsa(".chip[data-cat]", categoryGroup).forEach((c) => {
        toggleChip(c, c.dataset.cat === "all");
      });
      state.filters.categories = new Set();
    } else {
      const isActive = chip.classList.toggle("active");
      toggleChip(qs(".chip[data-cat='all']", categoryGroup), false);
      if (isActive) {
        state.filters.categories.add(cat);
      } else {
        state.filters.categories.delete(cat);
      }
      if (!state.filters.categories.size) {
        toggleChip(qs(".chip[data-cat='all']", categoryGroup), true);
      }
    }
    resetFeed();
    fetchNews({ reset: true });
  }

  function handleSentimentClick(ev) {
    const chip = ev.target.closest(".chip[data-sentiment]");
    if (!chip) return;
    const sentiment = chip.dataset.sentiment;
    qsa(".chip[data-sentiment]", sentimentGroup).forEach((c) => toggleChip(c, c === chip));
    state.filters.sentiment = sentiment;
    resetFeed();
    fetchNews({ reset: true });
  }

  function handleRangeClick(ev) {
    const chip = ev.target.closest(".chip[data-range]");
    if (!chip) return;
    qsa(".chip[data-range]", rangeGroup).forEach((c) => toggleChip(c, c === chip));
    state.filters.range = chip.dataset.range || "today";
    resetFeed();
    fetchNews({ reset: true });
  }

  if (kapToggle) {
    kapToggle.addEventListener("click", () => {
      const active = kapToggle.getAttribute("aria-pressed") === "true";
      const next = !active;
      kapToggle.setAttribute("aria-pressed", next ? "true" : "false");
      kapToggle.classList.toggle("active", next);
      state.filters.kapOnly = next;
      resetFeed();
      fetchNews({ reset: true });
    });
  }

  categoryGroup && categoryGroup.addEventListener("click", handleCategoryClick);
  sentimentGroup && sentimentGroup.addEventListener("click", handleSentimentClick);
  rangeGroup && rangeGroup.addEventListener("click", handleRangeClick);

  if (symbolInput) {
    symbolInput.addEventListener("input", handleSymbolInput);
    symbolInput.addEventListener("focus", async () => {
      await fetchSymbolsOnce();
      const value = normaliseSymbol(symbolInput.value);
      if (!value) renderDropdown(symbolData.slice(0, 10));
    });
    symbolInput.addEventListener("blur", () => {
      setTimeout(clearDropdown, 120);
    });
    symbolInput.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        const value = normaliseSymbol(symbolInput.value);
        if (value) {
          selectSymbol(value);
          clearDropdown();
        }
      }
    });
  }

  symbolClear && symbolClear.addEventListener("click", () => {
    if (!symbolInput) return;
    symbolInput.value = "";
    symbolClear.hidden = true;
    clearDropdown();
  });

  document.addEventListener("click", (ev) => {
    if (!dropdownEl) return;
    if (!dropdownEl.contains(ev.target) && !symbolInput.contains(ev.target)) {
      clearDropdown();
    }
  });

  function safeContentFragment(html) {
    if (!html) return null;
    const allowedTags = new Set(["A", "B", "STRONG", "EM", "I", "U", "P", "BR", "UL", "OL", "LI", "SPAN"]);
    const template = document.createElement("template");
    template.innerHTML = html;
    const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT, null);
    const toRemove = [];
    while (walker.nextNode()) {
      const el = walker.currentNode;
      if (!allowedTags.has(el.tagName)) {
        toRemove.push(el);
        continue;
      }
      Array.from(el.attributes).forEach((attr) => {
        const name = attr.name.toLowerCase();
        if (el.tagName === "A" && name === "href") {
          if (!/^https?:/i.test(attr.value)) {
            el.removeAttribute(attr.name);
          }
          return;
        }
        el.removeAttribute(attr.name);
      });
      if (el.tagName === "A") {
        el.setAttribute("target", "_blank");
        el.setAttribute("rel", "noopener");
      }
    }
    toRemove.forEach((node) => {
      const frag = document.createDocumentFragment();
      while (node.firstChild) frag.appendChild(node.firstChild);
      node.replaceWith(frag);
    });
    return template.content;
  }

  function appendParagraphs(container, text) {
    if (!container || !text) return;
    const parts = text.toString().split(/\n+/).map((part) => part.trim()).filter(Boolean);
    parts.forEach((part) => {
      const p = document.createElement("p");
      p.textContent = part;
      container.appendChild(p);
    });
  }
  function toPlainText(value) {
    if (value == null) return "";
    if (typeof value === "string") {
      const template = document.createElement("template");
      template.innerHTML = value;
      const text = template.content.textContent || "";
      return text.trim();
    }
    if (Array.isArray(value)) {
      return value.map((part) => toPlainText(part)).filter(Boolean).join(" ").trim();
    }
    if (typeof value === "number") {
      return value.toString();
    }
    if (typeof value === "object" && "text" in value) {
      return toPlainText(value.text);
    }
    return value.toString().trim();
  }

  function deriveSnippet(item, summary) {
    const candidates = [];
    if (summary) candidates.push(summary);
    const excerpt = item?.excerpt ?? item?.short_description ?? item?.shortDescription;
    if (excerpt) candidates.push(excerpt);
    if (item?.snippet) candidates.push(item.snippet);
    if (item?.content_preview) candidates.push(item.content_preview);
    if (item?.contentPreview) candidates.push(item.contentPreview);
    if (item?.content) candidates.push(item.content);
    if (item?.content_html) candidates.push(item.content_html);

    for (const candidate of candidates) {
      const text = toPlainText(candidate).replace(/\s+/g, " ").trim();
      if (text) return text;
    }
    return "";
  }
  function flattenAiAnalysis(item) {
    if (!item || typeof item !== "object") return item;
    const analysis = item.aiAnalysis || item.ai_analysis;
    if (!analysis || typeof analysis !== "object") return item;

    const summary = analysis.summary ?? analysis.ai_summary;
    if (summary && !item.ai_summary) {
      item.ai_summary = summary;
    }
    if (summary && !item.summary) {
      item.summary = summary;
    }
    const sentiment = analysis.sentiment;
    if (sentiment && !item.sentiment) {
      item.sentiment = sentiment;
    }
    if (sentiment && !item.ai_sentiment) {
      item.ai_sentiment = sentiment;
    }
    const importance = analysis.importance;
    if (importance && !item.ai_importance) {
      item.ai_importance = importance;
    }
    if (importance && !item.importance) {
      item.importance = importance;
    }
    const impact = analysis.impact;
    if (impact && !item.ai_impact) {
      item.ai_impact = impact;
    }
    if (impact && !item.impact) {
      item.impact = impact;
    }
    return item;
  }

  function normaliseSentiment(value) {
    const text = (value ?? "").toString().trim().toLowerCase();
    if (!text) return null;
    const positive = ["positive", "pozitif", "olumlu", "+"];
    const negative = ["negative", "negatif", "olumsuz", "-"];
    const neutral = ["neutral", "notr", "nötr", "not", "tarafsız", "tarafsiz", "0"];

    const inList = (list) => list.some((keyword) => text.startsWith(keyword));

    if (inList(positive)) {
      return { label: "Olumlu", className: "sentiment-positive" };
    }
    if (inList(negative)) {
      return { label: "Olumsuz", className: "sentiment-negative" };
    }
    if (inList(neutral)) {
      return { label: "Nötr", className: "sentiment-neutral" };
    }

    return { label: text, className: "sentiment-neutral" };
  }

  function formatAnalysisValue(value) {
    if (value === null || value === undefined) return "Belirtilmemiş";
    const str = value.toString().trim();
    return str ? str : "Belirtilmemiş";
  }
  function formatImportanceLevel(value) {
    if (value === null || value === undefined) return "Belirtilmemiş";
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      if (numeric >= 4) return "Kritik";
      if (numeric === 3) return "Çok Önemli";
      if (numeric === 2) return "Önemli";
      if (numeric === 1) return "Normal";
    }

    const str = value.toString().trim();
    if (!str) return "Belirtilmemiş";

    const normalized = str.toLowerCase();
    switch (normalized) {
      case "normal":
        return "Normal";
      case "onemli":
      case "önemli":
      case "important":
        return "Önemli";
      case "cok önemli":
      case "çok önemli":
      case "cok onemli":
      case "çok onemli":
      case "very important":
        return "Çok Önemli";
      case "kritik":
      case "critical":
        return "Kritik";
      default:
        return "Belirtilmemiş";
    }
  }

  function formatImpactHorizon(value) {
    if (value === null || value === undefined) return "Belirtilmemiş";
    const str = value.toString().trim();
    if (!str) return "Belirtilmemiş";

    const normalized = str
      .toString()
      .trim()
      .toLowerCase()
      .replace(/[_\s]+/g, "-");

    switch (normalized) {
      case "short-term":
        return "Kısa Vade";
      case "mid-term":
      case "medium-term":
        return "Orta Vade";
      case "long-term":
        return "Uzun Vade";
      default:
        return "Belirtilmemiş";
    }
  }
  let aiModalInstance = null;

  function ensureAiModal() {
    if (aiModalInstance) return aiModalInstance;

    const overlay = document.createElement("div");
    overlay.className = "ai-modal-overlay";
    overlay.id = "aiAnalysisModal";
    overlay.hidden = true;
    overlay.setAttribute("aria-hidden", "true");

    const modal = document.createElement("div");
    modal.className = "ai-modal";
    modal.setAttribute("role", "dialog");
    modal.setAttribute("aria-modal", "true");

    const closeBtn = document.createElement("button");
    closeBtn.type = "button";
    closeBtn.className = "ai-modal-close";
    closeBtn.setAttribute("aria-label", "Kapat");
    closeBtn.innerHTML = "&times;";

    const titleEl = document.createElement("h2");
    titleEl.className = "ai-modal-title";
    titleEl.id = "aiModalTitle";
    modal.setAttribute("aria-labelledby", titleEl.id);

    const body = document.createElement("div");
    body.className = "ai-modal-body";

    const spinner = document.createElement("div");
    spinner.className = "ai-modal-spinner";

    const content = document.createElement("div");
    content.className = "ai-modal-content";

    body.appendChild(spinner);
    body.appendChild(content);

    modal.appendChild(closeBtn);
    modal.appendChild(titleEl);
    modal.appendChild(body);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    const instance = {
      overlay,
      modal,
      closeBtn,
      titleEl,
      spinner,
      content,
      timerId: null,
      callbacks: {},
      triggerButton: null,
    };

    function handleClose() {
      closeAiModal();
    }

    closeBtn.addEventListener("click", handleClose);
    overlay.addEventListener("click", (ev) => {
      if (ev.target === overlay) handleClose();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape" && !overlay.hidden) {
        handleClose();
      }
    });

    aiModalInstance = instance;
    return instance;
  }

  function closeAiModal() {
    if (!aiModalInstance) return;
    const { overlay, modal, spinner, content } = aiModalInstance;
    if (aiModalInstance.timerId) {
      clearTimeout(aiModalInstance.timerId);
      aiModalInstance.timerId = null;
    }
    overlay.classList.remove("visible");
    modal.classList.remove("visible");
    overlay.setAttribute("aria-hidden", "true");
    document.documentElement.style.overflow = "";
    setTimeout(() => {
      overlay.hidden = true;
      spinner.hidden = false;
      modal.classList.remove("loading", "loaded");
      content.innerHTML = "";
    }, 320);
    const callbacks = aiModalInstance.callbacks || {};
    aiModalInstance.callbacks = {};
    const triggerButton = aiModalInstance.triggerButton;
    aiModalInstance.triggerButton = null;
    if (typeof callbacks.onClose === "function") {
      callbacks.onClose();
    }
    if (triggerButton) {
      triggerButton.classList.remove("loading");
      triggerButton.disabled = false;
      try {
        triggerButton.focus({ preventScroll: true });
      } catch (err) {
        triggerButton.focus();
      }
    }
  }

  function showAiModal(data, callbacks = {}) {
    const instance = ensureAiModal();
    const { overlay, modal, spinner, content, titleEl } = instance;
    if (instance.timerId) {
      clearTimeout(instance.timerId);
      instance.timerId = null;
    }

    instance.callbacks = {
      onLoaded: callbacks.onLoaded,
      onClose: callbacks.onClose,
    };
    instance.triggerButton = callbacks.triggerButton || null;

    overlay.hidden = false;
    overlay.setAttribute("aria-hidden", "false");
    requestAnimationFrame(() => {
      overlay.classList.add("visible");
      modal.classList.add("visible");
    });
    document.documentElement.style.overflow = "hidden";

    modal.classList.remove("loaded");
    modal.classList.add("loading");
    spinner.hidden = false;
    content.innerHTML = "";
    titleEl.textContent = data?.title || "Yapay Zeka Özeti";

    const summaryText = data?.summary || "Özet bulunamadı.";
    const sentimentLabel = data?.sentimentLabel || "Belirtilmemiş";
    const sentimentClass = data?.sentimentClass || "";
    const importanceText = formatImportanceLevel(data?.importance);
    const impactText = formatImpactHorizon(data?.impact);


    instance.timerId = window.setTimeout(() => {
      spinner.hidden = true;
      modal.classList.remove("loading");
      modal.classList.add("loaded");

      const summarySection = document.createElement("div");
      summarySection.className = "ai-modal-section";
      const summaryTitle = document.createElement("div");
      summaryTitle.className = "ai-modal-section-title";
      summaryTitle.textContent = "Özet";
      const summaryParagraph = document.createElement("p");
      summaryParagraph.className = "ai-modal-summary";
      summaryParagraph.textContent = summaryText;
      summarySection.appendChild(summaryTitle);
      summarySection.appendChild(summaryParagraph);
      content.appendChild(summarySection);

      const metricsSection = document.createElement("div");
      metricsSection.className = "ai-modal-section";
      const metricsTitle = document.createElement("div");
      metricsTitle.className = "ai-modal-section-title";
      metricsTitle.textContent = "Metrikler";
      metricsSection.appendChild(metricsTitle);

      const metricsList = document.createElement("dl");
      metricsList.className = "ai-modal-metrics";

      const metrics = [
        { label: "Duygu", value: sentimentLabel, className: sentimentClass },
        { label: "Önem", value: importanceText },
        { label: "Etki", value: impactText },
      ];

      metrics.forEach((metric) => {
        const dt = document.createElement("dt");
        dt.textContent = metric.label;
        metricsList.appendChild(dt);
        const dd = document.createElement("dd");
        dd.textContent = metric.value;
        if (metric.className) {
          dd.classList.add(metric.className);
        }
        metricsList.appendChild(dd);
      });

      metricsSection.appendChild(metricsList);
      content.appendChild(metricsSection);

      if (typeof instance.callbacks.onLoaded === "function") {
        instance.callbacks.onLoaded();
      }
    }, 2000);
  }


  function createBadge(label, extraClass = "") {
    const span = document.createElement("span");
    span.className = extraClass ? `badge-pill ${extraClass}` : "badge-pill";
    span.textContent = label;
    return span;
  }

  function renderNewsCard(item) {
    if (!newsListEl) return;
    const analysis = item?.aiAnalysis || item?.ai_analysis || {};
    const aiSummary = item?.ai_summary ?? analysis.summary ?? "";
    const fallbackSummary = item?.summary ?? "";
    const displaySummaryRaw = aiSummary || fallbackSummary;
    const aiSentimentRaw = item?.ai_sentiment ?? analysis?.sentiment ?? "";
    const displaySummary = displaySummaryRaw ? displaySummaryRaw.toString().trim() : "";
    const snippetText = deriveSnippet(item, displaySummary);

    const fallbackSentiment = item?.sentiment ?? "";
    const sentimentRaw = aiSentimentRaw || fallbackSentiment;
    const sentimentInfo = sentimentRaw ? normaliseSentiment(sentimentRaw) : null;
    const categories = getItemCategories(item);
    const publishedTs = item?.published_at || item?.publishedAt || item?.time || item?.timestamp;

    const card = document.createElement("article");
    card.className = "news-card";
    card.setAttribute("role", "article");
    card.tabIndex = 0;

    if (item?.id) card.dataset.id = item.id;

    const head = document.createElement("div");
    head.className = "news-head";

    const meta = document.createElement("div");
    meta.className = "news-meta";

    const title = document.createElement("div");
    title.className = "news-title";

    const headlineText =
      (typeof item?.headline === "string" && item.headline.trim()) ||
      (typeof item?.title === "string" && item.title.trim()) ||
      item?.title ||
      "Başlıksız haber";
    title.textContent = headlineText;

    const source = document.createElement("div");
    source.className = "news-source";
    const src = item?.source || item?.provider || "";
    const sourcePieces = [];
    if (src) sourcePieces.push(src);
    const when = formatDate(publishedTs);
    if (when) sourcePieces.push(when);
    if (sourcePieces.length) {
      source.textContent = sourcePieces.join(" • ");
    } else {
      source.hidden = true;
    }
    const timeEl = document.createElement("div");
    timeEl.className = "news-time";
    const rel = relativeTime(publishedTs);
    if (rel) {
      timeEl.textContent = rel;
    } else {
      timeEl.hidden = true;
    }

    meta.appendChild(title);
    if (!source.hidden) meta.appendChild(source);
    if (!timeEl.hidden) meta.appendChild(timeEl);

    const badgeWrap = document.createElement("div");
    badgeWrap.className = "badges";

    if (aiSummary) {
      badgeWrap.appendChild(createBadge("AI Özet"));
    }

    if (sentimentInfo) {
      badgeWrap.appendChild(createBadge(sentimentInfo.label, sentimentInfo.className));
    }

    if (isKapNews(item) || state.filters.kapOnly) {
      badgeWrap.appendChild(createBadge("KAP", "kap"));
    }

    if (Array.isArray(item?.tags)) {
      item.tags.slice(0, 2).forEach((tag) => {
        const badge = createBadge(tag.toString().toUpperCase());
        badgeWrap.appendChild(badge);
      });
    }

    head.appendChild(meta);
    if (badgeWrap.childNodes.length) head.appendChild(badgeWrap);

    const body = document.createElement("div");
    body.className = "news-body";

    const snippet = document.createElement("p");
    snippet.className = "news-snippet";
    if (snippetText) {
      snippet.textContent = snippetText;
    } else {
      snippet.textContent = "Detayları görmek için açın.";
      snippet.classList.add("fallback");
    }
    body.appendChild(snippet);

    card.appendChild(head);
    card.appendChild(body);

    const tagsEl = document.createElement("div");
    tagsEl.className = "news-tags";
    const catSet = new Set(categories.filter(Boolean).map((c) => c.toString()));
    catSet.forEach((cat) => {
      const span = document.createElement("span");
      span.textContent = cat;
      tagsEl.appendChild(span);
    });
    if (tagsEl.childNodes.length) {
      const footer = document.createElement("div");
      footer.className = "news-footer";
      footer.appendChild(tagsEl);
      card.appendChild(footer);
    }

    card.addEventListener("click", (ev) => {
      if (ev.target.closest("a, button")) return;
      openNewsModal(item);
    });

    card.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" || ev.key === " ") {
        ev.preventDefault();
        openNewsModal(item);
      }
    });
    newsListEl.appendChild(card);
  }
  function openNewsModal(item) {
    if (!modal) return;
    const analysis = item?.aiAnalysis || item?.ai_analysis || {};
    const aiSummary = item?.ai_summary ?? analysis.summary ?? "";
    const fallbackSummary = item?.summary ?? "";
    const displaySummaryRaw = aiSummary || fallbackSummary;
    const displaySummary = displaySummaryRaw ? displaySummaryRaw.toString().trim() : "";
    const aiSentimentRaw = item?.ai_sentiment ?? analysis?.sentiment ?? "";
    const fallbackSentiment = item?.sentiment ?? "";
    const sentimentRaw = aiSentimentRaw || fallbackSentiment;
    const sentimentInfo = sentimentRaw ? normaliseSentiment(sentimentRaw) : null;
    const importance = item?.ai_importance ?? analysis?.importance ?? "";
    const impact = item?.ai_impact ?? analysis?.impact ?? "";
    const hasAnalysis = Boolean(
      (analysis && (analysis.summary || analysis.sentiment || analysis.importance || analysis.impact)) ||
      aiSummary || aiSentimentRaw || importance || impact
    );
    const publishedTs = item?.published_at || item?.publishedAt || item?.time || item?.timestamp;

    const headlineText =
      (typeof item?.headline === "string" && item.headline.trim()) ||
      (typeof item?.title === "string" && item.title.trim()) ||
      item?.title ||
      "Başlıksız haber";
    if (modalTitle) {
      modalTitle.textContent = headlineText;
    }

    const categories = getItemCategories(item).filter(Boolean).map((c) => c.toString());
    if (modalMeta) {
      if (categories.length) {
        modalMeta.textContent = categories.join(" • ");
        modalMeta.hidden = false;
      } else {
        modalMeta.textContent = "";
        modalMeta.hidden = true;
      }
    }

    const rel = relativeTime(publishedTs);
    if (modalRelative) {
      if (rel) {
        modalRelative.textContent = rel;
        modalRelative.hidden = false;
      } else {
        modalRelative.textContent = "";
        modalRelative.hidden = true;
      }
    }

    const src = item?.source || item?.provider || "";
    const sourcePieces = [];
    if (src) sourcePieces.push(src);
    const when = formatDate(publishedTs);
    if (when) sourcePieces.push(when);
    if (modalSource) {
      if (sourcePieces.length) {
        modalSource.textContent = sourcePieces.join(" • ");
        modalSource.hidden = false;
      } else {
        modalSource.textContent = "";
        modalSource.hidden = true;
      }
    }

    if (modalBadges) {
      modalBadges.innerHTML = "";
      if (aiSummary) modalBadges.appendChild(createBadge("AI Özet"));
      if (sentimentInfo) modalBadges.appendChild(createBadge(sentimentInfo.label, sentimentInfo.className));
      if (isKapNews(item) || state.filters.kapOnly) modalBadges.appendChild(createBadge("KAP", "kap"));
      if (Array.isArray(item?.tags)) {
        item.tags.forEach((tag) => {
          modalBadges.appendChild(createBadge(tag.toString().toUpperCase()));
        });
      }
      modalBadges.hidden = modalBadges.childNodes.length === 0;
    }

    if (modalBody) {
      modalBody.innerHTML = "";
      if (displaySummary) {
        const summary = document.createElement("p");
        summary.className = "summary";
        summary.textContent = displaySummary;
        modalBody.appendChild(summary);
      }
      let hasDetails = false;
      if (item?.content_html) {
        const frag = safeContentFragment(item.content_html);
        if (frag && frag.childNodes.length) {
          modalBody.appendChild(frag);
          hasDetails = true;
        }
      } else if (item?.content) {
        const frag = safeContentFragment(item.content);
        if (frag && frag.childNodes.length) {
          modalBody.appendChild(frag);
          hasDetails = true;
        }
      }

      const excerpt = item?.excerpt ?? item?.content_preview ?? item?.contentPreview;
      if (!hasDetails && excerpt && (!displaySummary || toPlainText(excerpt) !== displaySummary)) {
        appendParagraphs(modalBody, excerpt);
        hasDetails = true;
      }

      if (!modalBody.childNodes.length) {
        const fallback = document.createElement("p");
        fallback.className = "summary fallback";
        fallback.textContent = "Bu haber için ayrıntı bulunamadı.";
        modalBody.appendChild(fallback);
      }

      modalBody.scrollTop = 0;
    }
    const actions = document.createElement("div");
    actions.className = "ai-summary-actions";
    const aiButton = document.createElement("button");
    aiButton.type = "button";
    aiButton.className = "ai-summary-button";
    aiButton.textContent = "Yapay Zeka’ya Özet Çıkar";
    actions.appendChild(aiButton);

    if (!hasAnalysis) {
      aiButton.disabled = true;
      aiButton.classList.add("disabled");
      aiButton.setAttribute("aria-disabled", "true");
      aiButton.textContent = "Yapay Zeka Analizi Yok";
      aiButton.title = "Bu haber için yapay zeka verisi bulunamadı.";
    } else {
      aiButton.addEventListener("click", () => {
        aiButton.classList.add("loading");
        aiButton.disabled = true;
        const sentimentLabel = aiSentimentRaw && sentimentInfo
          ? sentimentInfo.label
          : formatAnalysisValue(sentimentRaw);
        showAiModal(
          {
            title: item?.title || headlineText || "Yapay Zeka Özeti",
            summary: displaySummary || "Özet bulunamadı.",
            sentimentLabel,
            sentimentClass: aiSentimentRaw && sentimentInfo ? sentimentInfo.className : "",
            importance,
            impact,
          },
          {
            triggerButton: aiButton,
            onLoaded: () => {
              aiButton.classList.remove("loading");
              aiButton.disabled = false;
            },
            onClose: () => {
              aiButton.classList.remove("loading");
              aiButton.disabled = false;
            },
          },
        );
      });
    }

    body.appendChild(actions);
    if (modalAnalysis) {
      modalAnalysis.innerHTML = "";
      modalAnalysis.hidden = true;


    }

    if (modalTags) {
      modalTags.innerHTML = "";
      const tagSet = new Set();
      categories.forEach((cat) => tagSet.add(cat));
      if (Array.isArray(item?.tags)) {
        item.tags.forEach((tag) => {
          const text = tag?.toString?.();
          if (text) tagSet.add(text);
        });
      }
      tagSet.forEach((tag) => {
        const span = document.createElement("span");
        span.textContent = tag;
        modalTags.appendChild(span)
      });
      modalTags.hidden = modalTags.childNodes.length === 0;
    }

    if (modalLink) {
      if (item?.url) {
        modalLink.href = item.url;
        modalLink.hidden = false;
      } else {
        modalLink.hidden = true;
      }
    }
    const wasHidden = modal.hidden;
    if (modal.hidden) {
      modal.hidden = false;
    }
    modal.setAttribute("aria-hidden", "false");
    if (modalBackdrop) {
      if (modalBackdrop.hidden) modalBackdrop.hidden = false;
      modalBackdrop.setAttribute("aria-hidden", "false");
    }

    if (modalBody) modalBody.scrollTop = 0;
    if (modalSurface) modalSurface.scrollTop = 0;

    requestAnimationFrame(() => {
      modal.classList.add("is-active");
      modalBackdrop && modalBackdrop.classList.add("is-active");
      (modalClose || modalSurface)?.focus?.();
    });

    if (wasHidden) {
      lockScroll();
    }
  }

  function closeModal() {
    if (!modal || modal.hidden) return;
    modal.classList.remove("is-active");
    modalBackdrop && modalBackdrop.classList.remove("is-active");
    let cleaned = false;
    const cleanup = () => {
      if (cleaned) return;
      cleaned = true;
      modal.hidden = true;
      modal.setAttribute("aria-hidden", "true");
      if (modalBackdrop) {
        modalBackdrop.hidden = true;
        modalBackdrop.setAttribute("aria-hidden", "true");
      }
      unlockScroll();
    };

    const handle = (ev) => {
      if (ev.target === modal && ev.propertyName === "opacity") {
        modal.removeEventListener("transitionend", handle);
        cleanup();
      }
    };

    modal.addEventListener("transitionend", handle);
    setTimeout(() => {
      modal.removeEventListener("transitionend", handle);
      cleanup();
    }, 360);
  }



  async function fetchNews({ reset = false } = {}) {
    if (state.loading) return;
    if (reset) {
      if (newsListEl) newsListEl.innerHTML = "";
      if (newsEmptyEl) newsEmptyEl.hidden = true;
    }
    setStatus("Haberler yükleniyor…");
    setLoading(true, { reset });
    try {
      const params = new URLSearchParams();
      if (state.symbol) params.set("symbol", state.symbol);
      if (state.page) params.set("page", String(state.page));
      params.set("size", String(PAGE_SIZE));
      if (state.cursor) params.set("cursor", state.cursor);

      const url = `${newsEndpoint}?${params.toString()}`;
      const res = await fetch(url, { credentials: "same-origin" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      const items = Array.isArray(payload?.items)
        ? payload.items
        : Array.isArray(payload?.results)
          ? payload.results
          : [];
      const normalisedItems = items.map((entry) => {
        try {
          return flattenAiAnalysis(entry);
        } catch (err) {
          return entry;
        }
      });

      const rangeStart = getRangeThreshold(state.filters.range);
      const filteredItems = normalisedItems.filter((item) => {
        try {
          return shouldRenderItem(item, { rangeStart });
        } catch (err) {
          return false;
        }
      });

      if (!filteredItems.length && reset) {
        if (newsEmptyEl) newsEmptyEl.hidden = false;
      } else if (filteredItems.length && newsEmptyEl) {
        newsEmptyEl.hidden = true;
      }

      filteredItems.forEach((item) => {
        try { renderNewsCard(item); } catch (err) { }
      });

      const nextCursor = payload?.nextCursor || payload?.next_cursor || null;
      const nextPage = payload?.nextPage || payload?.next_page || null;
      const hasMoreFlag = payload?.hasMore ?? payload?.has_more;
      state.cursor = nextCursor || null;
      if (state.cursor) {
        state.hasMore = true;
      } else if (typeof hasMoreFlag === "boolean") {
        state.hasMore = hasMoreFlag;
      } else if (typeof nextPage === "number") {
        state.hasMore = nextPage > state.page;
      } else {
        state.hasMore = items.length > 0;
      }

      if (typeof nextPage === "number") {
        state.page = nextPage;
      } else if (items.length) {
        state.page += 1;
      }

      const showLoadMore = state.hasMore && (filteredItems.length > 0 || !reset);
      if (loadMoreBtn) {
        loadMoreBtn.hidden = !showLoadMore;
      }

      if (filteredItems.length) {
        setStatus(`${filteredItems.length} haber yüklendi`);
        updateLastUpdate(new Date());
        setLive(true);
      } else {
        if (reset) {
          setStatus("Bu filtrelerle haber bulunamadı");
        } else {
          setStatus("Yeni haber yok");
        }
        setLive(false);
      }
    } catch (err) {
      console.error("news fetch failed", err);
      setStatus("Haberler alınırken hata oluştu");
      setLive(false);
    } finally {
      setLoading(false);
    }
  }

  loadMoreBtn && loadMoreBtn.addEventListener("click", () => {
    if (!state.hasMore) return;
    fetchNews();
  });

  function openDrawer() {
    if (drawer && !drawer.classList.contains("open")) {
      drawer.classList.add("open");
      lockScroll();
    } backdrop && backdrop.classList.add("show");
    document.documentElement.style.overflow = "hidden";
  }

  function closeDrawer() {
    drawer && drawer.classList.remove("open");
    backdrop && backdrop.classList.remove("show");
  }

  btnMenu && btnMenu.addEventListener("click", openDrawer);
  btnCloseDrawer && btnCloseDrawer.addEventListener("click", closeDrawer);
  backdrop && backdrop.addEventListener("click", closeDrawer);
  modalClose && modalClose.addEventListener("click", closeModal);
  modalBackdrop && modalBackdrop.addEventListener("click", closeModal);
  modal && modal.addEventListener("click", (ev) => {
    if (ev.target === modal) {
      closeModal();
    }
  });
  if (btnInfo && infoPanel) {
    btnInfo.addEventListener("click", () => {
      infoPanel.hidden = !infoPanel.hidden;
    });
  }

  infoClose && infoClose.addEventListener("click", () => {
    if (infoPanel) infoPanel.hidden = true;
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") {
      if (modal && !modal.hidden) {
        closeModal();
        return;
      }
      closeDrawer();
      if (infoPanel) infoPanel.hidden = true;
    }
  });

  function init() {
    const webApp = window.Telegram?.WebApp;
    try {
      webApp?.ready?.();
      webApp?.expand?.();
      webApp?.disableVerticalSwipe?.();
      webApp?.enableClosingConfirmation?.(false);
      webApp?.MainButton?.hide?.();
    } catch (err) { }

    if (!state.symbol && symbolInput?.value) {
      state.symbol = normaliseSymbol(symbolInput.value);
    }
    if (!state.symbol) {
      const url = new URL(window.location.href);
      state.symbol = normaliseSymbol(url.searchParams.get("symbol") || "");
    }
    if (state.symbol && symbolInput) {
      symbolInput.value = state.symbol;
      symbolClear && (symbolClear.hidden = false);
    }
    updateNavLinks(state.symbol);
    updateUrl(state.symbol);
    refreshBrandLogo(state.symbol);
    fetchNews({ reset: true });
  }

  init();
})();