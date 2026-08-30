# -*- coding: utf-8 -*-
"""突變測試（安全版）。

先前幾次被外部逾時砍掉的突變跑，都在原始碼裡留下了突變體。第一次是靠測試紅燈
才發現，第二次我用 `grep "if False"` 檢查——**那是個爛檢查**，因為不是每個
突變都長那樣，於是漏掉了一個。更糟的是重跑時腳本把**已經被污染的檔案**
當成基準讀進去，於是那一項顯示「目標字串找不到，跳過」，看起來像設定問題。

所以這一版：跑之前把每個目標檔的基準 md5 與**乾淨副本**都寫進檔案；
每一輪結束逐位元組比對；啟動時先檢查上一次有沒有留下殘骸，有就自動還原。

突變體可以是三元組 (名稱, 原字串, 新字串)——預設打在 backend/card_engine.py 上——
或四元組 (名稱, 原字串, 新字串, 相對路徑)，用來打其他檔案（例如 combat_modifiers.py）。
"""
import pathlib as _pathlib
# repo 根目錄由這支腳本自己的位置推出來，不寫死路徑——
# 換一個容器、換一台機器都還跑得動。
REPO_ROOT = str(_pathlib.Path(__file__).resolve().parents[2])

import hashlib, json, pathlib, shutil, subprocess, sys, atexit

REPO = pathlib.Path(REPO_ROOT)
DEFAULT_TARGET = 'backend/card_engine.py'
GUARD = pathlib.Path('/tmp/mutation_baseline.json')
PRISTINE_DIR = pathlib.Path('/tmp/mutation_pristine')


def digest(path: pathlib.Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def _pristine_path(rel: str) -> pathlib.Path:
    return PRISTINE_DIR / rel.replace('/', '__')


def _restore_from_pristine(saved: dict) -> bool:
    """從乾淨副本還原所有對不上基準的檔案。回傳有沒有全部還原成功。"""
    ok = True
    for rel, want in saved.items():
        target = REPO / rel
        if digest(target) == want:
            continue
        backup = _pristine_path(rel)
        if backup.exists() and hashlib.md5(backup.read_bytes()).hexdigest() == want:
            target.write_bytes(backup.read_bytes())
            print(f"   已從 {backup} 還原 {rel}")
        else:
            print(f"   !! {rel} 對不上基準，而且沒有可用的乾淨副本")
            ok = False
    return ok


def main(mutants, runner=None, timeout=2400):
    """runner：判定「這個突變有沒有被抓到」的指令。

    預設是整套 backend 單元測試。前端行為的突變靠讀原始碼的字串斷言擋不住
    （`if (false) {` 就繞過去了），所以那種輪次要改用真前端的 e2e 當 runner——
    e2e 跑的是瀏覽器裡真正的那份程式碼。
    """
    # 補齊三元組的預設目標檔
    normalised = [(m[0], m[1], m[2], m[3] if len(m) > 3 else DEFAULT_TARGET)
                  for m in mutants]
    targets = sorted({rel for _, _, _, rel in normalised})

    if GUARD.exists():
        saved = json.loads(GUARD.read_text())
        if any(digest(REPO / rel) != want for rel, want in saved.items()):
            print("!! 上一次突變跑留下了殘骸——原始碼與基準不符。")
            if not _restore_from_pristine(saved):
                print("   先還原再跑。")
                return 1

    originals = {rel: (REPO / rel).read_bytes() for rel in targets}
    base = {rel: digest(REPO / rel) for rel in targets}
    PRISTINE_DIR.mkdir(parents=True, exist_ok=True)
    for rel, blob in originals.items():
        _pristine_path(rel).write_bytes(blob)
    GUARD.write_text(json.dumps(base, ensure_ascii=False))

    def restore_all():
        for rel, blob in originals.items():
            (REPO / rel).write_bytes(blob)
    atexit.register(restore_all)

    command = runner or [sys.executable, '-m', 'unittest', 'backend.test_backend', '-q']

    def run():
        for p in REPO.rglob('__pycache__'):
            shutil.rmtree(p, ignore_errors=True)
        r = subprocess.run(command, cwd=REPO, capture_output=True, text=True,
                           timeout=timeout)
        blob = r.stderr + r.stdout
        return r.returncode == 0, blob.count('FAIL:') + blob.count('ERROR:') + blob.count('**沒過**')

    for name, old, new, rel in normalised:
        text = originals[rel].decode('utf-8')
        n = text.count(old)
        if n != 1:
            # 出現 0 次通常是縮排抄錯。這不是「通過」，是這一項根本沒跑。
            print(f'!! {name}：在 {rel} 裡目標出現 {n} 次，跳過', flush=True)
            continue
        (REPO / rel).write_text(text.replace(old, new), encoding='utf-8')
        try:
            ok, fails = run()
        finally:
            restore_all()
            assert digest(REPO / rel) == base[rel], f'{name} 還原失敗'
        print(f'   {name}：{"被抓到" if not ok else "逃掉了"}（{fails} 條紅）', flush=True)

    for p in REPO.rglob('__pycache__'):
        shutil.rmtree(p, ignore_errors=True)
    for rel in targets:
        assert digest(REPO / rel) == base[rel], f'收尾時 {rel} 與基準不符'
    GUARD.unlink(missing_ok=True)
    shutil.rmtree(PRISTINE_DIR, ignore_errors=True)
    print('來源已還原，逐位元組與基準相同。')
    return 0
