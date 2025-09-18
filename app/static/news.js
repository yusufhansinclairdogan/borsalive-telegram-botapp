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

  const symbolsEndpoint = window.SYMBOLS_API || "/api/sectoral-brief";
  const newsEndpoint = window.NEWS_API || "/api/news";

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

  function createBadge(label, extraClass = "") {
    const span = document.createElement("span");
    span.className = extraClass ? `badge-pill ${extraClass}` : "badge-pill";
    span.textContent = label;
    return span;
  }

  function renderNewsCard(item) {
    if (!newsListEl) return;
    const card = document.createElement("article");
    card.className = "news-card";
    card.setAttribute("role", "article");
    if (item?.id) card.dataset.id = item.id;

    const head = document.createElement("div");
    head.className = "news-head";

    const meta = document.createElement("div");
    meta.className = "news-meta";

    const title = document.createElement("div");
    title.className = "news-title";
    title.textContent = item?.title || "Başlıksız haber";

    const source = document.createElement("div");
    source.className = "news-source";
    const src = item?.source || item?.provider || "";
    const categories = Array.isArray(item?.categories) ? item.categories : (item?.category ? [item.category] : []);
    const sourcePieces = [];
    if (src) sourcePieces.push(src);
    const when = formatDate(item?.published_at || item?.publishedAt || item?.time || item?.timestamp);
    if (when) sourcePieces.push(when);
    source.textContent = sourcePieces.join(" • ");

    const timeEl = document.createElement("div");
    timeEl.className = "news-time";
    const rel = relativeTime(item?.published_at || item?.publishedAt || item?.time || item?.timestamp);
    timeEl.textContent = rel;

    meta.appendChild(title);
    meta.appendChild(source);
    meta.appendChild(timeEl);

    const badgeWrap = document.createElement("div");
    badgeWrap.className = "badges";

    if (item?.ai_summary || item?.summary) {
      badgeWrap.appendChild(createBadge("AI Özet"));
    }

    const sentiment = (item?.sentiment || "").toString().toLowerCase();
    if (sentiment) {
      let cls = "sentiment-neutral";
      let label = "Nötr";
      if (sentiment.startsWith("pos")) {
        cls = "sentiment-positive";
        label = "Olumlu";
      } else if (sentiment.startsWith("neg")) {
        cls = "sentiment-negative";
        label = "Olumsuz";
      }
      badgeWrap.appendChild(createBadge(label, cls));
    }

    if (item?.is_kap || state.filters.kapOnly) {
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

    if (item?.ai_summary) {
      const summary = document.createElement("p");
      summary.textContent = item.ai_summary;
      summary.classList.add("summary");
      body.appendChild(summary);
    } else if (item?.summary) {
      const summary = document.createElement("p");
      summary.textContent = item.summary;
      summary.classList.add("summary");
      body.appendChild(summary);
    }

    if (item?.content_html) {
      const frag = safeContentFragment(item.content_html);
      if (frag) body.appendChild(frag);
    } else if (item?.content) {
      const frag = safeContentFragment(item.content);
      if (frag) body.appendChild(frag);
    } else if (item?.excerpt) {
      appendParagraphs(body, item.excerpt);
    }

    const footer = document.createElement("div");
    footer.className = "news-footer";

    const tagsEl = document.createElement("div");
    tagsEl.className = "news-tags";
    const catSet = new Set(categories.filter(Boolean).map((c) => c.toString()));
    catSet.forEach((cat) => {
      const span = document.createElement("span");
      span.textContent = cat;
      tagsEl.appendChild(span);
    });
    if (tagsEl.childNodes.length) footer.appendChild(tagsEl);

    if (item?.url) {
      const link = document.createElement("a");
      link.className = "news-link";
      link.href = item.url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = "Habere git";
      footer.appendChild(link);
    }

    card.appendChild(head);
    card.appendChild(body);
    if (footer.childNodes.length) card.appendChild(footer);

    newsListEl.appendChild(card);
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
      if (state.filters.kapOnly) params.set("kap", "true");
      if (state.filters.categories.size) params.set("categories", Array.from(state.filters.categories).join(","));
      if (state.filters.sentiment && state.filters.sentiment !== "all") params.set("sentiment", state.filters.sentiment);
      if (state.filters.range && state.filters.range !== "today") params.set("range", state.filters.range);
      if (state.page) params.set("page", String(state.page));
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

      if (!items.length && reset) {
        if (newsEmptyEl) newsEmptyEl.hidden = false;
        setStatus("Haber bulunamadı");
        setLive(false);
        loadMoreBtn && (loadMoreBtn.hidden = true);
        return;
      }

      items.forEach((item) => {
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

      loadMoreBtn && (loadMoreBtn.hidden = !state.hasMore);
      if (!state.hasMore) {
        loadMoreBtn && (loadMoreBtn.hidden = true);
      }

      if (items.length) {
        setStatus(`${items.length} haber yüklendi`);
        updateLastUpdate(new Date());
        setLive(true);
      } else {
        setStatus("Yeni haber yok");
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
    drawer && drawer.classList.add("open");
    backdrop && backdrop.classList.add("show");
    document.documentElement.style.overflow = "hidden";
  }

  function closeDrawer() {
    drawer && drawer.classList.remove("open");
    backdrop && backdrop.classList.remove("show");
    document.documentElement.style.overflow = "";
  }

  btnMenu && btnMenu.addEventListener("click", openDrawer);
  btnCloseDrawer && btnCloseDrawer.addEventListener("click", closeDrawer);
  backdrop && backdrop.addEventListener("click", closeDrawer);

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
      closeDrawer();
      if (infoPanel) infoPanel.hidden = true;
    }
  });

  function init() {
    try { window.Telegram?.WebApp?.ready?.(); } catch (err) { }
    try { window.Telegram?.WebApp?.expand?.(); } catch (err) { }

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
    fetchNews({ reset: true });
  }

  init();
})();