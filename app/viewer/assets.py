"""Static assets of the viewer site: stylesheet and sort script.

Design tokens and component rules are taken 1:1 from the macro dashboard
(D:\\programme\\macro-dashboard\\index.html) so both tools read as one
toolbox. Two deliberate differences:

* No `@import` of the Google fonts. The dossier site is opened from disk as
  often as from the web; a remote font that fails to load must not change
  the layout, so the stacks fall back to local system fonts.
* No dark mode and no theme toggle — one rendering, so a screenshot always
  means the same thing.

Kept as module constants rather than package data files: the site
generator writes them out next to the pages, and a constant cannot go
missing from a wheel or a container image.
"""
from __future__ import annotations

import logging
from typing import Final

logger = logging.getLogger(__name__)

CSS_FILENAME: Final[str] = "site.css"
JS_FILENAME: Final[str] = "sort.js"

SITE_CSS: Final[str] = """\
:root{
  --paper:#f4f3ef; --card:#ffffff; --ink:#16233a; --ink-soft:#5b6675;
  --line:#e3e1da; --navy:#16233a; --accent:#8a2f2b;
  --green:#1e7d4f; --yellow:#c08c0e; --red:#b3362b; --grey:#9aa1ab;
  --mono:'IBM Plex Mono',monospace; --sans:'IBM Plex Sans',sans-serif;
  --serif:'Spectral',serif;
}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--paper);color:var(--ink);font-family:var(--sans);font-size:14px;line-height:1.5}
a{color:var(--accent)}
/* ---------- Header ---------- */
header{background:var(--navy);color:#f2f0ea;padding:0 28px}
.hd-back{display:inline-block;padding:14px 0 0;color:#9fb0c6;font-size:12.5px;text-decoration:none}
.hd-back:hover{color:#fff}
.hd-top{display:flex;align-items:baseline;gap:16px;padding:10px 0 18px;flex-wrap:wrap}
.hd-top h1{font-family:var(--serif);font-weight:600;font-size:26px;letter-spacing:.2px}
.hd-top h1 span{color:#c9a86a}
.hd-meta{margin-left:auto;font-family:var(--mono);font-size:12px;color:#9fb0c6}
/* ---------- Layout ---------- */
main{max-width:1240px;margin:0 auto;padding:26px 28px 60px}
h2{font-family:var(--serif);font-weight:600;font-size:20px;margin:26px 0 12px}
h2:first-child{margin-top:0}
.sub{color:var(--ink-soft);font-size:13px;margin-bottom:16px;max-width:860px}
.card{background:var(--card);border:1px solid var(--line);border-radius:6px;padding:18px 20px;box-shadow:0 1px 2px rgba(22,35,58,.05)}
.banner{background:#fdf6e3;border:1px solid #e8d9a0;color:#7a5c00;padding:10px 14px;border-radius:4px;margin-bottom:18px;font-size:13px}
.banner.err{background:#fbeeec;border-color:#e4b6b0;color:#7c2822}
/* ---------- KPI-Karten ---------- */
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:12px}
.kpi{background:var(--card);border:1px solid var(--line);border-left-width:4px;border-radius:4px;padding:12px 14px}
.kpi.green{border-left-color:var(--green)}
.kpi.yellow{border-left-color:var(--yellow)}
.kpi.red{border-left-color:var(--red)}
.kpi.na{border-left-color:var(--grey)}
.kpi .k-name{font-size:12px;color:var(--ink-soft);min-height:32px}
.kpi .k-val{font-family:var(--mono);font-size:21px;font-weight:500;margin:2px 0}
/* ---------- Ampel-Badges ---------- */
.pill{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.5px;padding:3px 9px;border-radius:20px;color:#fff}
.pill.green{background:var(--green)}
.pill.yellow{background:var(--yellow)}
.pill.red{background:var(--red)}
.pill.na{background:var(--grey)}
.tag{display:inline-block;font-size:10.5px;letter-spacing:.4px;padding:2px 7px;border:1px solid var(--line);border-radius:3px;color:var(--ink-soft);background:var(--paper);margin-left:6px;white-space:nowrap}
.defect{color:var(--yellow);cursor:help;font-size:12px}
/* ---------- Tabellen ---------- */
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);font-size:13px}
th,td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--line);vertical-align:top}
th{background:var(--navy);color:#f2f0ea;font-weight:500;font-size:12px}
th[data-sortable]{cursor:pointer;white-space:nowrap}
th[data-sortable]:hover{color:#c9a86a}
th[aria-sort]::after{content:' \\2195';color:#c9a86a}
td.mono{font-family:var(--mono);font-size:12px;white-space:nowrap}
td.num{font-family:var(--mono);font-size:12px;white-space:nowrap;text-align:right}
td.stars{font-family:var(--mono);font-size:12px;color:var(--ink-soft);white-space:nowrap}
tbody tr:hover{background:#faf9f6}
.t-name{font-weight:600}
.t-sub{color:var(--ink-soft);font-size:12px}
.age-yellow{color:var(--yellow);font-weight:600}
.age-red{color:var(--red);font-weight:600}
/* ---------- Fuß ---------- */
.foot{margin-top:22px;padding:14px 16px;background:#eceae3;border-radius:4px;color:var(--ink-soft);font-size:12.5px;max-width:900px}
@media(max-width:900px){main{padding:20px 16px 48px}.kpi-grid{grid-template-columns:1fr 1fr}}
@media(max-width:700px){header{padding:0 16px}.kpi-grid{grid-template-columns:1fr}table{font-size:12px}}
"""

SORT_JS: Final[str] = """\
/* Column sorting for the overview table.
   Sort value comes from each cell's data-sort attribute, never from the
   displayed text: the display string is the dossier's own formatting
   ("314.2x (FY)") and must stay untouched. An empty data-sort means "not
   comparable" and always sorts to the end, in both directions, so missing
   data never masquerades as a smallest or largest value. */
(function () {
  "use strict";

  function cellValue(row, index) {
    var cell = row.children[index];
    if (!cell) { return null; }
    var raw = cell.getAttribute("data-sort");
    if (raw === null || raw === "") { return null; }
    var num = parseFloat(raw);
    return isNaN(num) ? raw : num;
  }

  function compare(a, b) {
    if (a === null && b === null) { return 0; }
    if (a === null) { return 1; }
    if (b === null) { return -1; }
    if (typeof a === "number" && typeof b === "number") { return a - b; }
    return String(a).localeCompare(String(b));
  }

  function sortBy(table, index, ascending) {
    var body = table.tBodies[0];
    var rows = Array.prototype.slice.call(body.rows);
    rows.sort(function (rowA, rowB) {
      var valueA = cellValue(rowA, index);
      var valueB = cellValue(rowB, index);
      if (valueA === null || valueB === null) { return compare(valueA, valueB); }
      return ascending ? compare(valueA, valueB) : compare(valueB, valueA);
    });
    rows.forEach(function (row) { body.appendChild(row); });
  }

  function attach(table) {
    var headers = Array.prototype.slice.call(table.tHead.rows[0].cells);
    headers.forEach(function (header, index) {
      if (!header.hasAttribute("data-sortable")) { return; }
      header.addEventListener("click", function () {
        var ascending = header.getAttribute("aria-sort") !== "ascending";
        headers.forEach(function (other) { other.removeAttribute("aria-sort"); });
        header.setAttribute("aria-sort", ascending ? "ascending" : "descending");
        sortBy(table, index, ascending);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.slice
      .call(document.querySelectorAll("table[data-sortable-table]"))
      .forEach(attach);
  });
})();
"""
