// Table sorting, the "last 30 days / this year" toggle, and "See more" on long lists. No fetching.
(function () {
  var SHOWN = 10;

  // Any list marked data-more (a ul, ol or tbody) shows its first 10 items, then a "See more" button.
  // Without JavaScript every item stays visible.
  document.querySelectorAll("[data-more]").forEach(function (list) {
    var items = Array.prototype.slice.call(list.children);
    if (items.length <= SHOWN) return;
    items.slice(SHOWN).forEach(function (item) { item.hidden = true; });
    var button = document.createElement("button");
    button.type = "button";
    button.className = "more";
    button.textContent = "See more (" + (items.length - SHOWN) + " more)";
    button.addEventListener("click", function () {
      items.forEach(function (item) { item.hidden = false; });
      button.remove();
    });
    var anchor = list.tagName === "TBODY" ? (list.closest(".table-scroll") || list.closest("table")) : list;
    anchor.insertAdjacentElement("afterend", button);
  });

  function cellValue(row, index) {
    var cell = row.children[index];
    var v = cell.getAttribute("data-sort-value");
    if (v === null) v = cell.getAttribute("data-value");
    if (v === null) v = cell.textContent.trim();
    var n = parseFloat(v);
    return isNaN(n) || !/^-?[\d.]+$/.test(v) ? v.toLowerCase() : n;
  }

  document.querySelectorAll("table[data-sortable]").forEach(function (table) {
    var headers = table.querySelectorAll("th[data-sort]");
    headers.forEach(function (th) {
      var button = th.querySelector("button");
      button.addEventListener("click", function () {
        var index = Array.prototype.indexOf.call(th.parentNode.children, th);
        var ascending = th.getAttribute("aria-sort") !== "ascending";
        headers.forEach(function (h) { h.removeAttribute("aria-sort"); });
        th.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        var body = table.tBodies[0];
        var rows = Array.prototype.slice.call(body.rows);
        rows.sort(function (a, b) {
          var x = cellValue(a, index), y = cellValue(b, index);
          if (x < y) return ascending ? -1 : 1;
          if (x > y) return ascending ? 1 : -1;
          return 0;
        });
        rows.forEach(function (r) { body.appendChild(r); });
      });
    });
  });

  document.querySelectorAll("[data-toggle-group]").forEach(function (group) {
    var name = group.getAttribute("data-toggle-group");
    var buttons = group.querySelectorAll("button[data-period]");
    var panels = document.querySelectorAll("[data-period-panel][data-group='" + name + "']");
    function show(period) {
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", String(b.getAttribute("data-period") === period)); });
      panels.forEach(function (p) { p.hidden = p.getAttribute("data-period-panel") !== period; });
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { show(b.getAttribute("data-period")); }); });
    show("last30");
  });
})();
