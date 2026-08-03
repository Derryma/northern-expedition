# Remote play

The game server synchronizes the map, armies, battles, generals, loyalty, jails, cards, economy, and turn state between browsers.

## Recommended: Render public playtest

Use Render when you want a normal public HTTPS link and do not want to keep a MacBook running.

1. Push the latest code to GitHub.
2. Go to <https://dashboard.render.com/>.
3. Choose **New > Blueprint** if Render offers the `render.yaml` blueprint flow, or **New > Web Service**.
4. Connect `https://github.com/MaelLiu/northern-expedition`.
5. Use these settings if entering them manually:

   ```text
   Runtime: Python
   Build Command: python3 -m py_compile scripts/run_playtest_server.py backend/server.py
   Start Command: python3 scripts/run_playtest_server.py
   Plan: Free
   ```

6. Render will set the `PORT` environment variable automatically. The launcher falls back to `8766` only for local play.
7. Share the generated `https://...onrender.com` URL with players.

Free Render services can sleep after idle time, so the first load after a break can take about a minute. The current playtest state is held in server memory, so a redeploy, restart, or sleep can reset the active session until persistent storage is added.

## Alternative: Tailscale local host

Use Tailscale when you want no cloud account and are willing to keep one host computer running.

## One-time Tailscale setup

1. Install Tailscale on both computers: <https://tailscale.com/download>
2. Sign both computers into the same Tailscale network.
3. On the host computer, open Terminal in this project and run:

   ```bash
   python3 scripts/run_playtest_server.py
   ```

4. Find the host's Tailscale IPv4 address in the Tailscale app, or run:

   ```bash
   tailscale ip -4
   ```

5. On the second computer, open:

   ```text
   http://100.66.153.107:8766
   ```

The current host address is `100.66.153.107`. If the host address changes, run `tailscale ip -4` on the host again.

Keep the host Terminal window open while playing. The host browser uses `http://127.0.0.1:8766`.

## Session behavior

- Opening or refreshing the page joins the existing match; it no longer starts a new game.
- Changes synchronize about once per second.
- Only the **重新開始** button creates a fresh match for every connected player.
- The current playtest state is held in server memory, so stopping the Python server ends that session.
- GitHub Pages cannot run this Python game server or synchronize live match state. GitHub can store the source, but Render or Tailscale must run the live server for this build.

If macOS asks whether Python may accept incoming connections, choose **Allow**.

## Partner handoff for an AI coding agent

Give your agent this instruction:

> I need to join a remote local playtest. Install or open Tailscale, sign in to the same tailnet as the host, and verify that `100.66.153.107` is reachable. Do not start a second game server. Open `http://100.66.153.107:8766` in my browser. If it does not connect, check that Tailscale is connected, that the host is running `python3 scripts/run_playtest_server.py`, and that TCP port 8766 is allowed. The game state is synchronized by the host server; refreshing the page should join the existing match.
