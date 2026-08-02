// Map rendering with realistic China map + hexagonal overlay + army markers

const canvas = document.getElementById('mapCanvas');
const ctx = canvas ? canvas.getContext('2d') : null;
const svg = document.getElementById('mapOverlay');

let selectedArmy = null;
let unmovedArmies = [];
let hoveredArmy = null;

// Initialize map rendering
function initMapRenderer() {
  if (!ctx) return;

  drawMap();
  renderArmyMarkers();
  setupMapInteraction();
  startUnitCycling();
}

// Draw realistic China map with provinces and rivers
function drawMap() {
  // Clear canvas
  ctx.fillStyle = '#2a2520';
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw provinces with faction colors
  PROVINCES.forEach(prov => {
    const [west, east, south, north] = prov.bounds;
    const topLeft = lonLatToXY(west, north, MAP_BOUNDS);
    const bottomRight = lonLatToXY(east, south, MAP_BOUNDS);

    const faction = FACTIONS[prov.faction];
    if (faction) {
      // Semi-transparent faction fill
      ctx.fillStyle = faction.color + '33'; // 20% opacity
      ctx.fillRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);
    }

    // Province border
    ctx.strokeStyle = '#6b5c38';
    ctx.lineWidth = 1;
    ctx.strokeRect(topLeft.x, topLeft.y, bottomRight.x - topLeft.x, bottomRight.y - topLeft.y);

    // Province label
    const center = lonLatToXY((west + east) / 2, (south + north) / 2, MAP_BOUNDS);
    ctx.fillStyle = '#f3ecdb';
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(prov.name, center.x, center.y);
  });

  // Draw rivers
  ctx.strokeStyle = '#4a7c8a';
  ctx.lineWidth = 2;
  RIVERS.forEach(river => {
    ctx.beginPath();
    river.pts.forEach((pt, idx) => {
      const { x, y } = lonLatToXY(pt[0], pt[1], MAP_BOUNDS);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  });

  // Draw cities
  CITIES.forEach(city => {
    const { x, y } = lonLatToXY(city.lon, city.lat, MAP_BOUNDS);

    // City dot
    ctx.fillStyle = '#f3ecdb';
    ctx.beginPath();
    ctx.arc(x, y, city.level, 0, Math.PI * 2);
    ctx.fill();

    // City name
    ctx.fillStyle = '#f3ecdb';
    ctx.font = 'bold 11px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(city.name, x, y - city.level - 4);
  });
}

// Render army markers (番號) as SVG overlays
function renderArmyMarkers() {
  const markersGroup = document.getElementById('armyMarkers');
  if (!markersGroup) return;

  markersGroup.innerHTML = '';

  armies.forEach(army => {
    const { x, y } = lonLatToXY(army.location.lon, army.location.lat, MAP_BOUNDS);

    // Army marker group
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    g.setAttribute('data-army', army.id);
    g.setAttribute('transform', `translate(${x}, ${y})`);
    g.style.cursor = 'pointer';

    // Halo for unmoved units (not constant animation on hover)
    if (!army.has_moved) {
      const halo = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      halo.setAttribute('r', 20);
      halo.setAttribute('fill', 'none');
      halo.setAttribute('stroke', '#ffd700');
      halo.setAttribute('stroke-width', 3);
      halo.setAttribute('opacity', 0.6);
      halo.style.animation = 'pulse 2s ease-in-out infinite';
      g.appendChild(halo);
    }

    // Base circle
    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('r', 16);
    circle.setAttribute('fill', FACTIONS[army.faction].color);
    circle.setAttribute('stroke', 'white');
    circle.setAttribute('stroke-width', 2);
    g.appendChild(circle);

    // 番號 text
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dy', '0.35em');
    text.setAttribute('fill', 'white');
    text.setAttribute('font-size', '13');
    text.setAttribute('font-weight', 'bold');
    text.setAttribute('pointer-events', 'none');
    text.textContent = army.designation.replace('第', '').replace('軍', '');
    g.appendChild(text);

    // Event listeners
    g.addEventListener('click', () => onArmyClick(army));
    g.addEventListener('mouseenter', () => onArmyHover(army, true));
    g.addEventListener('mouseleave', () => onArmyHover(army, false));

    markersGroup.appendChild(g);
  });
}

// Army click handler
function onArmyClick(army) {
  selectedArmy = army;
  console.log(`選中 ${army.designation}:`, army.units);

  // TODO: Show movement range
  // TODO: Enable valid province clicks
}

// Army hover handler (show unit composition tooltip)
function onArmyHover(army, isEnter) {
  hoveredArmy = isEnter ? army : null;

  if (isEnter) {
    // Show tooltip with unit composition
    const unitsText = `步${army.units.infantry} 騎${army.units.cavalry} 砲${army.units.artillery} 機${army.units.machine_gun}`;
    console.log(`${army.designation}: ${unitsText}`);
    // TODO: Create visual tooltip
  }
}

// Setup map interaction
function setupMapInteraction() {
  if (!canvas) return;

  canvas.addEventListener('click', (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const y = e.clientY - rect.top;

    // TODO: Convert click position to lon/lat
    // TODO: Check if clicked province is valid move destination
    // TODO: Move army if valid
  });
}

// Civ6-style unit cycling
function startUnitCycling() {
  updateUnmovedList();
  if (unmovedArmies.length > 0) {
    cycleToNextUnit();
  }
}

function updateUnmovedList() {
  unmovedArmies = armies.filter(a => !a.has_moved);
}

function cycleToNextUnit() {
  updateUnmovedList();

  if (unmovedArmies.length === 0) {
    console.log('所有部隊已移動 - 可以結束回合');
    selectedArmy = null;
    return;
  }

  selectedArmy = unmovedArmies[0];
  console.log(`自動選中: ${selectedArmy.designation}`);

  // Pan camera to unit (simplified - would use smooth animation)
  // TODO: Implement camera pan
}

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
  if (e.key === ' ' || e.key === 'Enter') {
    // Skip current unit
    if (selectedArmy) {
      selectedArmy.has_moved = true;
      renderArmyMarkers();
      cycleToNextUnit();
    }
  }
});

// Export for use in app.js
window.mapRenderer = {
  init: initMapRenderer,
  renderArmies: renderArmyMarkers,
  cycleNext: cycleToNextUnit,
};
