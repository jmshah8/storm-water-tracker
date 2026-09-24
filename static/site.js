// Table sorting and filtering, the "last 30 days / this year" toggle, "See more" on long lists,
// and the overflow map. No fetching: every number is already in the HTML.
//
// Without JavaScript every row, every list item and every map dot stays visible, and the table is
// still readable in document order. JS only adds sorting, filtering and the map popup.
(function () {
  var SHOWN = 10;

  function text(el) { return (el.textContent || "").trim(); }

  // ---------------------------------------------------------------- "See more" on plain lists
  // A ul or ol marked data-more shows its first 10 items, then a "See more" button. Tables handle
  // their own limit inside initTable, because there it has to cooperate with filtering.
  document.querySelectorAll("ul[data-more], ol[data-more]").forEach(function (list) {
    var items = Array.prototype.slice.call(list.children);
    if (items.length <= SHOWN) return;
    var button = document.createElement("button");
    button.type = "button";
    button.className = "more";
    var expanded = false;
    function render() {
      items.slice(SHOWN).forEach(function (item) { item.hidden = !expanded; });
      button.textContent = expanded ? "See less" : "See more (" + (items.length - SHOWN) + " more)";
      button.setAttribute("aria-expanded", String(expanded));
    }
    render();
    button.addEventListener("click", function () {
      expanded = !expanded;
      render();
      if (!expanded) button.scrollIntoView({block: "nearest"});
    });
    list.insertAdjacentElement("afterend", button);
  });

  // ---------------------------------------------------------------- tables
  function cellOf(row, index) { return row.children[index]; }

  function rawValue(row, index) {
    var cell = cellOf(row, index);
    if (!cell) return "";
    var v = cell.getAttribute("data-sort-value");
    if (v === null) v = cell.getAttribute("data-value");
    if (v === null) v = text(cell);
    return v;
  }

  // The value a filter checkbox matches on: the label a reader sees, not the sort key.
  function filterValue(row, index) {
    var cell = cellOf(row, index);
    if (!cell) return "";
    var v = cell.getAttribute("data-filter-value");
    return v === null ? text(cell) : v;
  }

  function comparable(v) {
    var n = parseFloat(v);
    return isNaN(n) || !/^-?[\d.]+$/.test(v) ? String(v).toLowerCase() : n;
  }

  function initTable(table) {
    var body = table.tBodies[0];
    if (!body) return;
    var headers = Array.prototype.slice.call(table.querySelectorAll("thead th"));
    var rows = Array.prototype.slice.call(body.rows);
    var filters = {};                       // column index -> Set of accepted display values
    var limited = body.hasAttribute("data-more") && rows.length > SHOWN;
    var expanded = false;
    var moreButton = null;
    var status = null;

    function matches(row) {
      // An owning page (the map) can add a predicate of its own. It goes through here rather than
      // setting row.hidden directly, so page filtering and the "See more" limit agree on one answer.
      if (table.swtExternal && !table.swtExternal(row)) return false;
      for (var i in filters) {
        if (!filters[i].has(filterValue(row, Number(i)))) return false;
      }
      return true;
    }

    function apply() {
      var shown = 0, matching = 0;
      rows.forEach(function (row) {
        var ok = matches(row);
        if (ok) matching++;
        var visible = ok && (!limited || expanded || matching <= SHOWN);
        row.hidden = !visible;
        if (visible) shown++;
      });
      if (moreButton) {
        var hiddenByLimit = matching - shown;
        moreButton.hidden = hiddenByLimit <= 0 && !expanded;
        moreButton.textContent = expanded ? "See less" : "See more (" + hiddenByLimit + " more)";
        moreButton.setAttribute("aria-expanded", String(expanded));
      }
      if (status) {
        var filtered = Object.keys(filters).length > 0 || !!table.swtExternal;
        status.textContent = filtered ? "Showing " + matching + " of " + rows.length + " rows" : "";
        status.hidden = !filtered;
      }
      table.dispatchEvent(new CustomEvent("swt:filtered", {bubbles: true}));
    }

    function sortBy(index, ascending) {
      var sorted = rows.slice().sort(function (a, b) {
        var x = comparable(rawValue(a, index)), y = comparable(rawValue(b, index));
        if (typeof x !== typeof y) { x = String(x); y = String(y); }
        if (x < y) return ascending ? -1 : 1;
        if (x > y) return ascending ? 1 : -1;
        return 0;
      });
      headers.forEach(function (h) { h.removeAttribute("aria-sort"); });
      if (headers[index]) headers[index].setAttribute("aria-sort", ascending ? "ascending" : "descending");
      sorted.forEach(function (r) { body.appendChild(r); });
      rows = sorted;
      apply();
    }

    // One menu per column: how to sort it, and — where the column has a small set of repeated
    // values — which of those values to show.
    headers.forEach(function (th, index) {
      var kind = th.getAttribute("data-col");
      if (!kind) return;
      var label = text(th) || "column";
      th.classList.add("th-menu");
      th.textContent = "";

      var trigger = document.createElement("button");
      trigger.type = "button";
      trigger.className = "th-trigger";
      trigger.setAttribute("aria-haspopup", "true");
      trigger.setAttribute("aria-expanded", "false");
      trigger.innerHTML = "<span>" + label + "</span>";
      th.appendChild(trigger);

      var menu = document.createElement("div");
      menu.className = "th-pop";
      menu.hidden = true;
      th.appendChild(menu);

      var asc = kind === "num" ? "Lowest first" : "A → Z";
      var desc = kind === "num" ? "Highest first" : "Z → A";
      [[asc, true], [desc, false]].forEach(function (pair) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "th-sort";
        b.textContent = pair[0];
        b.addEventListener("click", function () { sortBy(index, pair[1]); close(); });
        menu.appendChild(b);
      });

      // Distinct values, in the order they appear. Offered as checkboxes only when the column
      // really is categorical: a column of 60 different numbers is a sort, not a filter.
      var values = [];
      rows.forEach(function (row) {
        var v = filterValue(row, index);
        if (values.indexOf(v) === -1) values.push(v);
      });
      var categorical = th.hasAttribute("data-filter")
        || (kind === "text" && values.length > 1 && values.length <= 40);
      if (categorical && values.length > 1) {
        values.sort(function (a, b) {
          var x = comparable(a), y = comparable(b);
          if (typeof x !== typeof y) { x = String(x); y = String(y); }
          return x < y ? -1 : x > y ? 1 : 0;
        });
        var head = document.createElement("div");
        head.className = "th-pop-head";
        head.textContent = "Show";
        menu.appendChild(head);

        var list = document.createElement("div");
        list.className = "th-pop-list";
        var boxes = [];
        values.forEach(function (v) {
          var id = "f" + Math.random().toString(36).slice(2, 9);
          var wrap = document.createElement("label");
          wrap.setAttribute("for", id);
          var box = document.createElement("input");
          box.type = "checkbox";
          box.checked = true;
          box.id = id;
          box.value = v;
          box.addEventListener("change", function () {
            var on = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
            if (on.length === values.length) delete filters[index];
            else filters[index] = new Set(on);
            th.classList.toggle("is-filtered", on.length !== values.length);
            apply();
          });
          boxes.push(box);
          wrap.appendChild(box);
          wrap.appendChild(document.createTextNode(v === "" ? "(blank)" : v));
          list.appendChild(wrap);
        });
        menu.appendChild(list);

        var all = document.createElement("button");
        all.type = "button";
        all.className = "th-clear";
        all.textContent = "Select all";
        all.addEventListener("click", function () {
          boxes.forEach(function (b) { b.checked = true; });
          delete filters[index];
          th.classList.remove("is-filtered");
          apply();
        });
        menu.appendChild(all);
      }

      function close() {
        menu.hidden = true;
        trigger.setAttribute("aria-expanded", "false");
      }
      function open() {
        document.querySelectorAll(".th-pop").forEach(function (m) {
          if (m !== menu) { m.hidden = true; }
        });
        document.querySelectorAll(".th-trigger").forEach(function (t) {
          if (t !== trigger) t.setAttribute("aria-expanded", "false");
        });
        menu.hidden = false;
        trigger.setAttribute("aria-expanded", "true");
      }
      trigger.addEventListener("click", function (e) {
        e.stopPropagation();
        if (menu.hidden) open(); else close();
      });
      menu.addEventListener("click", function (e) { e.stopPropagation(); });
      th.addEventListener("keydown", function (e) { if (e.key === "Escape") { close(); trigger.focus(); } });
    });

    if (limited) {
      moreButton = document.createElement("button");
      moreButton.type = "button";
      moreButton.className = "more";
      moreButton.addEventListener("click", function () {
        expanded = !expanded;
        apply();
        if (!expanded) moreButton.scrollIntoView({block: "nearest"});
      });
      (table.closest(".table-scroll") || table).insertAdjacentElement("afterend", moreButton);
    }
    if (table.hasAttribute("data-col-any") || table.querySelector("thead th[data-col]")) {
      status = document.createElement("p");
      status.className = "table-status";
      status.hidden = true;
      (moreButton || table.closest(".table-scroll") || table).insertAdjacentElement("afterend", status);
    }
    table.swtApply = apply;
    apply();
  }

  document.addEventListener("click", function () {
    document.querySelectorAll(".th-pop").forEach(function (m) { m.hidden = true; });
    document.querySelectorAll(".th-trigger").forEach(function (t) { t.setAttribute("aria-expanded", "false"); });
  });

  document.querySelectorAll("table[data-sortable], table[data-filterable]").forEach(initTable);

  // ---------------------------------------------------------------- period toggle
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

  // ---------------------------------------------------------------- the overflow map
  // Every dot and every table row carries its own period counts and status codes, so filtering is
  // a read of the DOM rather than a fetch. Codes are single letters, defined in build_site.py:
  // d dry day spill, c contested by radar, n not a dry day, p rain check pending,
  // i insufficient rain data, g no gauge within 10 km.
  var mapRoot = document.querySelector("[data-map]");
  if (mapRoot) {
    var svg = mapRoot.querySelector("svg");
    var dots = Array.prototype.slice.call(svg.querySelectorAll(".dot"));
    var mapTable = document.querySelector("table[data-map-table]");
    var mapRows = mapTable ? Array.prototype.slice.call(mapTable.tBodies[0].rows) : [];
    var popup = mapRoot.querySelector("[data-map-popup]");
    var counter = document.querySelector("[data-map-count]");
    var periodButtons = Array.prototype.slice.call(document.querySelectorAll("[data-map-period] button"));
    var periodKeys = periodButtons.map(function (b) { return b.getAttribute("data-period"); });
    var period = 0;                  // index into periodKeys, matching the data-p0/data-p1 attributes
    var statuses = null;             // null = every status
    var companies = null;
    var openIndex = -1;

    // "4:dnc" -> how many events, and which statuses were among them.
    function cell(el) { return (el.getAttribute("data-p" + period) || "0:").split(":"); }
    function company(el) { return el.getAttribute("data-c") || ""; }

    function visible(el) {
      var parts = cell(el);
      if (parseInt(parts[0], 10) === 0) return false;
      if (companies && !companies.has(company(el))) return false;
      if (statuses) {
        var codes = parts[1], hit = false;
        statuses.forEach(function (s) { if (codes.indexOf(s) !== -1) hit = true; });
        if (!hit) return false;
      }
      return true;
    }

    function applyMap() {
      var shown = 0;
      dots.forEach(function (dot, i) {
        var on = visible(dot);
        dot.style.display = on ? "" : "none";
        if (on) {
          // Lit when this period holds a dry day spill the radar does not contest — but not when the
          // reader has switched that status off, or the map would still be lit by what they hid.
          var lit = cell(dot)[1].indexOf("d") !== -1 && (!statuses || statuses.has("d"));
          dot.setAttribute("class", lit ? "dot dot--flag" : "dot");
          shown++;
        }
      });
      if (mapTable && mapTable.swtApply) {
        mapTable.swtExternal = visible;   // rows carry the same data-p attributes as the dots
        mapTable.swtApply();
      }
      if (counter) {
        counter.textContent = shown + " overflow" + (shown === 1 ? "" : "s");
        counter.setAttribute("data-value", String(shown));
      }
      if (openIndex >= 0 && dots[openIndex] && dots[openIndex].style.display === "none") hidePopup();
    }

    function hidePopup() {
      if (!popup) return;
      popup.hidden = true;
      openIndex = -1;
      dots.forEach(function (d) { d.classList.remove("is-open"); });
    }

    function showPopup(index) {
      var dot = dots[index], row = mapRows[index];
      if (!popup || !dot || !row) return;
      // Everything shown here comes from the row, so the popup and the table cannot disagree.
      var cells = row.children;
      var base = 3 + period * 4;     // name, company, watercourse, then four cells per period
      function cellText(n) { return cells[n] ? text(cells[n]) : ""; }
      dots.forEach(function (d) { d.classList.remove("is-open"); });
      dot.classList.add("is-open");
      openIndex = index;
      popup.querySelector("[data-pop-name]").textContent = cellText(0);
      popup.querySelector("[data-pop-company]").textContent = cellText(1);
      popup.querySelector("[data-pop-water]").textContent = cellText(2);
      popup.querySelector("[data-pop-events]").textContent = cellText(base);
      popup.querySelector("[data-pop-dry]").textContent = cellText(base + 1);
      popup.querySelector("[data-pop-contested]").textContent = cellText(base + 2);
      popup.querySelector("[data-pop-last]").textContent = cellText(base + 3);
      var href = cells[1] && cells[1].querySelector("a");
      popup.querySelector("[data-pop-link]").setAttribute("href", href ? href.getAttribute("href") : "#");
      popup.hidden = false;
      // Keep the panel inside the map, whichever side of it the dot sits on.
      var box = mapRoot.getBoundingClientRect();
      var spot = dot.getBoundingClientRect();
      var left = spot.left - box.left + spot.width / 2;
      var top = spot.top - box.top + spot.height / 2;
      popup.style.left = Math.min(Math.max(left, 8), Math.max(box.width - popup.offsetWidth - 8, 8)) + "px";
      popup.style.top = Math.min(Math.max(top + 12, 8), Math.max(box.height - popup.offsetHeight - 8, 8)) + "px";
    }

    dots.forEach(function (dot, i) {
      dot.addEventListener("click", function (e) { e.stopPropagation(); clearRegion(); showPopup(i); });
    });
    // The map is a pointer view; the table under it is the keyboard and screen-reader equivalent,
    // so a row click opens the same panel rather than making 1,000+ dots part of the tab order.
    mapRows.forEach(function (row, i) {
      row.addEventListener("click", function () {
        showPopup(i);
        mapRoot.scrollIntoView({block: "nearest", behavior: "smooth"});
      });
    });
    // Clicking the map anywhere that is not a dot names the region under the pointer.
    var readout = mapRoot.querySelector("[data-region-readout]");
    var regions = Array.prototype.slice.call(svg.querySelectorAll(".region"));
    function nameRegion(path) {
      regions.forEach(function (r) { r.classList.toggle("is-on", r === path); });
      if (!readout) return;
      readout.querySelector("[data-region-label]").textContent = path.getAttribute("data-region");
      readout.hidden = false;
    }
    function clearRegion() {
      regions.forEach(function (r) { r.classList.remove("is-on"); });
      if (readout) readout.hidden = true;
    }
    regions.forEach(function (path) {
      path.addEventListener("click", function (e) { e.stopPropagation(); hidePopup(); nameRegion(path); });
      path.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); hidePopup(); nameRegion(path); }
      });
    });

    mapRoot.addEventListener("click", function () { hidePopup(); clearRegion(); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") { hidePopup(); clearRegion(); } });
    if (popup) popup.addEventListener("click", function (e) { e.stopPropagation(); });
    var closeButton = popup && popup.querySelector("[data-pop-close]");
    if (closeButton) closeButton.addEventListener("click", hidePopup);

    periodButtons.forEach(function (b, i) {
      b.addEventListener("click", function () {
        period = i;
        periodButtons.forEach(function (o, j) { o.setAttribute("aria-pressed", String(i === j)); });
        document.querySelectorAll("[data-period-col]").forEach(function (c) {
          c.hidden = c.getAttribute("data-period-col") !== periodKeys[i];
        });
        hidePopup();
        applyMap();
      });
    });

    function readSet(name) {
      var boxes = Array.prototype.slice.call(document.querySelectorAll("[data-map-filter='" + name + "'] input"));
      var on = boxes.filter(function (b) { return b.checked; }).map(function (b) { return b.value; });
      return on.length === boxes.length ? null : new Set(on);
    }
    document.querySelectorAll("[data-map-filter] input").forEach(function (box) {
      box.addEventListener("change", function () {
        statuses = readSet("status");
        companies = readSet("company");
        hidePopup();
        applyMap();
      });
    });
    document.querySelectorAll("[data-map-reset]").forEach(function (b) {
      b.addEventListener("click", function () {
        document.querySelectorAll("[data-map-filter] input").forEach(function (i) { i.checked = true; });
        statuses = companies = null;
        hidePopup();
        applyMap();
      });
    });
    applyMap();
  }
})();
