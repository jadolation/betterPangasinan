// Better Pangasinan: progressive navigation and source-driven LGU discovery.

document.addEventListener("DOMContentLoaded", function () {
  document.documentElement.classList.add("js");
  var toggle = document.querySelector(".nav-toggle");
  var links = document.querySelector(".nav-links");

  if (toggle && links) {
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && links.classList.contains("open")) {
        links.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.focus();
      }
    });
    toggle.addEventListener("click", function () {
      var isOpen = links.classList.toggle("open");
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });

    links.querySelectorAll("a").forEach(function (a) {
      a.addEventListener("click", function () {
        links.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      });
    });
  }

  // Mark the current page in the nav
  var here = location.pathname.split("/").pop() || "index.html";
  document.querySelectorAll(".nav-links a").forEach(function (a) {
    var target = a.getAttribute("href");
    if (target === here || (here === "" && target === "index.html")) {
      a.setAttribute("aria-current", "page");
    } else if ((here === "lgu.html" && target === "lgus.html") || (["finances.html", "procurement.html", "project.html", "map.html", "legislation.html", "services.html", "statistics.html"].includes(here) && target === "projects.html")) {
      a.setAttribute("aria-current", "location");
    }
  });

  var form = document.querySelector("#lgu-search");
  var profile = document.querySelector("#profile-content");
  if (!form && !profile) return;

  function element(tag, text, className) {
    var node = document.createElement(tag);
    if (text) node.textContent = text;
    if (className) node.className = className;
    return node;
  }

  var dictionary = {};
  function translate(key, fallback) { return dictionary[key] || fallback; }
  Promise.all([
    fetch("data/public.json").then(function (response) {
      if (!response.ok) throw new Error("LGU data unavailable");
      return response.json();
    }),
    fetch("locales/en.json").then(function (response) { return response.ok ? response.json() : {}; }).catch(function () { return {}; })
  ]).then(function (loaded) {
    var data = loaded[0];
    dictionary = loaded[1];
    var records = data.lgus;
    if (!Array.isArray(records)) throw new Error("Invalid directory");
    var testMode = document.querySelector('meta[name="data-mode"][content="test"]') !== null;
    records = records.filter(function (record) { return testMode || (record.is_mock === false && record.publication_status !== "demo_only"); });
    var params = new URLSearchParams(location.search);
    if (form) {
      var query = document.querySelector("#lgu-query");
      var type = document.querySelector("#lgu-type");
      query.value = params.get("q") || "";
      type.value = params.get("type") || "";
      function render() {
        var filtered = records.filter(function (record) {
          return String(record.name).toLowerCase().includes(query.value.trim().toLowerCase()) && (!type.value || record.classification === type.value);
        });
        var results = document.querySelector("#lgu-results");
        results.replaceChildren();
        filtered.forEach(function (record) {
          var card = element("article", "", "card");
          card.append(element("span", record.classification || "Classification unavailable", "badge"), element("h2", record.name));
          var link = element("a", "View profile →", "card-link");
          link.href = "lgu.html?id=" + encodeURIComponent(record.id);
          card.append(link);
          results.append(card);
        });
        document.querySelector("#lgu-result-count").textContent = filtered.length + " " + translate("directory.found", "published profiles found");
        document.querySelector("#lgu-empty").hidden = filtered.length > 0;
        if (records.length && !filtered.length) document.querySelector("#lgu-empty h2").textContent = translate("directory.no_results", "No matching profiles");
      }
      form.addEventListener("submit", function (event) {
        event.preventDefault();
        var next = new URLSearchParams();
        if (query.value.trim()) next.set("q", query.value.trim());
        if (type.value) next.set("type", type.value);
        history.replaceState(null, "", "lgus.html" + (next.size ? "?" + next : ""));
        render();
      });
      query.addEventListener("input", render);
      type.addEventListener("change", render);
      render();
    } else {
      var record = records.find(function (item) { return item.id === params.get("id"); });
      if (!record) return;
      document.querySelector("#profile-status").hidden = true;
      profile.hidden = false;
      document.querySelector("#profile-name").textContent = record.name;
      document.title = record.name + " | Better Pangasinan";
      var details = element("dl");
      [["Classification", record.classification], ["PSGC", record.psgc], ["Population", record.population == null ? null : record.population], ["Reporting period", record.reporting_period], ["Verification", record.verification_status]].forEach(function (entry) {
        details.append(element("dt", entry[0]), element("dd", entry[1] == null ? translate("data.not_collected", "Not yet collected") : String(entry[1])));
      });
      profile.append(details);
      var grid = element("div", "", "grid grid-2");
      [["Financial records", "finances.html", "finances"], ["Public projects", "projects.html", "projects"], ["Legislation & documents", "legislation.html", "legislation"], ["Statistics", "statistics.html", "statistics"], ["Government services", "services.html", "services"], ["Offices & officials", null, "entities"]].forEach(function (entry) {
        var card = element("section", "", "card");
        card.append(element("h2", entry[0]));
        var related = (data[entry[2]] || []).filter(function (item) { return item.lgu_id === record.id && (testMode || (item.is_mock === false && item.publication_status === "approved")); });
        if (!related.length) card.append(element("p", "Reviewed information is not yet available for this profile."));
        else {
          var list = element("ul");
          related.forEach(function (item) { list.append(element("li", item.name || item.title || item.id)); });
          card.append(list);
        }
        if (entry[1]) {
          var link = element("a", "Explore records →", "card-link");
          link.href = entry[1] + "?lgu=" + encodeURIComponent(record.id);
          card.append(link);
        }
        grid.append(card);
      });
      profile.append(grid, element("h2", "Source references"));
      (record.source_ids || []).forEach(function (id) {
        var source = (data.sources || []).find(function (item) { return item.id === id; });
        var paragraph = element("p", source ? source.name || source.title || id : id);
        if (source && source.url && /^https:\/\//i.test(source.url)) {
          var link = element("a", "Open source", "card-link");
          link.href = source.url;
          link.rel = "noopener noreferrer";
          paragraph.append(link);
        }
        profile.append(paragraph);
      });
      if (!(record.source_ids || []).length) profile.append(element("p", "Sources not yet published"));
    }
  }).catch(function () {
    var status = document.querySelector("#lgu-result-count");
    if (status) status.textContent = translate("directory.failure", "The directory could not be loaded. Use the official source below or try again later.");
  });
});
