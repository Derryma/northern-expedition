# -*- coding: utf-8 -*-
"""把這一輪的省界與地盤改動拍成截圖存證，存到 _shots/。

拍三張：
  province_map_full.png          整張戰略圖
  province_map_northwest.png     西北一角（青海、甘肅、察哈爾、綏遠、陝西）
  province_map_sichuan.png       四川與川東
  province_map_qinghai.png       新的甘青省界，西寧留在甘肅那一側

不做判定，判定在 province_ownership_e2e.py。這支只負責讓人看得見。
"""
import pathlib as _pathlib
REPO = str(_pathlib.Path(__file__).resolve().parents[2])

import asyncio, os, subprocess, sys, tempfile, time, urllib.request
sys.path.insert(0, REPO)
from playwright.async_api import async_playwright

BASE = 'http://127.0.0.1:8776'
SHOTS = _pathlib.Path(REPO) / '_shots'

# frontend/map.js 的投影常數。截圖要把畫面移到指定經緯度上，得自己算一次。
MIN_LON, MAX_LON, MIN_LAT, MAX_LAT, K = 95, 135, 18, 54, 36
MAPW, MAPH = (MAX_LON - MIN_LON) * K, (MAX_LAT - MIN_LAT) * K


def start_server():
    try:
        urllib.request.urlopen(BASE + '/', timeout=1).read(1)
    except Exception:
        pass
    else:
        raise SystemExit(f"{BASE} 已經有東西在跑了")
    env = dict(os.environ)
    env['NE_GAME_DATA_DIR'] = tempfile.mkdtemp(prefix='ne-shot-')
    proc = subprocess.Popen(
        ['python3', '-c', 'from backend.server import run; run(port=8776)'],
        cwd=REPO, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(60):
        if proc.poll() is not None:
            raise SystemExit("伺服器啟動失敗")
        try:
            urllib.request.urlopen(BASE + '/', timeout=2).read(1)
            return proc
        except Exception:
            time.sleep(0.5)
    proc.kill()
    raise SystemExit("伺服器起不來")


HIDE_PANELS = """
() => {
  // 回合面板與提示框會蓋住地圖右半邊，存證時先收起來。
  for (const sel of ['#turnDock', '.turn-dock', '.overlay-panel', '#battlePanel',
                     '.phase-banner', '.map-controls']) {
    document.querySelectorAll(sel).forEach((el) => { el.style.display = 'none'; });
  }
}
"""

FOCUS = """
([lon, lat, zoom, MIN_LON, MAX_LAT, K, MAPW, MAPH]) => {
  const stage = document.getElementById('mapStage');
  const container = document.querySelector('.map-container');
  const x = (lon - MIN_LON) * K;
  const y = (MAX_LAT - lat) * K;
  const stageX = (x / MAPW) * stage.offsetWidth;
  const stageY = (y / MAPH) * stage.offsetHeight;
  const panX = container.clientWidth / 2 - stageX * zoom;
  const panY = container.clientHeight / 2 - stageY * zoom;
  stage.style.transform = `translate(${panX}px, ${panY}px) scale(${zoom})`;
}
"""


async def main():
    proc = start_server()
    SHOTS.mkdir(exist_ok=True)
    shots = []
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(args=['--no-sandbox'])
            page = await browser.new_page(viewport={'width': 1600, 'height': 1000})
            await page.goto(BASE + '/', wait_until='networkidle')
            await page.wait_for_timeout(7000)
            await page.evaluate(HIDE_PANELS)
            await page.wait_for_timeout(400)

            for name, lon, lat, zoom in [
                ('province_map_full', 115.0, 36.0, 1.0),
                ('province_map_northwest', 106.0, 37.5, 2.3),
                ('province_map_sichuan', 105.5, 30.5, 2.6),
                ('province_map_qinghai', 100.3, 36.4, 4.2),
            ]:
                await page.evaluate(FOCUS, [lon, lat, zoom, MIN_LON, MAX_LAT, K, MAPW, MAPH])
                await page.wait_for_timeout(700)
                path = SHOTS / f'{name}.png'
                await page.locator('.map-container').screenshot(path=str(path))
                shots.append(str(path))
            await page.close()
            await browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=8)
        except Exception:
            proc.kill()
    for path in shots:
        print(path)
    return 0


sys.exit(asyncio.run(main()))
