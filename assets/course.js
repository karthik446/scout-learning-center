(function () {
  document.documentElement.classList.add("js");

  function currentTheme() {
    return document.documentElement.getAttribute("data-theme") === "dark" ? "dark" : "light";
  }

  function applyHljsTheme(theme) {
    document.querySelectorAll("link[data-hljs-theme]").forEach(function (link) {
      link.disabled = link.getAttribute("data-hljs-theme") !== theme;
    });
  }

  function highlightCode() {
    if (window.hljs) {
      document.querySelectorAll("pre code[data-lang]").forEach(function (block) {
        try {
          block.removeAttribute("data-highlighted");
          window.hljs.highlightElement(block);
        } catch (e) { /* leave plain */ }
      });
    }
  }

  // Mermaid configuration is global: finish legacy diagrams before the standard
  // v2 sequences, and serialize theme changes through the same queue.
  var mermaidRender = Promise.resolve();
  function renderMermaid(theme) {
    if (!window.mermaid) { return; }
    mermaidRender = mermaidRender.then(async function () {
      var styled = [];
      var ordinary = [];
      document.querySelectorAll(".mermaid").forEach(function (el) {
        if (!el.hasAttribute("data-src")) { el.setAttribute("data-src", el.textContent); }
        el.removeAttribute("data-processed");
        el.textContent = el.getAttribute("data-src");
        (el.parentElement.getAttribute("data-diagram-style") === "sequence" ? styled : ordinary).push(el);
      });
      window.mermaid.initialize({
        startOnLoad: false,
        theme: theme === "dark" ? "dark" : "default",
        securityLevel: "strict",
      });
      if (ordinary.length) { await window.mermaid.run({ nodes: ordinary }); }
      if (!styled.length) { return; }
      var dark = theme === "dark";
      var fg = dark ? "#e6e6e6" : "#1a1a1a";
      var line = dark ? "#b3b3b3" : "#4d4d4d";
      var border = dark ? "#7b8aa5" : "#8795b1";
      var chip = dark ? "#22273a" : "#eef2ff";
      // The operator accepted news-feed's pixels before the standard rollout.
      var accepted = window.location.pathname === "/learn/lessons/sd-ex-news-feed/";
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
        themeVariables: {
          darkMode: dark, fontSize: "16px",
          primaryColor: chip, primaryTextColor: fg, primaryBorderColor: border,
          lineColor: line, actorBkg: chip, actorBorder: border, actorTextColor: fg,
          signalColor: line, signalTextColor: fg,
          noteBkgColor: dark ? "#1d2024" : "#f6f8fa",
          noteTextColor: fg, noteBorderColor: border,
          labelBoxBkgColor: chip, labelBoxBorderColor: border,
          labelTextColor: fg, loopTextColor: fg,
        },
        sequence: {
          useMaxWidth: true, actorMargin: accepted ? 36 : 4, width: accepted ? 130 : 120, height: 44,
          boxMargin: 12, boxTextMargin: 8, noteMargin: 16, messageMargin: 36,
          labelBoxWidth: accepted ? 50 : 35,
          mirrorActors: false, wrap: true, wrapPadding: accepted ? 12 : 4,
        },
      });
      await window.mermaid.run({ nodes: styled });
      if (!accepted) {
        styled.forEach(function (el) {
          el.querySelectorAll(".sequenceNumber").forEach(function (number) {
            number.style.fontSize = "16px";
          });
          var svg = el.querySelector("svg");
          var view = svg.viewBox.baseVal;
          var left = view.x, top = view.y, right = view.x + view.width, bottom = view.y + view.height;
          // Fit overflowing notes/text, never Mermaid's deliberately clipped
          // actor lifelines: their getBBox() extends far beyond the last call.
          svg.querySelectorAll("text, rect.note").forEach(function (label) {
            var box = label.getBBox();
            left = Math.min(left, box.x - 4); top = Math.min(top, box.y - 4);
            right = Math.max(right, box.x + box.width + 4);
            bottom = Math.max(bottom, box.y + box.height + 4);
          });
          if (left !== view.x || top !== view.y || right !== view.x + view.width || bottom !== view.y + view.height) {
            svg.setAttribute("viewBox", [left, top, right - left, bottom - top].join(" "));
            svg.style.maxWidth = (right - left) + "px";
          }
        });
      }
    }).catch(function () { /* fallback text stays visible */ });
  }

  applyHljsTheme(currentTheme());
  highlightCode();
  renderMermaid(currentTheme());

  var toggleBtn = document.getElementById("theme-toggle");
  function updateToggleLabel(theme) {
    if (!toggleBtn) { return; }
    var label = toggleBtn.querySelector(".theme-toggle-label");
    if (theme === "dark") {
      if (label) { label.textContent = "Dark"; }
    } else {
      if (label) { label.textContent = "Light"; }
    }
  }
  updateToggleLabel(currentTheme());

  if (toggleBtn) {
    toggleBtn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { window.name = "course-theme:" + next; } catch (e) { /* window.name unavailable */ }
      try { window.localStorage.setItem("course-theme", next); } catch (e) { /* no storage available */ }
      updateToggleLabel(next);
      applyHljsTheme(next);
      renderMermaid(next);
    });
  }

  var toggles = document.querySelectorAll(".toc-module > summary");
  toggles.forEach(function (s) { s.addEventListener("click", function () {}); });

  var searchInput = document.getElementById("sidebar-search-input");
  if (searchInput) {
    searchInput.addEventListener("input", function () {
      var q = searchInput.value.trim().toLowerCase();
      document.querySelectorAll("nav.sidebar details.toc-module").forEach(function (mod) {
        var items = mod.querySelectorAll("ul.module-lessons > li");
        var anyVisible = false;
        items.forEach(function (li) {
          var title = li.getAttribute("data-lesson-title") || "";
          var match = !q || title.indexOf(q) !== -1;
          li.classList.toggle("lesson-hidden", !match);
          if (match) { anyVisible = true; }
        });
        mod.classList.toggle("module-hidden", !anyVisible);
        if (q && anyVisible) { mod.setAttribute("open", ""); }
      });
    });
  }
})();
