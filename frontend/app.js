const portraits = {
  F: "/assets/portraits/張作霖.jpg",
  W: "/assets/portraits/吳佩孚.jpg",
  S: "/assets/portraits/孫傳芳.jpg",
  N: "/assets/portraits/蔣介石.jpg",
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
  if (!card) return "無事件";
  const bits = [card.name || card.id];
  if (card.category) bits.push(card.category);
  if (card.foreign_power) bits.push(card.foreign_power);
  if (card.npc_faction) bits.push(card.npc_faction);
  return bits.join(" · ");
}

function shortEffect(card) {
  if (!card) return "尚未抽事件。";
  const injected = card.generated_event_cards?.length
    ? `\n\n注入事件：${card.generated_event_cards.map((c) => c.name || c.id).join("、")}`
    : "";
  return `${cardTitle(card)}\n\n${card.effect || "無效果文字"}${injected}`;
}

function render() {
  $("turnBadge").textContent = `回合 ${state.turn}`;
  $("statusLine").textContent = `事件池 ${state.counts.event_pool} · 注入 ${state.counts.injected_event_pool}`;
  $("poolMeta").textContent = `事件 ${state.counts.event_pool} / 注入 ${state.counts.injected_event_pool}`;
  $("eventCard").textContent = shortEffect(state.last_event);
  $("eventCard").classList.toggle("empty", !state.last_event);
  renderHands();
}

function renderHands() {
  $("hands").innerHTML = Object.entries(state.players).map(([player, payload]) => {
    const faction = bootstrap.players.find((item) => item.code === player);
    const cards = payload.hand.map((id) => cardIndex[id]).filter(Boolean);
    const body = cards.length
      ? cards.map((card) => `
        <div class="hand-card">
          <div>
            <b>${card.name}</b>
            <small>${card.category || "function"}</small>
          </div>
          <button data-use="${card.id}" data-player="${player}" title="打出功能卡">打出</button>
        </div>
      `).join("")
      : `<div class="hand-card muted">無手牌</div>`;
    return `
      <div class="hand">
        <div class="hand-head">
          <img src="${portraits[player] || ""}" alt="">
          <div>
            <h3>${player} · ${faction?.leader || player}</h3>
            <small>牌庫 ${payload.function_deck.length} · 手牌 ${payload.hand.length} · 棄牌 ${payload.discard.length}</small>
          </div>
        </div>
        ${body}
      </div>
    `;
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
        $("eventCard").textContent = `功能卡已打出：${result.card.name}\n\n注入事件池：\n${result.injected.map(cardTitle).join("\n")}`;
        $("eventCard").classList.remove("empty");
      }
    });
  });
}

function setupBoardTabs() {
  document.querySelectorAll("[data-board]").forEach((button) => {
    button.addEventListener("click", () => {
      document.querySelectorAll("[data-board]").forEach((item) => item.classList.remove("active"));
      button.classList.add("active");
      $("boardFrame").src = button.dataset.board;
    });
  });
}

function setupCombatDefaults() {
  $("armyA").value = JSON.stringify({
    name: "北伐第一軍",
    units: { infantry: 10, cavalry: 2, artillery: 2, machine_gun: 2 },
    tactic: "normal_advance",
  }, null, 2);
  $("armyB").value = JSON.stringify({
    name: "直系守軍",
    units: { infantry: 9, cavalry: 1, artillery: 2, machine_gun: 3 },
    tactic: "layered_delaying",
  }, null, 2);
}

async function boot() {
  bootstrap = await api("/api/bootstrap");
  indexCards();
  state = await api("/api/new-game", { players: bootstrap.players.map((p) => p.code) });
  $("playerSelect").innerHTML = bootstrap.players.map((p) => `<option value="${p.code}">${p.code} · ${p.leader}</option>`).join("");
  setupBoardTabs();
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
