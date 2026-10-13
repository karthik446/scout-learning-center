/* The search page: ONE search box (the site's own form) feeds Pagefind's UI from the same origin, and ONE result-count line
   (#result-count) is written into the DOM. The UI's own input, its clear button and its own count line are hidden by site-extra.css (not removed: the results sit in the same form).
   No inline script, no third party; the index is /learn/pagefind/, built by `pagefind --site site/learn`. */
(function () {
  var params = new URLSearchParams(window.location.search);
  var input = document.getElementById("search-q");
  var form = input && input.form;
  var counter = document.getElementById("result-count");
  var host = document.getElementById("search");
  var ui = null;
  var pagefind = null;
  var latest = 0;

  if (window.PagefindUI && host) {
    ui = new window.PagefindUI({ element: "#search", showSubResults: true, showImages: false, resetStyles: false, baseUrl: "/" });
  }

  function count(q) {
    if (!counter) { return; }
    var ticket = ++latest;
    if (!q) { counter.removeAttribute("data-count"); counter.textContent = ""; return; }
    counter.textContent = "Searching...";
    (pagefind || (pagefind = import("/learn/pagefind/pagefind.js").then(function (pf) {
      return pf.options({ baseUrl: "/" }).then(function () { return pf; });
    }))).then(function (pf) { return pf.search(q); }).then(function (res) {
      if (ticket !== latest) { return; }
      counter.setAttribute("data-count", String(res.results.length));
      counter.textContent = res.results.length + " result" + (res.results.length === 1 ? "" : "s") + " for \"" + q + "\"";
    }).catch(function (e) {
      if (ticket !== latest) { return; }
      counter.setAttribute("data-count", "error");
      counter.textContent = "Search is unavailable: " + e;
    });
  }

  function run(q) {
    if (ui) { ui.triggerSearch(q); }
    count(q);
  }

  var q = (params.get("q") || "").trim();
  if (input) { input.value = q; }
  if (q) { run(q); }

  if (form && input) {
    var timer = 0;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var value = input.value.trim();
      try { window.history.replaceState(null, "", value ? "?q=" + encodeURIComponent(value) : window.location.pathname); } catch (err) { /* the address is a convenience */ }
      run(value);
    });
    input.addEventListener("input", function () {
      window.clearTimeout(timer);
      timer = window.setTimeout(function () { run(input.value.trim()); }, 250);
    });
  }
})();
