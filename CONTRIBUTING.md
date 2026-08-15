# Contributing

Thanks for helping build the game.

## Local playtest workflow

1. Pull the latest `main` before starting a new change.
2. Run `python3 scripts/run_playtest_server.py` and open `http://127.0.0.1:8766`.
3. Keep debugger-only work local. Do not push or trigger the Render deployment unless Owen explicitly requests a production update.
4. Before restarting a live local match, save `/api/shared-state` to `state_snapshots/` and restore it after restart; use the commands in `REMOTE_PLAY.md`.
5. Test the affected backend, combat, general-tree, and navy modules before opening a pull request.

## Workflow

1. Open an issue or discussion for bigger ideas before doing a large change.
2. Keep each pull request focused on one feature, fix, asset batch, or document update.
3. Explain what changed and how to try it.
4. Do not upload secrets, passwords, private keys, or personal files.
5. Never commit live playtest snapshots; they may contain unfinished player decisions.

## Good contributions

- Game mechanics and prototypes.
- Bug fixes.
- Art, music, sound, and other assets you have the right to share.
- Documentation, design notes, balancing ideas, and task lists.

## Asset rules

Only upload assets you created yourself or have permission to use in this project. Include attribution when required.
