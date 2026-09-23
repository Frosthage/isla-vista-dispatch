(function () {
  var data = JSON.parse(document.getElementById('data').textContent);
  var byId = {};
  data.forEach(function (d) { byId[d.id] = d; });

  var map = L.map('map').setView(REGION.center, REGION.zoom);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(map);
  var cluster = L.markerClusterGroup({ maxClusterRadius: 40, disableClusteringAtZoom: 17 });
  map.addLayer(cluster);
  var markers = {};

  function money(v) { return v ? '$' + v.toLocaleString() : 'Price on request'; }
  function popup(d) {
    var img = d.photo ? '<img src="' + (d.photo.indexOf('http') === 0 ? '' : ROOT) + d.photo + '" alt="">' : '';
    return img + '<a class="pp-title" href="' + ROOT + 'l/' + d.id + '.html">' + d.title + '</a>' +
      (d.address ? d.address + (d.unit ? ' #' + d.unit : '') + '<br>' : '') +
      '<strong>' + money(d.rent) + '</strong>' + (d.beds != null ? ' · ' + d.beds + ' bd' : '') + (d.new ? ' · <span style="color:#0f9d58">New</span>' : '');
  }
  var colors = { lease: '#0a66c2', sublease: '#b25e09', room: '#7a3db8' };
  data.forEach(function (d) {
    if (d.lat == null) return;
    var m = L.circleMarker([d.lat, d.lng], { radius: 8, color: '#fff', weight: 1.5, fillColor: colors[d.kind] || '#333', fillOpacity: 0.95 });
    m.bindPopup(popup(d));
    m.on('click', function () {
      document.querySelectorAll('.card.active').forEach(function (c) { c.classList.remove('active'); });
      var card = document.getElementById('c-' + d.id);
      if (card) { card.classList.add('active'); card.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
    });
    markers[d.id] = m;
  });

  var form = document.getElementById('filters');
  var cards = Array.prototype.slice.call(document.querySelectorAll('.card'));
  cards.forEach(function (c) {
    c.addEventListener('mouseenter', function () { var m = markers[c.dataset.id]; if (m) m.setStyle({ radius: 12 }); });
    c.addEventListener('mouseleave', function () { var m = markers[c.dataset.id]; if (m) m.setStyle({ radius: 8 }); });
  });

  function avail(text, want) {
    if (!want) return true;
    if (want === '2027') return /2027/.test(text) && !/^2026|now/.test(text);
    return !/2027/.test(text);
  }
  function apply() {
    var kinds = Array.prototype.map.call(form.querySelectorAll('input[name=kind]:checked'), function (i) { return i.value; });
    var beds = parseFloat(form.beds.value) || 0;
    var rent = parseFloat(form.rent.value) || Infinity;
    var source = form.source.value;
    var want = form.avail.value;
    var onlyNew = form.new.checked;
    var sort = form.sort.value;
    var visible = [];
    cards.forEach(function (c) {
      var d = c.dataset;
      var ok = kinds.indexOf(d.kind) >= 0 &&
        (!beds || parseFloat(d.beds) >= beds) &&
        (!d.rent || parseFloat(d.rent) <= rent) &&
        (!source || d.source === source) &&
        avail(d.avail, want) &&
        (!onlyNew || d.new === '1');
      c.hidden = !ok;
      if (ok) visible.push(c);
    });
    visible.sort(function (a, b) {
      var ra = parseFloat(a.dataset.rent) || Infinity, rb = parseFloat(b.dataset.rent) || Infinity;
      if (sort === 'rent-asc') return ra - rb;
      if (sort === 'rent-desc') return (rb === Infinity ? -1 : rb) - (ra === Infinity ? -1 : ra);
      if (sort === 'beds') return (parseFloat(b.dataset.beds) || 0) - (parseFloat(a.dataset.beds) || 0);
      return (b.dataset.new - a.dataset.new) || (ra - rb);
    });
    var parent = document.getElementById('cards');
    visible.forEach(function (c) { parent.appendChild(c); });
    cluster.clearLayers();
    visible.forEach(function (c) { var m = markers[c.dataset.id]; if (m) cluster.addLayer(m); });
    document.getElementById('count').textContent = visible.length;
    document.getElementById('empty').hidden = visible.length > 0;
    try { localStorage.setItem('filters:' + location.pathname, JSON.stringify(serialize())); } catch (e) {}
  }
  function serialize() {
    var o = {};
    Array.prototype.forEach.call(form.elements, function (el) {
      if (!el.name) return;
      if (el.type === 'checkbox') o[el.name + ':' + el.value] = el.checked; else o[el.name] = el.value;
    });
    return o;
  }
  function restore() {
    try {
      var o = JSON.parse(localStorage.getItem('filters:' + location.pathname) || 'null');
      if (!o) return;
      Array.prototype.forEach.call(form.elements, function (el) {
        if (!el.name) return;
        if (el.type === 'checkbox') { if ((el.name + ':' + el.value) in o) el.checked = o[el.name + ':' + el.value]; }
        else if (el.name in o) el.value = o[el.name];
      });
    } catch (e) {}
  }
  form.addEventListener('input', apply);
  form.addEventListener('change', apply);
  document.getElementById('reset').addEventListener('click', function () { form.reset(); apply(); });
  restore();
  apply();
})();
