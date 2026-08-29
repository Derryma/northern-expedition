import hashlib, os, sys, json
root = sys.argv[1]
# `_to_delete/` 只存在於使用者本機——device_bash 刪不掉檔案，所以要丟棄的東西
# 都搬進那裡等他自己清。它不該算進指紋，否則兩邊永遠對不起來。
skip_dirs = {'.git', '__pycache__', 'node_modules', '_source', 'PJ Boardgame',
             '_to_delete'}
rows = []
for base, dirs, files in os.walk(root):
    dirs[:] = [d for d in dirs if d not in skip_dirs]
    for name in files:
        path = os.path.join(base, name)
        rel = os.path.relpath(path, root)
        if rel.startswith('.git') or '__pycache__' in rel:
            continue
        with open(path, 'rb') as fh:
            data = fh.read().replace(b'\r\n', b'\n')
        rows.append((rel, hashlib.md5(data).hexdigest()))
rows.sort()
overall = hashlib.md5('\n'.join(f'{r}:{h}' for r, h in rows).encode()).hexdigest()
print(json.dumps({'files': len(rows), 'overall': overall,
                  'rows': dict(rows)}, ensure_ascii=False))
