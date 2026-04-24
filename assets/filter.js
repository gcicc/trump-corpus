window.trumpFilter = (function () {
  function apply(hide) {
    document.querySelectorAll(".post-card").forEach(function (el) {
      var t = el.dataset.theme;
      el.style.display = hide.has(t) ? "none" : "";
    });
  }
  function refresh() {
    var chips = document.querySelectorAll(".filter-bar .chip");
    var hidden = new Set();
    chips.forEach(function (c) { if (!c.classList.contains("on")) hidden.add(c.dataset.theme); });
    apply(hidden);
  }
  document.addEventListener("click", function (e) {
    var chip = e.target.closest(".filter-bar .chip");
    if (!chip) return;
    e.preventDefault();
    if (e.shiftKey) {
      chip.classList.toggle("on");
    } else {
      // solo: turn all off, this one on (or if already solo, restore all)
      var chips = document.querySelectorAll(".filter-bar .chip");
      var soloing = Array.from(chips).every(function (c) {
        return c === chip ? c.classList.contains("on") : !c.classList.contains("on");
      });
      chips.forEach(function (c) {
        if (soloing) c.classList.add("on");
        else c.classList.toggle("on", c === chip);
      });
    }
    refresh();
  });
  return {
    solo: function () { document.querySelectorAll(".filter-bar .chip").forEach(function (c) { c.classList.add("on"); }); refresh(); },
    none: function () { document.querySelectorAll(".filter-bar .chip").forEach(function (c) { c.classList.remove("on"); }); refresh(); }
  };
})();