import pathlib, re, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
p = pathlib.Path(r"C:\Users\admin\AppData\Roaming\StardewValley\Saves\Wahaha_450799035\Wahaha_450799035")
xml = p.read_text(encoding="utf-8", errors="replace")
# 定位 Farm 的 GameLocation 块：<GameLocation xsi:type="Farm"> ... </GameLocation>
m = re.search(r'<GameLocation xsi:type="Farm">(.*?)</GameLocation>', xml, re.S)
print("Farm 块找到:", bool(m), "len:", len(m.group(1)) if m else 0)
if m:
    farm = m.group(1)
    trees = re.findall(r'<TerrainFeature xsi:type="Tree">(.*?)</TerrainFeature>', farm, re.S)
    print("Farm Tree 特征数:", len(trees))
    st = sum(1 for b in trees if re.search(r"<stump>\s*(true|1)\s*</stump>", b))
    print("Farm stump=true:", st, "=> FarmScan 口径(trees) 应为:", len(trees)-st)
    ft = re.findall(r'<TerrainFeature xsi:type="FruitTree">', farm)
    gr = re.findall(r'<TerrainFeature xsi:type="Grass">', farm)
    hd = re.findall(r'<TerrainFeature xsi:type="HoeDirt">', farm)
    bs = re.findall(r'<TerrainFeature xsi:type="Bush">', farm)
    print("Farm FruitTree:", len(ft), "Grass:", len(gr), "HoeDirt:", len(hd), "Bush:", len(bs))
    gs = {}
    for b in trees:
        mm = re.search(r"<treeType>(\d+)</treeType>", b)
        g2 = re.search(r"<growthStage>(\d+)</growthStage>", b)
        k = (mm.group(1) if mm else "?", g2.group(1) if g2 else "?")
        gs[k] = gs.get(k,0)+1
    print("Farm Tree (treeType,growthStage) 分布前 12:", sorted(gs.items(), key=lambda kv:-kv[1])[:12])
    print("TreesChopped? ", re.search(r"<key><string>TreesChopped</string></key><value><unsignedInt>(\d+)</unsignedInt>", xml).group(1) if re.search(r"TreesChopped", xml) else "n/a")
