// TrueCheck — интерактив фронтенда: сплэш, табы, drag&drop, появления.
(function () {
  "use strict";

  // ---- приветственный сплэш (один раз за сессию) ----
  const splash = document.getElementById("splash");
  if (splash) {
    const seen = sessionStorage.getItem("tc_splash");
    if (seen) {
      splash.remove();
    } else {
      sessionStorage.setItem("tc_splash", "1");
      setTimeout(() => splash.classList.add("gone"), 1700);
      splash.addEventListener("transitionend", () => splash.remove());
    }
  }

  // ---- сегментированные табы (Файл / Текст / Ссылка) ----
  const segBtns = document.querySelectorAll(".seg-btn");
  segBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      const tab = btn.dataset.tab;
      segBtns.forEach((b) => b.classList.toggle("active", b === btn));
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.toggle("hidden", t.dataset.tab !== tab);
      });
    });
  });

  // ---- drag & drop + имя выбранного файла ----
  document.querySelectorAll(".drop").forEach((drop) => {
    const input = drop.querySelector("input[type=file]");
    const title = drop.querySelector(".drop-title");
    const base = title ? title.textContent : "";
    ["dragenter", "dragover"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
    ["dragleave", "drop"].forEach((ev) =>
      drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
    drop.addEventListener("drop", (e) => {
      if (e.dataTransfer && e.dataTransfer.files.length && input) {
        input.files = e.dataTransfer.files;
        update(input, title, base);
        runProgress(drop, input.files);
      }
    });
    if (input) input.addEventListener("change", () => {
      update(input, title, base);
      runProgress(drop, input.files);
    });
  });

  function update(input, title, base) {
    if (!title) return;
    const f = input.files;
    title.textContent = !f.length ? base
      : f.length === 1 ? f[0].name
      : `Выбрано файлов: ${f.length}`;
  }

  // ---- шкала загрузки файла 0–100% → «ОК, файл загружен» ----
  function runProgress(drop, files) {
    if (!files || !files.length) return;
    let bar = drop.querySelector(".up-bar");
    if (!bar) {
      bar = document.createElement("div");
      bar.className = "up-bar";
      bar.innerHTML = '<div class="up-track"><i></i></div><span class="up-pct">0%</span>'
                    + '<div class="up-ok" hidden></div>';
      drop.appendChild(bar);
    }
    bar.classList.remove("done");
    const fill = bar.querySelector(".up-track i");
    const pct = bar.querySelector(".up-pct");
    const ok = bar.querySelector(".up-ok");
    ok.hidden = true;
    fill.style.width = "0%"; pct.textContent = "0%";

    const list = Array.from(files);
    const total = list.reduce((s, f) => s + f.size, 0) || 1;
    let done = 0, i = 0;

    const render = (cur) => {
      const p = Math.min(100, Math.round((cur / total) * 100));
      fill.style.width = p + "%";
      pct.textContent = p + "%";
    };
    const finish = () => {
      render(total);
      bar.classList.add("done");
      ok.hidden = false;
      ok.textContent = list.length > 1
        ? `✓ ОК, файлы загружены (${list.length})`
        : "✓ ОК, файл загружен";
    };
    const readNext = () => {
      if (i >= list.length) { finish(); return; }
      const f = list[i];
      const fr = new FileReader();
      // мелкие файлы читаются мгновенно — гарантируем видимый шаг шкалы
      fr.onprogress = (e) => { if (e.lengthComputable) render(done + e.loaded); };
      fr.onloadend = () => { done += f.size; i++; render(done); setTimeout(readNext, 120); };
      fr.onerror = () => { i++; readNext(); };
      fr.readAsArrayBuffer(f);
    };
    readNext();
  }

  // ---- появление элементов при скролле ----
  const reveals = document.querySelectorAll(".reveal");
  if ("IntersectionObserver" in window && reveals.length) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((e) => {
        if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); }
      });
    }, { threshold: 0.12 });
    reveals.forEach((el) => io.observe(el));
  } else {
    reveals.forEach((el) => el.classList.add("in"));
  }

  // ---- параллакс фона за курсором (ТОЛЬКО мышь; на сенсоре выключен,
  //      иначе при скролле фон сдвигается и оголяет белую полосу) ----
  const bg = document.querySelector(".bg");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const finePointer = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  if (bg && !reduce && finePointer) {
    bg.style.transition = "transform .25s ease-out";
    window.addEventListener("mousemove", (e) => {
      const dx = (e.clientX / window.innerWidth - 0.5) * 22;
      const dy = (e.clientY / window.innerHeight - 0.5) * 22;
      bg.style.transform = `translate(${dx}px, ${dy}px)`;
    }, { passive: true });
  }

  // ---- анимированный счётчик (балл соответствия) ----
  const counters = document.querySelectorAll(".js-count");
  counters.forEach((el) => {
    const to = parseInt(el.dataset.to || "0", 10);
    if (reduce) { el.textContent = to; return; }
    let cur = 0;
    const t0 = performance.now(), dur = 1100;
    const tick = (t) => {
      const p = Math.min(1, (t - t0) / dur);
      const eased = 1 - Math.pow(1 - p, 3);
      el.textContent = Math.round(eased * to);
      if (p < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });

  // ---- состояние кнопки при отправке (проверка может идти долго) ----
  const form = document.getElementById("form");
  if (form) {
    form.addEventListener("submit", () => {
      const btn = form.querySelector("button[type=submit]");
      if (btn) { btn.disabled = true; btn.textContent = "Проверяем…"; btn.classList.add("loading"); }
    });
  }

  // ---- отчёт: фильтр эпизодов по статусу (клик по чипу) ----
  const chips = document.querySelectorAll("#chips .chip");
  if (chips.length) {
    const eps = document.querySelectorAll(".ep");
    chips.forEach((chip) => chip.addEventListener("click", () => {
      const st = chip.dataset.st || "";
      chips.forEach((c) => c.classList.toggle("active", c === chip));
      eps.forEach((ep) => { ep.style.display = (!st || ep.dataset.st === st) ? "" : "none"; });
    }));
  }

  // ---- отчёт: подсветка ссылок прямо в тексте эпизода ----
  const cite = /(\[[^\]\n]{1,40}\]|https?:\/\/[^\s<]+|10\.\d{4,9}\/[^\s<]+)/g;
  document.querySelectorAll(".ep-text").forEach((el) => {
    el.innerHTML = el.innerHTML.replace(cite, '<span class="cite-hl">$1</span>');
  });
})();
