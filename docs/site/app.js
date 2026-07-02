'use strict';

// Category display order (mirrors build_site.py CATEGORY_ORDER).
const CATEGORY_ORDER = [
  'vegetables','paneer','soya','daal','curries','rice','roti','dosas','bread',
  'regional','east','snacks','pakora','chutney','raita','salad','soup',
  'refreshment','sweets','cakes','mushroom','microwave','chicken','redmeat',
  'seafood','egg','nonvegsweets','assorted',
];

let RECIPES = [];
let activeCat = null;      // category slug, or null = all
let vegOnly = false;

const els = {
  q: document.getElementById('q'),
  chips: document.getElementById('chips'),
  vegOnly: document.getElementById('vegOnly'),
  count: document.getElementById('count'),
  results: document.getElementById('results'),
  recipe: document.getElementById('recipe'),
};

fetch('recipes.json')
  .then(r => r.json())
  .then(data => { RECIPES = data; buildChips(); route(); })
  .catch(() => { els.count.textContent = 'Could not load recipes.'; });

function buildChips() {
  const present = new Set(RECIPES.map(r => r.category));
  const nameFor = {};
  RECIPES.forEach(r => { nameFor[r.category] = r.categoryName; });
  els.chips.innerHTML = '';
  els.chips.appendChild(chip('All', null));
  CATEGORY_ORDER.filter(slug => present.has(slug))
    .forEach(slug => els.chips.appendChild(chip(nameFor[slug], slug)));
}

function chip(label, slug) {
  const b = document.createElement('button');
  b.className = 'chip' + (slug === activeCat ? ' active' : '');
  b.textContent = label;
  b.onclick = () => { activeCat = slug; buildChips(); render(); };
  return b;
}

function norm(s) { return (s || '').toLowerCase(); }

function matches(r, terms) {
  if (!terms.length) return true;
  const hay = norm(r.title) + ' ' + norm(r.contributor) + ' ' + norm(r.ingredients.join(' '));
  return terms.every(t => hay.includes(t));
}

function render() {
  els.recipe.hidden = true;
  els.results.hidden = false;
  const terms = els.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const list = RECIPES.filter(r =>
    (!activeCat || r.category === activeCat) &&
    (!vegOnly || r.isVeg) &&
    matches(r, terms));
  els.count.textContent = `${list.length.toLocaleString()} recipe${list.length === 1 ? '' : 's'}`;

  els.results.innerHTML = '';
  const frag = document.createDocumentFragment();
  list.slice(0, 400).forEach(r => {
    const li = document.createElement('li');
    li.innerHTML =
      `<div class="rtitle">${esc(r.title)}</div>` +
      `<div class="rmeta">${r.contributor ? 'by ' + esc(r.contributor) + ' · ' : ''}` +
      `${esc(r.categoryName)}${r.isVeg ? '' : ' · non-veg'}</div>`;
    li.onclick = () => { location.hash = '#/recipe/' + r.id; };
    frag.appendChild(li);
  });
  els.results.appendChild(frag);
  if (list.length > 400) {
    const li = document.createElement('li');
    li.className = 'note';
    li.textContent = `Showing the first 400 of ${list.length.toLocaleString()}. Refine your search to narrow it down.`;
    els.results.appendChild(li);
  }
}

function showRecipe(id) {
  const r = RECIPES.find(x => x.id === id);
  if (!r) { location.hash = ''; return; }
  els.results.hidden = true;
  els.recipe.hidden = false;
  const badge = r.isVeg
    ? '<span class="badge veg">veg</span>'
    : '<span class="badge nonveg">non-veg</span>';
  const by = r.contributor ? 'by ' + esc(r.contributor) + ' · ' : '';
  els.recipe.innerHTML =
    `<button class="back">&larr; Back</button>` +
    `<h2>${esc(r.title)}${badge}</h2>` +
    `<div class="by">${by}${esc(r.categoryName)}</div>` +
    (r.ingredients.length
      ? `<h3>Ingredients</h3><ul>${r.ingredients.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : '') +
    (r.method.length
      ? `<h3>Method</h3><ol>${r.method.map(m => `<li>${esc(m.replace(/^\d+[.)]\s*/, ''))}</li>`).join('')}</ol>` : '');
  els.recipe.querySelector('.back').onclick = () => history.back();
  window.scrollTo(0, 0);
}

function route() {
  const m = location.hash.match(/#\/recipe\/(\d+)/);
  if (m) showRecipe(parseInt(m[1], 10));
  else render();
}

function esc(s) {
  return (s || '').replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

els.q.addEventListener('input', () => {
  if (location.hash) location.hash = '';   // leaving a recipe view resets to list
  else render();
});
els.vegOnly.addEventListener('change', () => { vegOnly = els.vegOnly.checked; render(); });
window.addEventListener('hashchange', route);
