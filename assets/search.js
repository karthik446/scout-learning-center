/* The search page: Pagefind's UI from the same origin, plus a plain result count written into the DOM.
   No inline script, no third party; the index is /learn/pagefind/, built by `pagefind --site site/learn`. */
(function () {
  var params = new URLSearchParams(window.location.search);
  var q = (params.get("q") || "").trim();
  var input = document.getElementById("search-q");
  if (input) { input.value = q; }
  var counter = document.getElementById("result-count");

  if (window.PagefindUI) {
    var ui = new window.PagefindUI({ element: "#search", showSubResults: true, showImages: false, resetStyles: false });
    if (q) { ui.triggerSearch(q); }
  }

  if (q && counter) {
    counter.textContent = "Searching...";
    import("/learn/pagefind/pagefind.js").then(function (pf) {
      return pf.search(q);
    }).then(function (res) {
      counter.setAttribute("data-count", String(res.results.length));
      counter.textContent = res.results.length + " result" + (res.results.length === 1 ? "" : "s") + " for \"" + q + "\"";
    }).catch(function (e) {
      counter.setAttribute("data-count", "error");
      counter.textContent = "Search is unavailable: " + e;
    });
  }
})();
