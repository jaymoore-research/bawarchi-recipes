'use strict';

// Category display order (mirrors build_site.py CATEGORY_ORDER).
const CATEGORY_ORDER = [
  'vegetables', 'paneer', 'soya', 'daal', 'curries', 'rice', 'roti', 'dosas', 'bread',
  'regional', 'east', 'snacks', 'pakora', 'chutney', 'raita', 'salad', 'soup',
  'refreshment', 'sweets', 'cakes', 'mushroom', 'microwave', 'chicken', 'redmeat',
  'seafood', 'egg', 'nonvegsweets', 'assorted',
];

// Sub-group display order within Vegetables and within Regional (mirror build_site.py).
const VEG_SUB_ORDER = [
  'Aloo / Potato', 'Baingan / Eggplant', 'Bhindi / Okra', 'Gobi / Cauliflower',
  'Cabbage', 'Capsicum / Mirchi', 'Matar / Peas & Beans', 'Chole / Rajma / Chana',
  'Methi & Palak (Greens)', 'Karela / Bittergourd', 'Lauki / Gourds',
  'Carrot & Beetroot', 'Corn', 'Tomato', 'Yam, Plantain & Root', 'Koftas',
  'Other Vegetables',
];
const REGION_ORDER = [
  'Indo-Chinese', 'Italian & Continental', 'Mexican', 'Thai & East Asian', 'Bengali',
  'Gujarati', 'Maharashtrian', 'Punjabi & North', 'Rajasthani', 'Kashmiri', 'Sindhi',
  'South Indian', 'Other Regional',
];

// Table-of-contents grouping of the category chips, by similarity.
const META_GROUPS = [
  ['Everyday veg', ['vegetables', 'paneer', 'soya', 'mushroom', 'daal', 'curries']],
  ['Rice & bread', ['rice', 'roti', 'dosas', 'bread']],
  ['Snacks & sides', ['snacks', 'pakora', 'chutney', 'raita', 'salad', 'soup']],
  ['Regional & world', ['regional', 'east']],
  ['Sweet & drinks', ['sweets', 'cakes', 'refreshment']],
  ['Non-vegetarian', ['chicken', 'redmeat', 'seafood', 'egg', 'nonvegsweets']],
  ['Other', ['microwave', 'assorted']],
];

let RECIPES = [];
let NAME_FOR = {};          // slug -> display name (built from data)
let activeCat = null;       // category slug, or null = all
let vegOnly = false;

const els = {
  q: document.getElementById('q'),
  chips: document.getElementById('chips'),
  vegOnly: document.getElementById('vegOnly'),
  count: document.getElementById('count'),
  results: document.getElementById('results'),
  recipe: document.getElementById('recipe'),
  about: document.getElementById('about'),
};

fetch('recipes.json')
  .then(r => r.json())
  .then(data => {
    RECIPES = data;
    RECIPES.forEach(r => { NAME_FOR[r.category] = r.categoryName; });
    buildNav();
    route();
  })
  .catch(() => { els.count.textContent = 'Could not load recipes.'; });

// --- table-of-contents nav ------------------------------------------------

function buildNav() {
  const present = new Set(RECIPES.map(r => r.category));
  els.chips.innerHTML = '';

  const allRow = document.createElement('div');
  allRow.className = 'navgroup';
  allRow.appendChild(chip('All recipes', null));
  els.chips.appendChild(allRow);

  for (const [label, slugs] of META_GROUPS) {
    const here = slugs.filter(s => present.has(s));
    if (!here.length) continue;
    const row = document.createElement('div');
    row.className = 'navgroup';
    const lab = document.createElement('span');
    lab.className = 'navlabel';
    lab.textContent = label;
    row.appendChild(lab);
    const box = document.createElement('div');
    box.className = 'navchips';
    here.forEach(s => box.appendChild(chip(NAME_FOR[s], s)));
    row.appendChild(box);
    els.chips.appendChild(row);
  }
}

function chip(label, slug) {
  const b = document.createElement('button');
  b.className = 'chip' + (slug === activeCat ? ' active' : '');
  b.textContent = label;
  b.onclick = () => { activeCat = slug; buildNav(); render(); };
  return b;
}

// --- search + wall --------------------------------------------------------

function norm(s) { return (s || '').toLowerCase(); }

