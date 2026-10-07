// Recipes DB: a small Obsidian-Bases-style browser for the recipe database.
(function () {
  "use strict";

  const cfg = window.RECIPES_CONFIG || {};
  const useSupabase = Boolean(cfg.supabaseUrl && cfg.supabaseAnonKey);

  // Views mirror vault/Recipes DB.base
  const VIEWS = [
    { id: "table", name: "Table", type: "table", filter: () => true },
    { id: "cards", name: "Cards", type: "cards", filter: () => true },
    { id: "desserts", name: "Desserts", type: "cards", filter: (r) => r.categories.includes("dessert") },
    { id: "not-desserts", name: "Not Desserts", type: "cards", filter: (r) => !r.categories.includes("dessert") },
  ];

  const state = { recipes: [], view: "table", query: "", sort: { key: "title", dir: 1 } };
  const app = document.getElementById("app");
  const search = document.getElementById("search");

  // ---------------------------------------------------------------- data
  async function loadRecipes() {
    if (!useSupabase) {
      const res = await fetch("data/recipes.json");
      if (!res.ok) throw new Error("Could not load data/recipes.json");
      return res.json();
    }
    const select = [
      "*",
      "owner:app_user!recipe_owner_id_fkey(username,display_name)",
      "recipe_category(category(name))",
      "recipe_cuisine(cuisine(name))",
      "recipe_tag(tag(name))",
      "recipe_ingredient(section,position,raw_text,ingredient(name))",
      "recipe_step(section,position,body)",
      "recipe_equipment(position,name)",
      "recipe_note(title,body,created_at,author:app_user(username,display_name))",
      "recipe_image(kind,url)",
      "cook_log(rating)",
    ].join(",");
    const url = `${cfg.supabaseUrl}/rest/v1/recipe?select=${encodeURIComponent(select)}&visibility=eq.public`;
    const res = await fetch(url, {
      headers: { apikey: cfg.supabaseAnonKey, Authorization: `Bearer ${cfg.supabaseAnonKey}` },
    });
    if (!res.ok) throw new Error(`Supabase request failed: ${res.status} ${await res.text()}`);
    return (await res.json()).map(fromSupabase);
  }

  function fromSupabase(r) {
    const byPos = (a, b) => a.position - b.position;
    const ratings = (r.cook_log || []).map((c) => c.rating).filter((x) => x != null);
    return {
      id: r.recipe_id,
      owner: r.owner && r.owner.username,
      owner_name: r.owner && r.owner.display_name,
      title: r.title,
      slug: r.slug,
      visibility: r.visibility,
      description: r.description,
      forked_from: r.forked_from_recipe_id,
      prep_minutes: r.prep_minutes,
      cook_minutes: r.cook_minutes,
      total_minutes: r.total_minutes,
      yield_text: r.yield_text,
      servings: r.servings,
      kcal_per_serving: r.kcal_per_serving,
      nutrition_text: r.nutrition_text,
      source_name: r.source_name,
      source_url: r.source_url,
      cover_image_url: r.cover_image_url,
      images: (r.recipe_image || []).map((i) => i.url),
      categories: (r.recipe_category || []).map((x) => x.category.name),
      cuisines: (r.recipe_cuisine || []).map((x) => x.cuisine.name),
      tags: (r.recipe_tag || []).map((x) => x.tag.name),
      ingredients: (r.recipe_ingredient || []).sort(byPos).map((i) => ({
        section: i.section, text: i.raw_text, ingredient: i.ingredient && i.ingredient.name,
      })),
      steps: (r.recipe_step || []).sort(byPos),
      equipment: (r.recipe_equipment || []).sort(byPos).map((e) => e.name),
      notes: (r.recipe_note || []).map((n) => ({
        title: n.title, body: n.body,
        author: n.author && n.author.username, author_name: n.author && n.author.display_name,
      })),
      avg_rating: ratings.length ? Math.round((ratings.reduce((a, b) => a + b, 0) / ratings.length) * 10) / 10 : null,
      rating_count: ratings.length,
    };
  }

  // ---------------------------------------------------------------- helpers
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  function minutes(m) {
    if (m == null) return "";
    if (m < 60) return `${m} min`;
    const h = Math.floor(m / 60), r = m % 60;
    return r ? `${h} hr ${r} min` : `${h} hr`;
  }

  const tagPills = (tags) => tags.map((t) => `<span class="tag">#${esc(t.replace(/\s+/g, "-"))}</span>`).join("");
  const listPills = (items) => items.map((t) => `<span class="pill">${esc(t)}</span>`).join("");
  const stars = (r) => (r.avg_rating ? `<span class="stars" title="${r.rating_count} ratings">★ ${r.avg_rating}</span>` : "");

  function matches(r, q) {
    if (!q) return true;
    const hay = [r.title, r.owner_name, r.description, ...r.tags, ...r.categories, ...r.cuisines,
      ...r.ingredients.map((i) => i.ingredient || i.text)].join(" ").toLowerCase();
    return q.toLowerCase().split(/\s+/).every((w) => hay.includes(w));
  }

  function visibleRecipes(view) {
    const { key, dir } = state.sort;
    return state.recipes
      .filter(view.filter)
      .filter((r) => matches(r, state.query))
      .sort((a, b) => {
        const av = sortValue(a, key), bv = sortValue(b, key);
        if (av == null && bv == null) return 0;
        if (av == null) return 1;
        if (bv == null) return -1;
        return (av > bv ? 1 : av < bv ? -1 : 0) * dir;
      });
  }

  function sortValue(r, key) {
    if (key === "tags") return r.tags[0];
    if (key === "category") return r.categories[0];
    if (key === "title" || key === "owner_name") return (r[key] || "").toLowerCase();
    return r[key];
  }

  // ---------------------------------------------------------------- views
  function renderViews(activeId) {
    document.getElementById("views").innerHTML = VIEWS.map((v) =>
      `<a href="#/view/${v.id}" class="view-tab${v.id === activeId ? " active" : ""}">${esc(v.name)}</a>`).join("");
  }

  const COLUMNS = [
    { key: "title", label: "name" },
    { key: "tags", label: "tags" },
    { key: "category", label: "category" },
    { key: "cook_minutes", label: "cook time" },
    { key: "total_minutes", label: "total time" },
    { key: "owner_name", label: "owner" },
    { key: "avg_rating", label: "rating" },
  ];

  function renderTable(rows) {
    const head = COLUMNS.map((c) => {
      const arrow = state.sort.key === c.key ? (state.sort.dir > 0 ? " ↑" : " ↓") : "";
      return `<th><button class="th-btn" data-sort="${c.key}">${esc(c.label)}${arrow}</button></th>`;
    }).join("");
    const body = rows.map((r) => `
      <tr>
        <td><a class="internal-link" href="#/recipe/${r.id}">${esc(r.title)}</a></td>
        <td>${tagPills(r.tags)}</td>
        <td>${listPills(r.categories)}</td>
        <td class="num">${esc(minutes(r.cook_minutes))}</td>
        <td class="num">${esc(minutes(r.total_minutes))}</td>
        <td>${esc(r.owner_name)}</td>
        <td>${stars(r)}</td>
      </tr>`).join("");
    return `<div class="table-wrap"><table class="bases-table"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function cover(r) {
    if (r.cover_image_url) return `<img src="${esc(r.cover_image_url)}" alt="" loading="lazy">`;
    return `<div class="cover-blank">${esc(r.title.charAt(0))}</div>`;
  }

  function renderCards(rows) {
    return `<div class="cards">${rows.map((r) => `
      <a class="card" href="#/recipe/${r.id}">
        <div class="card-cover">${cover(r)}</div>
        <div class="card-body">
          <div class="card-title">${esc(r.title)}</div>
          <div class="card-prop">${tagPills(r.tags) || '<span class="muted">No tags</span>'}</div>
          <div class="card-prop">${listPills(r.categories)}</div>
        </div>
      </a>`).join("")}</div>`;
  }

  function renderList(viewId) {
    const view = VIEWS.find((v) => v.id === viewId) || VIEWS[0];
    state.view = view.id;
    renderViews(view.id);
    const rows = visibleRecipes(view);
    const count = `<div class="results-count muted">${rows.length} result${rows.length === 1 ? "" : "s"}</div>`;
    app.innerHTML = count + (rows.length ? (view.type === "table" ? renderTable(rows) : renderCards(rows))
      : '<p class="muted">No recipes match.</p>');
    app.querySelectorAll("[data-sort]").forEach((btn) => btn.addEventListener("click", () => {
      const key = btn.dataset.sort;
      state.sort = { key, dir: state.sort.key === key ? -state.sort.dir : 1 };
      renderList(state.view);
    }));
  }

  function groupBySection(items) {
    const groups = [];
    for (const item of items) {
      const last = groups[groups.length - 1];
      if (last && last.section === item.section) last.items.push(item);
      else groups.push({ section: item.section, items: [item] });
    }
    return groups;
  }

  function renderRecipe(id) {
    renderViews(null);
    const r = state.recipes.find((x) => String(x.id) === id);
    if (!r) {
      app.innerHTML = '<p>Recipe not found. It may be private.</p><p><a href="#/">Back to all recipes</a></p>';
      return;
    }
    const fork = r.forked_from && state.recipes.find((x) => x.id === r.forked_from);
    const props = [
      ["owner", esc(r.owner_name)],
      ["category", listPills(r.categories)],
      ["cuisine", listPills(r.cuisines)],
      ["tags", tagPills(r.tags)],
      ["prep time", esc(minutes(r.prep_minutes))],
      ["cook time", esc(minutes(r.cook_minutes))],
      ["total time", esc(minutes(r.total_minutes))],
      ["makes", esc(r.yield_text)],
      ["kcal/serving", esc(r.kcal_per_serving)],
      ["rating", r.avg_rating ? `${stars(r)} <span class="muted">(${r.rating_count})</span>` : ""],
      ["source", r.source_url ? `<a href="${esc(r.source_url)}" target="_blank" rel="noopener">${esc(r.source_name || r.source_url)}</a>` : esc(r.source_name)],
      ["forked from", fork ? `<a class="internal-link" href="#/recipe/${fork.id}">${esc(fork.title)}</a>` : ""],
    ].filter(([, v]) => v);

    const ingredients = groupBySection(r.ingredients).map((g) => `
      ${g.section ? `<h4>${esc(g.section)}</h4>` : ""}
      <ul>${g.items.map((i) => `<li>${esc(i.text)}</li>`).join("")}</ul>`).join("");
    const steps = groupBySection(r.steps).map((g) => `
      ${g.section ? `<h4>${esc(g.section)}</h4>` : ""}
      <ol>${g.items.map((s) => `<li>${esc(s.body)}</li>`).join("")}</ol>`).join("");
    const notes = r.notes.map((n) => `
      <li>${n.title ? `<strong>${esc(n.title)}</strong><br>` : ""}${esc(n.body).replace(/\n/g, "<br>")}
      ${n.author !== r.owner ? `<span class="muted"> · ${esc(n.author_name)}</span>` : ""}</li>`).join("");

    app.innerHTML = `
      <article class="note">
        <p><a href="#/view/${state.view}" class="muted">← Recipes DB</a></p>
        <h1>${esc(r.title)}</h1>
        ${r.cover_image_url ? `<img class="hero" src="${esc(r.cover_image_url)}" alt="">` : ""}
        <div class="properties">${props.map(([k, v]) => `
          <div class="prop-row"><div class="prop-key">${esc(k)}</div><div class="prop-val">${v}</div></div>`).join("")}
        </div>
        ${r.description ? `<p>${esc(r.description)}</p>` : ""}
        ${r.equipment.length ? `<hr><h2>Equipment</h2><ul>${r.equipment.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
        <hr><h2>Ingredients</h2>${ingredients || '<p class="muted">None written down yet.</p>'}
        <hr><h2>Directions</h2>${steps || '<p class="muted">None written down yet.</p>'}
        ${notes ? `<hr><h2>Notes</h2><ul>${notes}</ul>` : ""}
        ${r.nutrition_text ? `<hr><h2>Nutrition</h2><p>${esc(r.nutrition_text)}</p>` : ""}
        ${r.images.length ? `<hr><h2>Pictures</h2>${r.images.map((u) => `<img class="hero" src="${esc(u)}" alt="" loading="lazy">`).join("")}` : ""}
      </article>`;
    window.scrollTo(0, 0);
  }

  // ---------------------------------------------------------------- routing
  function route() {
    const hash = location.hash.replace(/^#\/?/, "");
    const [kind, id] = hash.split("/");
    if (kind === "recipe" && id) renderRecipe(id);
    else renderList(kind === "view" ? id : state.view);
  }

  search.addEventListener("input", () => {
    state.query = search.value.trim();
    if (location.hash.startsWith("#/recipe/")) location.hash = `#/view/${state.view}`;
    else renderList(state.view);
  });
  window.addEventListener("hashchange", route);

  document.getElementById("footer").textContent = useSupabase
    ? "Live data from Supabase · public recipes"
    : "Static demo data (data/recipes.json) · public recipes";

  loadRecipes()
    .then((recipes) => { state.recipes = recipes; route(); })
    .catch((err) => { app.innerHTML = `<p class="error">${esc(err.message)}</p>`; });
})();
