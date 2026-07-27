const portraits = {
  F: "/assets/portraits/張作霖.jpg",
  W: "/assets/portraits/吳佩孚.jpg",
  S: "/assets/portraits/孫傳芳.jpg",
  N: "/assets/portraits/蔣介石.jpg",
};

const colors = {
  F: "#546e7a",
  W: "#6a1b9a",
  S: "#2e7d32",
  N: "#b1812f",
};

let bootstrap = null;
let state = null;
let cardIndex = {};

const $ = (id) => document.getElementById(id);

async function api(path, payload = null) {
  const options = payload
    ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) }
    : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || response.statusText);
  return data;
}

function indexCards() {
  cardIndex = {};
  for (const group of Object.values(bootstrap.cards)) {
    for (const card of group) cardIndex[card.id] = card;
  }
}

function cardTitle(card) {
  const bits = [card.name || card.id];
  if (card.category) bits.push(card.category);
  if (card.foreign_power) bits.push(card.foreign_power);
  if (card.npc_faction) bits.push(card.npc_faction);
  return bits.join(" · ");
}

function renderCard(card) {
  if (!card) return "No event drawn.";
  const lines = [cardTitle(card), "", card.effect || ""];
  if (card.generated_event_cards?.length) {
    lines.push("", "Injects: " + card.generated_event_cards.map((c) => c.name || c.id).join(", "));
  }
  return lines.join("\n");
}

function render() {
  $("turnBadge").textContent = `Turn ${state.turn}`;
  $("statusLine").textContent = `Events ${state.counts.event_pool} · Injected ${state.counts.injected_event_pool}`;
  $("poolMeta").textContent = `Event ${state.counts.event_pool} / Injected ${state.counts.injected_event_pool}`;
  $("eventMeta").textContent = state.last_event ? cardTitle(state.last_event) : "-";
  $("eventCard").textContent = renderCard(state.last_event);
  $("eventCard").classList.toggle("empty", !state.last_event);
  renderFactions();
  renderHands();
  renderReference();
}

function renderFactions() {
  $("factions").innerHTML = bootstrap.players.map((faction) => `
    <div class="faction" style="--swatch:${colors[faction.code] || "#9c8b71"}">
      <img src="${portraits[faction.code] || ""}" alt="">
      <div>
        <h3>${faction.leader}</h3>
        <small>${faction.code} · ${faction.name}</small>
        <small>Deck ${state.counts.players[faction.code]?.deck ?? 0} · Hand ${state.counts.players[faction.code]?.hand ?? 0}</small>
      </div>
    </div>
  `).join("");
}

function renderHands() {
  $("hands").innerHTML = Object.entries(state.players).map(([player, payload]) => {
    const cards = payload.hand.map((id) => cardIndex[id]).filter(Boolean);
    const body = cards.length ? cards.map((card) => `
      <div class="mini-card">
        <span>${card.name}<small class="tag">${card.category || "function"}</small></span>
        <button data-use="${card.id}" data-player="${player}" title="Use card">✓</button>
      </div>
    `).join("") : `<div class="mini-card"><span>No cards</span></div>`;
    return `<div class="hand"><h3>${player}</h3>${body}</div>`;
  }).join("");

  document.querySelectorAll("[data-use]").forEach((button) => {
    button.addEventListener("click", async () => {
      const result = await api("/api/use-function", {
        player: button.dataset.player,
        card_id: button.dataset.use,
      });
      state = result.state;
      render();
      if (result.injected.length) {
        $("eventCard").textContent = `Injected into event pool:\n\n${result.injected.map(cardTitle).join("\n")}`;
        $("eventCard").classList.remove("empty");
      }
    });
  });
}

function renderReference() {
  const mode = $("referenceMode").value;
  const query = $("referenceSearch").value.trim().toLowerCase();
  let items = [];
  if (mode === "function") items = bootstrap.cards.function;
  if (mode === "event") items = bootstrap.cards.event;
  if (mode === "injected") items = bootstrap.cards.injected_event;
  if (mode === "npc") items = bootstrap.npc_factions;
  if (mode === "foreign") items = Object.values(bootstrap.foreign_powers.powers);

  const filtered = items.filter((item) => JSON.stringify(item).toLowerCase().includes(query)).slice(0, 80);
  $("referenceList").innerHTML = filtered.map((item) => {
    if (mode === "npc") {
      return `<article class="reference-item"><h3>${item.name}<span class="tag">${item.code}</span></h3><p>${item.generals.join("、")}</p></article>`;
    }
    if (mode === "foreign") {
      return `<article class="reference-item"><h3>${item.display_name}</h3><p>${(item.territories || []).join("、")}</p></article>`;
    }
    return `<article class="reference-item"><h3>${cardTitle(item)}</h3><p>${item.effect || ""}</p></article>`;
  }).join("");
}

function setupCombatDefaults() {
  $("armyA").value = JSON.stringify({
    name: "A Test Army",
    units: { infantry: 10, cavalry: 2, artillery: 2, machine_gun: 2 },
    tactic: "normal_advance",
  }, null, 2);
  $("armyB").value = JSON.stringify({
    name: "B Test Army",
    units: { infantry: 9, cavalry: 1, artillery: 2, machine_gun: 3 },
    tactic: "layered_delaying",
  }, null, 2);
}

async function boot() {
  bootstrap = await api("/api/bootstrap");
  indexCards();
  state = await api("/api/new-game", { players: bootstrap.players.map((p) => p.code) });
  $("playerSelect").innerHTML = bootstrap.players.map((p) => `<option value="${p.code}">${p.code} · ${p.leader}</option>`).join("");
  setupCombatDefaults();
  render();
}

$("newGame").addEventListener("click", async () => {
  state = await api("/api/new-game", { players: bootstrap.players.map((p) => p.code) });
  render();
});

$("nextTurn").addEventListener("click", async () => {
  const result = await api("/api/next-turn", {});
  state = result.state;
  render();
});

$("drawEvent").addEventListener("click", async () => {
  const result = await api("/api/draw-event", {});
  state = result.state;
  render();
});

$("drawFunction").addEventListener("click", async () => {
  const result = await api("/api/draw-function", { player: $("playerSelect").value });
  state = result.state;
  render();
});

$("referenceMode").addEventListener("change", renderReference);
$("referenceSearch").addEventListener("input", renderReference);

$("runCombat").addEventListener("click", async () => {
  try {
    const result = await api("/api/combat", {
      army_a: JSON.parse($("armyA").value),
      army_b: JSON.parse($("armyB").value),
      max_rounds: 8,
    });
    $("combatResult").textContent = JSON.stringify({
      winner: result.winner,
      rounds: result.rounds,
      remaining: result.remaining,
      first_round: result.log[0],
    }, null, 2);
  } catch (error) {
    $("combatResult").textContent = error.message;
  }
});

boot().catch((error) => {
  $("statusLine").textContent = error.message;
});
