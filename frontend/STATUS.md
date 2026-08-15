# Current Status

Updated 2026-08-15.

The map overhaul, fog of war, army markers, reserve pool, general tree, cards, shared events, NPC armies, multiplayer synchronization, and first naval layer are implemented.

Current composition invariant: a field army's battalion totals live only in `army.units`. Backend reserve transfer returns a delta and does not maintain a second combat ledger. This prevents replenished units from being materialized again after fighting NPC armies.

Current naval invariant: fire eligibility is checked at the start of each exchange. A division with no active gunboat takes fire without replying and retreats. An army remains in contact while at least one artillery battalion survives. If both fleets cross their retreat line in the same exchange, higher remaining gunboat HP holds the tile; equal HP makes both withdraw.

Known architectural limit: Render and local shared games are memory-backed. A server restart requires restoring a saved snapshot.
