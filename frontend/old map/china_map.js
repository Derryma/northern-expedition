// China map rendering and interaction logic

let selectedArmy = null;
let unmovedArmies = [];
let currentArmyIndex = 0;

// Initialize map
function initMap() {
  renderProvinces();
  renderArmies();
  startUnitCycling();
}

// Render provinces as simplified shapes
function renderProvinces() {
  const provincesGroup = document.getElementById('provinces');

  provinces.forEach(prov => {
    // Create simple hexagon for each province
    const hex = createHexagon(prov.x, prov.y, 60);
    hex.setAttribute('class', `province faction-${prov.controlled_by}`);
    hex.setAttribute('data-province', prov.id);
    hex.addEventListener('click', () => onProvinceClick(prov));

    provincesGroup.appendChild(hex);

    // Add province label
    const label = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    label.setAttribute('x', prov.x);
    label.setAttribute('y', prov.y + 5);
    label.setAttribute('class', 'province-label');
    label.textContent = prov.name;
    provincesGroup.appendChild(label);
  });
}

// Create hexagon path
function createHexagon(cx, cy, size) {
  const points = [];
  for (let i = 0; i < 6; i++) {
    const angle = (Math.PI / 3) * i;
    const x = cx + size * Math.cos(angle);
    const y = cy + size * Math.sin(angle);
    points.push(`${x},${y}`);
  }

  const polygon = document.createElementNS('http://www.w3.org/2000/svg', 'polygon');
  polygon.setAttribute('points', points.join(' '));
  return polygon;
}

// Render army markers (番號)
function renderArmies() {
  const armiesGroup = document.getElementById('armies');
  armiesGroup.innerHTML = '';

  armies.forEach(army => {
    const prov = provinces.find(p => p.id === army.location);
    if (!prov) return;

    // Army marker group
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('class', `army-marker ${!army.has_moved ? 'unmoved' : ''}`);
    g.setAttribute('data-army', army.id);
    g.setAttribute('transform', `translate(${prov.x}, ${prov.y})`);

    // Halo circle (for unmoved units)
    const halo = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    halo.setAttribute('r', 28);
    halo.setAttribute('class', 'army-halo');
    g.appendChild(halo);

    // Base circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', 24);
    circle.setAttribute('fill', factionColors[army.faction]);
    circle.setAttribute('stroke', 'white');
    circle.setAttribute('stroke-width', 2);
    circle.setAttribute('filter', 'url(#shadow)');
    g.appendChild(circle);

    // Designation text (番號)
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('y', 6);
    text.setAttribute('class', 'army-designation');
    text.textContent = army.designation.replace('第', '').replace('軍', '');
    g.appendChild(text);

    g.addEventListener('click', () => onArmyClick(army));
    armiesGroup.appendChild(g);
  });
}

// Province click handler
function onProvinceClick(province) {
  if (!selectedArmy) return;

  // Check if province is adjacent
  const currentProv = provinces.find(p => p.id === selectedArmy.location);
  if (!currentProv.adjacent.includes(province.id)) {
    console.log('Province not adjacent');
    return;
  }

  // Move army
  selectedArmy.location = province.id;
  selectedArmy.has_moved = true;

  // Re-render and cycle to next
  renderArmies();
  cycleToNextUnmovedUnit();
}

// Army click handler
function onArmyClick(army) {
  selectedArmy = army;
  console.log(`Selected ${army.designation}`, army.units);
}

// Civ6-style unit cycling
function startUnitCycling() {
  updateUnmovedList();
  if (unmovedArmies.length > 0) {
    cycleToNextUnmovedUnit();
  }
}

function updateUnmovedList() {
  unmovedArmies = armies.filter(a => !a.has_moved);
  currentArmyIndex = 0;
}

function cycleToNextUnmovedUnit() {
  updateUnmovedList();

  if (unmovedArmies.length === 0) {
    console.log('All units moved - ready for next turn');
    selectedArmy = null;
    return;
  }

  selectedArmy = unmovedArmies[currentArmyIndex];

  // Pan camera to selected unit
  const prov = provinces.find(p => p.id === selectedArmy.location);
  if (prov) {
    panCameraTo(prov.x, prov.y);
  }

  console.log(`Auto-selected: ${selectedArmy.designation} at ${selectedArmy.location}`);
}

function panCameraTo(x, y) {
  // Simple pan - center the viewBox on the target
  const svg = document.getElementById('map');
  const viewBox = svg.viewBox.baseVal;

  // Animate viewBox (simplified - real implementation would use smooth transition)
  const newX = x - viewBox.width / 2;
  const newY = y - viewBox.height / 2;
  svg.setAttribute('viewBox', `${newX} ${newY} ${viewBox.width} ${viewBox.height}`);
}

// Keyboard controls
document.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' || e.key === ' ') {
    // Skip current unit
    if (selectedArmy) {
      selectedArmy.has_moved = true;
      renderArmies();
      cycleToNextUnmovedUnit();
    }
  }
});

// Initialize on load
window.addEventListener('load', initMap);