function matches(r, terms) {
  if (!terms.length) return true;
  const hay = norm(r.title) + ' ' + norm(r.contributor) + ' ' + norm(r.ingredients.join(' '));
  return terms.every(t => hay.includes(t));
}

// A recipe's wall sub-group label: its sub-category if it has one, else its category.
function groupLabel(r) { return r.sub || r.categoryName; }

// Ordered list of wall group labels: category order, with Vegetables and
// Regional expanded into their sub-groups.
function orderedLabels() {
  const out = [], seen = new Set();
  const push = L => { if (!seen.has(L)) { seen.add(L); out.push(L); } };
  for (const slug of CATEGORY_ORDER) {
    if (slug === 'vegetables') VEG_SUB_ORDER.forEach(push);
    else if (slug === 'regional' || slug === 'east') REGION_ORDER.forEach(push);
    else if (NAME_FOR[slug]) push(NAME_FOR[slug]);
  }
  return out;
}

function render() {
  els.recipe.hidden = true;
  els.about.hidden = true;
  els.results.hidden = false;
  const terms = els.q.value.trim().toLowerCase().split(/\s+/).filter(Boolean);
  const list = RECIPES.filter(r =>
    (!activeCat || r.category === activeCat) &&
    (!vegOnly || r.isVeg) &&
    matches(r, terms));
  els.count.textContent = `${list.length.toLocaleString()} recipe${list.length === 1 ? '' : 's'}`;

  const groups = new Map();
  for (const r of list) {
    const label = groupLabel(r);
    let g = groups.get(label);
    if (!g) { g = []; groups.set(label, g); }
    g.push(r);
  }
  const order = orderedLabels();
  for (const label of groups.keys()) if (!order.includes(label)) order.push(label);

  let out = '';
  for (const label of order) {
    const items = groups.get(label);
    if (!items) continue;
    out += `<section class="group"><h3 class="group-head">${esc(label)}` +
      `<span class="gc">${items.length}</span></h3><div class="wall">` +
      items.map(r => `<a class="rt${r.isVeg ? '' : ' nv'}" data-id="${r.id}">${esc(r.title)}</a>`).join('') +
      `</div></section>`;
  }
  els.results.innerHTML = out || '<p class="note">No recipes found.</p>';
}

function showRecipe(id) {
  const r = RECIPES.find(x => x.id === id);
  if (!r) { location.hash = ''; return; }
  els.results.hidden = true;
  els.about.hidden = true;
  els.recipe.hidden = false;
  const badge = r.isVeg
    ? '<span class="badge veg">veg</span>'
    : '<span class="badge nonveg">non-veg</span>';
  const by = r.contributor ? 'by ' + esc(r.contributor) + ' · ' : '';
  const cat = r.sub ? `${esc(r.categoryName)} · ${esc(r.sub)}` : esc(r.categoryName);
  els.recipe.innerHTML =
    `<button class="back">&larr; Back</button>` +
    `<h2>${esc(r.title)}${badge}</h2>` +
    `<div class="by">${by}${cat}</div>` +
    (r.ingredients.length
      ? `<h3>Ingredients</h3><ul>${r.ingredients.map(i => `<li>${esc(i)}</li>`).join('')}</ul>` : '') +
    (r.method.length
      ? `<h3>Method</h3><ol>${r.method.map(m => `<li>${esc(m.replace(/^\d+[.)]\s*/, ''))}</li>`).join('')}</ol>` : '');
  els.recipe.querySelector('.back').onclick = () => history.back();
  window.scrollTo(0, 0);
}

function showAbout() {
  els.results.hidden = true;
  els.recipe.hidden = true;
  els.about.hidden = false;
  els.about.querySelector('.back').onclick = () => history.back();
  window.scrollTo(0, 0);
}

function route() {
  const m = location.hash.match(/#\/recipe\/(\d+)/);
  if (m) showRecipe(parseInt(m[1], 10));
  else if (location.hash === '#/about') showAbout();
  else render();
}

function esc(s) {
  return (s || '').replace(/[&<>"]/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

els.results.addEventListener('click', e => {
  const a = e.target.closest('[data-id]');
  if (a) location.hash = '#/recipe/' + a.dataset.id;
});
els.q.addEventListener('input', () => {
  if (location.hash) location.hash = '';   // leaving a recipe/about view resets to list
  else render();
});
els.vegOnly.addEventListener('change', () => { vegOnly = els.vegOnly.checked; render(); });
window.addEventListener('hashchange', route);
