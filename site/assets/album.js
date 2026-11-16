(() => {
  // Routes: "#/" is the index, "#/<series>/<page>" a page of one series (page 0 is its title).
  // Series never link to each other; the only way between them is back through the index.
  const cover = document.querySelector(".cover");
  const reader = document.querySelector(".reader");
  const stage = reader.querySelector(".stage");
  const title = reader.querySelector(".reader-title");
  const counter = reader.querySelector(".counter");
  const prev = reader.querySelector(".prev");
  const next = reader.querySelector(".next");
  const back = reader.querySelector(".back");

  const series = new Map([...document.querySelectorAll(".series")].map((section) => [section.id, {
    section,
    head: section.querySelector(".series-head"),
    figures: [...section.querySelectorAll("figure")],
  }]));

  const GAP = 16;
  // A row may share a page only if its photos stay nearly as tall as the page allows:
  // a whole short series (e.g. three portraits) at FIT, otherwise a pair at PAIR.
  const FIT = 0.85;
  const PAIR = 0.9;

  let current = null; // { id, page }
  let pages = [];

  const box = () => {
    const style = getComputedStyle(stage);
    return {
      w: stage.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight),
      h: stage.clientHeight - parseFloat(style.paddingTop) - parseFloat(style.paddingBottom),
    };
  };

  const ratio = (figure) => parseFloat(figure.dataset.ar);

  // Height the figures get when laid side by side in the stage.
  const rowHeight = (figures, { w, h }) =>
    Math.min(h, (w - GAP * (figures.length - 1)) / figures.reduce((sum, f) => sum + ratio(f), 0));

  const paginate = (figures, size) => {
    if (figures.length <= 3 && rowHeight(figures, size) >= FIT * size.h) return [figures];
    const result = [];
    for (let i = 0; i < figures.length; i++) {
      const pair = figures.slice(i, i + 2);
      if (pair.length === 2 && rowHeight(pair, size) >= PAIR * size.h) {
        result.push(pair);
        i++;
      } else {
        result.push([figures[i]]);
      }
    }
    return result;
  };

  const layout = (figures) => {
    const size = box();
    const h = rowHeight(figures, size);
    for (const figure of figures) {
      const w = ratio(figure) * h;
      figure.style.width = `${w}px`;
      figure.style.height = `${h}px`;
      const img = figure.querySelector("img");
      img.sizes = `${Math.ceil(w)}px`;
      img.loading = "eager";
    }
  };

  const warm = (figures = []) => {
    const size = box();
    const h = rowHeight(figures, size);
    for (const figure of figures) {
      const source = figure.querySelector("img");
      const img = new Image();
      img.sizes = `${Math.ceil(ratio(figure) * h)}px`;
      img.srcset = source.srcset;
    }
  };

  const render = () => {
    const entry = series.get(current.id);
    const { page } = current;
    const last = pages.length; // pages[] holds photo pages; page 0 is the title

    stage.replaceChildren();
    const sheet = document.createElement("div");
    sheet.className = page === 0 ? "sheet sheet-title" : "sheet";
    if (page === 0) {
      const head = entry.head.cloneNode(true);
      const count = document.createElement("p");
      count.className = "count";
      count.textContent = `${entry.figures.length} photographs`;
      head.append(count);
      sheet.append(head);
    } else {
      const figures = pages[page - 1];
      sheet.append(...figures);
      layout(figures);
    }
    stage.append(sheet);
    requestAnimationFrame(() => sheet.classList.add("shown"));

    title.textContent = page === 0 ? "" : `${entry.section.dataset.number}  ${entry.section.dataset.title}`;
    title.lang = entry.section.lang;
    if (page === 0) {
      counter.textContent = "";
    } else {
      const figures = pages[page - 1];
      const first = entry.figures.indexOf(figures[0]) + 1;
      const end = first + figures.length - 1;
      counter.textContent = `${first === end ? first : `${first}–${end}`} / ${entry.figures.length}`;
    }
    prev.hidden = page === 0;
    next.hidden = page === last;
    back.hidden = page !== last;
    warm(pages[page]);
  };

  const open = (id, page) => {
    const entry = series.get(id);
    if (!entry) return showIndex();
    cover.hidden = true;
    reader.hidden = false; // the stage must be visible before it can be measured
    pages = paginate(entry.figures, box());
    current = { id, page: Math.max(0, Math.min(page, pages.length)) };
    document.title = `${entry.section.dataset.title} — ${document.querySelector("h1").textContent}`;
    render();
  };

  const showIndex = () => {
    current = null;
    reader.hidden = true;
    cover.hidden = false;
    stage.replaceChildren();
    document.title = document.querySelector("h1").textContent;
  };

  const route = () => {
    const [id, page] = decodeURIComponent(location.hash).replace(/^#\/?/, "").split("/");
    if (!id) return showIndex();
    if (current && current.id === id) {
      current.page = Math.max(0, Math.min(parseInt(page, 10) || 0, pages.length));
      render();
    } else {
      open(id, parseInt(page, 10) || 0);
    }
  };

  const go = (delta) => {
    if (!current) return;
    const page = current.page + delta;
    if (page < 0 || page > pages.length) return;
    // Replace rather than push, so the browser's back button returns to the index.
    location.replace(`#/${current.id}/${page}`);
  };

  prev.addEventListener("click", () => go(-1));
  next.addEventListener("click", () => go(1));

  document.addEventListener("keydown", (event) => {
    if (!current || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === "ArrowRight" || event.key === " " || event.key === "PageDown") go(1);
    else if (event.key === "ArrowLeft" || event.key === "PageUp") go(-1);
    else if (event.key === "Escape") location.hash = "#/";
    else return;
    event.preventDefault();
  });

  let startX = null;
  stage.addEventListener("touchstart", (event) => { startX = event.touches[0].clientX; }, { passive: true });
  stage.addEventListener("touchend", (event) => {
    if (startX === null) return;
    const dx = event.changedTouches[0].clientX - startX;
    if (Math.abs(dx) > 40) go(dx < 0 ? 1 : -1);
    startX = null;
  });

  // Re-paginate on resize, keeping the first photo of the current page in view.
  let resizeTimer;
  addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (!current) return;
      const entry = series.get(current.id);
      const anchor = current.page > 0 ? pages[current.page - 1][0] : null;
      pages = paginate(entry.figures, box());
      if (anchor) current.page = pages.findIndex((p) => p.includes(anchor)) + 1;
      location.replace(`#/${current.id}/${current.page}`);
      render();
    }, 150);
  });

  // Index preview: hovering or focusing a series shows its photo; leaving the list keeps
  // the last one, so the cover never falls back to empty.
  const previews = [...cover.querySelectorAll(".preview img")];
  const caption = cover.querySelector(".preview figcaption");
  const showPreview = (slug) => {
    const img = previews.find((p) => p.dataset.series === slug);
    if (!img || img.classList.contains("active")) return;
    previews.forEach((p) => p.classList.toggle("active", p === img));
    caption.querySelector(".num").textContent = img.dataset.number;
    const name = caption.querySelector(".name");
    name.textContent = img.dataset.title;
    name.lang = series.get(slug).section.lang;
  };
  for (const link of cover.querySelectorAll(".index a")) {
    const slug = link.hash.replace(/^#\//, "");
    link.addEventListener("pointerenter", () => showPreview(slug));
    link.addEventListener("focus", () => showPreview(slug));
  }

  addEventListener("hashchange", route);
  route();
})();
