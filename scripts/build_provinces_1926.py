#!/usr/bin/env python3
"""Derive June-1926 top-level administrative boundaries from modern province polygons.

Source: frontend/data/china_provinces.geojson (modern PRC provinces), clipped to the
playable silhouette that frontend/map.js defines (CHINA_PROPER + HAINAN). Anything the
game map does not cover -- 新疆, 西藏, 外蒙古, Korea, foreign territory -- is dropped.
Output: frontend/data/provinces_1926.geojson -- the only map the game reads.

The 1926 units are built by unioning modern provinces and clipping them with
longitude/latitude boxes where a 1926 unit cut across a modern one.  The clip boxes are
approximations of the historical limits, not surveyed boundaries; each is annotated below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from shapely.geometry import Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = REPO_ROOT / "frontend/data/china_provinces.geojson"
MAP_JS = REPO_ROOT / "frontend/map.js"
OUT = REPO_ROOT / "frontend/data/provinces_1926.geojson"
STRATEGIC_MAP = REPO_ROOT / "scenario/data/strategic_map.json"

# ---------------------------------------------------------------------------
# 1926 年的內部分界
#
# 凡是 1926 年的界線與現代省界、國界或海岸線重合之處，幾何直接沿用來源檔，
# 自然就是真實的曲線與複雜多邊形。真正需要自己畫的，只有「切進現代省內部」
# 的那幾條線。這些線以前是用經緯度矩形去切，矩形邊會在省內部留下筆直的切口。
#
# 現在改成兩種手法：
#   1. 內蒙古由四條由南到北的密集切線切成五塊（綏遠、察哈爾、熱河、奉天、
#      黑龍江）。四個切區逐層包含，靠相減得到各塊，因此彼此貼合、不留空隙。
#   2. 從河北、遼寧劃走的部分各用一個密集環處理，環的南界沿長城、東界沿山脈。
#
# 折線是依史料位置描的近似線，不是實測界線；每條都標了依據的地理標的。
# 為了讓切區確實蓋住資料範圍，每條切線都往西、往南延伸到資料以外。
# ---------------------------------------------------------------------------

FAR_W, FAR_E, FAR_S, FAR_N = 90.0, 140.0, 30.0, 60.0


def _zone_west_of(line):
    """切線以西（含以南）的整片區域，用來做逐層相減。"""
    return [[FAR_W, FAR_S]] + list(line) + [[FAR_W, FAR_N], [FAR_W, FAR_S]]


# 切線 A｜綏遠 / 察哈爾：沿大青山東麓north上，經集寧西側入錫林郭勒西緣。
CUT_SUIYUAN_CHAHAR = [
    [112.35, 30.0], [112.40, 38.0], [112.45, 39.2], [112.55, 40.0], [112.70, 40.6],
    [112.62, 41.2], [112.70, 41.9], [112.95, 42.6], [113.30, 43.3], [113.75, 44.0],
    [114.25, 44.6], [114.80, 45.1], [115.40, 45.6], [116.05, 46.1], [116.70, 46.6],
    [117.30, 47.1], [117.90, 60.0],
]

# 切線 B｜察哈爾 / 熱河：沿灤河上游與大興安嶺南段西麓，經多倫東側北上。
CUT_CHAHAR_REHE = [
    [116.20, 30.0], [116.25, 40.2], [116.45, 40.8], [116.75, 41.4], [117.15, 42.0],
    [117.60, 42.6], [118.05, 43.2], [118.45, 43.8], [118.80, 44.4], [119.15, 45.0],
    [119.55, 45.6], [120.00, 46.2], [120.50, 46.8], [121.05, 47.4], [121.60, 60.0],
]

# 切線 C｜熱河 / 奉天：沿努魯兒虎山脊向東北，錦州、義縣仍屬奉天。
CUT_REHE_FENGTIAN = [
    [118.90, 30.0], [119.00, 40.3], [119.45, 40.8], [119.95, 41.3], [120.45, 41.8],
    [120.95, 42.3], [121.40, 42.8], [121.85, 43.3], [122.25, 43.8], [122.60, 44.3],
    [122.90, 44.8], [123.20, 45.3], [123.50, 45.8], [123.85, 46.3], [124.20, 60.0],
]

# 切線 D｜奉天 / 黑龍江：哲里木盟北界，沿洮兒河與嫩江西岸。
CUT_FENGTIAN_HLJ = [
    [90.0, 45.35], [114.0, 45.40], [116.0, 45.45], [118.0, 45.50], [119.5, 45.55],
    [120.8, 45.60], [122.0, 45.70], [123.0, 45.85], [123.9, 46.05], [124.7, 46.25],
    [125.4, 46.40], [126.0, 46.50], [140.0, 46.55],
]


def zone_a():
    return _zone_west_of(CUT_SUIYUAN_CHAHAR)


def zone_b():
    return _zone_west_of(CUT_CHAHAR_REHE)


def zone_c():
    return _zone_west_of(CUT_REHE_FENGTIAN)


def zone_d():
    """奉天所轄蒙地：切線 D 以南的整片。"""
    return [[FAR_W, FAR_S]] + list(CUT_FENGTIAN_HLJ) + [[FAR_E, FAR_S], [FAR_W, FAR_S]]


# 察哈爾自河北劃入的口北三廳（張家口、宣化、萬全）。南界沿長城，其餘沿用來源檔。
CHAHAR_HEBEI_RING = [
    [113.7, 40.35], [114.1, 40.30], [114.5, 40.32], [114.9, 40.40], [115.3, 40.52],
    [115.6, 40.68], [115.9, 40.85], [116.2, 41.00], [116.4, 41.25], [116.4, 41.70],
    [116.2, 42.10], [115.8, 42.40], [115.3, 42.55], [114.7, 42.55], [114.1, 42.40],
    [113.7, 42.10], [113.5, 41.60], [113.5, 41.05], [113.6, 40.65], [113.7, 40.35],
]

# 熱河自河北劃入的承德一帶。南界沿長城（喜峰口—古北口—冷口），東抵山海關以北。
REHE_HEBEI_RING = [
    [116.30, 40.55], [116.70, 40.45], [117.10, 40.38], [117.50, 40.30], [117.90, 40.22],
    [118.30, 40.15], [118.70, 40.10], [119.10, 40.10], [119.50, 40.20], [119.80, 40.45],
    [119.90, 40.85], [119.85, 41.30], [119.60, 41.75], [119.20, 42.10], [118.70, 42.35],
    [118.10, 42.45], [117.50, 42.40], [116.95, 42.20], [116.55, 41.85], [116.35, 41.40],
    [116.28, 40.95], [116.30, 40.55],
]

# 熱河自奉天劃入的朝陽、阜新。東界沿努魯兒虎山，錦州仍屬奉天。
REHE_LIAONING_RING = [
    [118.90, 40.60], [119.30, 40.55], [119.70, 40.62], [120.05, 40.80], [120.35, 41.05],
    [120.60, 41.35], [120.90, 41.65], [121.25, 41.95], [121.60, 42.25], [121.90, 42.60],
    [122.10, 43.00], [122.05, 43.40], [121.75, 43.65], [121.30, 43.70], [120.80, 43.55],
    [120.30, 43.30], [119.85, 42.95], [119.45, 42.55], [119.15, 42.10], [118.95, 41.60],
    [118.88, 41.10], [118.90, 40.60],
]

# 奉天自現代吉林省劃入的洮南、白城一角。參考圖上洮南為奉天所轄（哲里木盟東緣），
# 東界約在長春以西，長春本身仍屬吉林。
TAONAN_RING = [
    [121.40, 44.10], [121.60, 44.70], [121.90, 45.20], [122.30, 45.65], [122.80, 46.00],
    [123.40, 46.20], [124.00, 46.20], [124.45, 45.95], [124.70, 45.50], [124.75, 45.00],
    [124.60, 44.55], [124.25, 44.25], [123.70, 44.08], [123.00, 44.00], [122.20, 44.02],
    [121.40, 44.10],
]

# 甘肅：阿拉善、額濟納旗。北界為中蒙國界，沿用來源檔；東界沿賀蘭山北延一線。
ALXA_RING = [
    [96.2, 37.4], [96.4, 39.0], [97.0, 40.4], [98.0, 41.4], [99.3, 42.2],
    [100.7, 42.6], [102.1, 42.6], [103.4, 42.3], [104.5, 41.8], [105.3, 41.0],
    [105.8, 40.1], [106.0, 39.2], [105.9, 38.3], [105.6, 37.6], [105.0, 37.1],
    [104.0, 36.9], [102.5, 36.9], [100.5, 37.0], [98.4, 37.1], [96.2, 37.4],
]

# 吉林轄今黑龍江省東南部（濱江、雙城、依蘭、三姓、寧安）；龍江、訥河、璦琿仍屬黑龍江。
# 分界沿拉林河、松花江南岸至三姓，再折向東南沿完達山脈。
JILIN_HLJ_RING = [
    [124.6, 43.1], [124.9, 43.9], [125.3, 44.6], [125.8, 45.3], [126.3, 45.9],
    [126.9, 46.4], [127.6, 46.8], [128.4, 47.1], [129.2, 47.4], [130.1, 47.7],
    [131.0, 47.9], [132.0, 48.1], [133.2, 48.2], [134.4, 48.3], [135.6, 48.4],
    [135.6, 43.1], [124.6, 43.1],
]

# 廣東：欽廉道（欽州、防城、靈山、合浦、北海）。1926 年仍屬廣東，1952 年才劃給廣西。
# 北界不是一條圓弧，而是帶轉折的折線，依序沿：
#   十萬大山北麓（上思留在廣西、防城與欽州留在廣東）→ 靈山、浦北以北的分水嶺
#   （北界最高只到 22.40°N）→ 博白以南折向東南 → 於廉江西側接回原有的兩廣界線。
# 折線兩端都往外延伸到資料範圍以外，與越南國界、北部灣海岸的交會由來源檔決定，
# 所以海岸線與國界仍是真實幾何，只有這條內陸分界是描的。
QINLIAN_RING = [
    [106.20, 21.85],
    [107.05, 21.92], [107.40, 21.98], [107.75, 22.02], [107.98, 22.05],
    [108.20, 22.12], [108.42, 22.20], [108.62, 22.26], [108.85, 22.32],
    [109.05, 22.36], [109.29, 22.40], [109.45, 22.40], [109.58, 22.37],
    [109.72, 22.32], [109.86, 22.26], [109.98, 22.18], [110.12, 22.08],
    [110.28, 21.98], [110.45, 21.90],
    [110.45, 19.40], [106.20, 19.40], [106.20, 21.85],
]

TYPE_PROVINCE = "省"
TYPE_SPECIAL_REGION = "特別區域"
TYPE_SPECIAL_ADMIN = "特別行政區"
TYPE_LOCALITY = "地方"
TYPE_TREATY_PORT = "商埠"


def load_playable_area():
    """The hex grid only exists inside this silhouette (see frontend/map.js)."""
    source = MAP_JS.read_text(encoding="utf-8")

    def ring(name: str):
        body = re.search(r"export const %s = \[(.*?)\n\];" % name, source, re.S).group(1)
        return [(float(a), float(b)) for a, b in re.findall(r"\[([\d.]+), ?([\d.]+)\]", body)]

    return Polygon(ring("CHINA_PROPER")).union(Polygon(ring("HAINAN"))).buffer(0)


# CHINA_PROPER is a coarse silhouette that cuts inside the real coastline in places, so the
# geometry is clipped to a slightly grown copy: membership is decided against the strict
# silhouette, but 青島, 溫州, 廈門, 泉州 and 汕頭 must not fall outside their own province.
CLIP_MARGIN_DEGREES = 0.35
MIN_PLAYABLE_AREA = 2.0


def load_modern() -> dict:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    out = {}
    for feature in data["features"]:
        name = feature["properties"].get("name")
        if not name:
            continue
        out[name] = shape(feature["geometry"]).buffer(0)
    return out


def build(modern: dict) -> list[dict]:
    def m(*names):
        return unary_union([modern[n] for n in names])

    def clip(geom, bounds):
        return geom.intersection(box(*bounds))

    def ring_clip(geom, ring):
        """以折線多邊形切割，切口才會是曲線而不是矩形邊。"""
        return geom.intersection(Polygon(ring).buffer(0))

    def cut(geom, *bounds_list):
        for bounds in bounds_list:
            geom = geom.difference(box(*bounds))
        return geom

    inner_mongolia = modern["内蒙古自治区"]
    hebei = modern["河北省"]
    liaoning = modern["辽宁省"]
    heilongjiang = modern["黑龙江省"]
    sichuan = modern["四川省"]
    guangxi = modern["广西壮族自治区"]
    shandong = modern["山东省"]

    # 內蒙古切成五塊：逐層相減，彼此貼合不留縫。
    # 呼倫貝爾（切線 D 以北）整片歸黑龍江，所以先把蒙地上蓋，
    # 綏遠、察哈爾、熱河、奉天只在上蓋以南分。
    mongol_south = ring_clip(inner_mongolia, zone_d())
    alxa = ring_clip(inner_mongolia, ALXA_RING)   # 阿拉善、額濟納旗歸甘肅
    mongol_south = mongol_south.difference(alxa)

    suiyuan = ring_clip(mongol_south, zone_a())
    chahar_meng = ring_clip(mongol_south, zone_b()).difference(suiyuan)
    chahar = unary_union([chahar_meng, ring_clip(hebei, CHAHAR_HEBEI_RING)])
    rehe_meng = ring_clip(mongol_south, zone_c()).difference(unary_union([suiyuan, chahar_meng]))
    rehe = unary_union([
        rehe_meng,
        ring_clip(hebei, REHE_HEBEI_RING),
        ring_clip(liaoning, REHE_LIAONING_RING),
    ]).difference(chahar)

    zhili = unary_union([hebei, modern["北京市"], modern["天津市"]]).difference(
        unary_union([chahar, rehe])
    )

    fengtian_meng = mongol_south.difference(unary_union([suiyuan, chahar_meng, rehe_meng]))
    # 洮南一角在現代吉林省境內，但參考圖上屬奉天，先切出來再從吉林扣除。
    taonan = ring_clip(modern["吉林省"], TAONAN_RING)
    fengtian = unary_union([liaoning, fengtian_meng, taonan]).difference(rehe)
    jilin = unary_union([
        modern["吉林省"],
        heilongjiang.intersection(Polygon(JILIN_HLJ_RING)),
    ]).difference(taonan)
    # 剩下的內蒙古（呼倫貝爾）全部歸黑龍江，五塊合起來完整覆蓋內蒙古，不留空隙。
    heilongjiang_meng = inner_mongolia.difference(
        unary_union([suiyuan, chahar_meng, rehe_meng, fengtian_meng, alxa])
    )
    heilongjiang_1926 = unary_union([heilongjiang, heilongjiang_meng]).difference(jilin)

    gansu = unary_union([
        modern["甘肃省"],
        modern["宁夏回族自治区"],
        modern["青海省"],
        alxa,
    ]).difference(suiyuan)

    sichuan_1926 = unary_union([sichuan, modern["重庆市"]])

    guangdong = unary_union([
        modern["广东省"],
        modern["海南省"],
        ring_clip(guangxi, QINLIAN_RING),
    ])
    guangxi_1926 = guangxi.difference(guangdong)

    shandong_1926 = shandong

    units = [
        ("直隸", TYPE_PROVINCE, "天津", zhili),
        ("奉天", TYPE_PROVINCE, "奉天", fengtian),
        ("吉林", TYPE_PROVINCE, "吉林", jilin),
        ("黑龍江", TYPE_PROVINCE, "龍江", heilongjiang_1926),
        ("山東", TYPE_PROVINCE, "濟南", shandong_1926),
        ("河南", TYPE_PROVINCE, "開封", modern["河南省"]),
        ("山西", TYPE_PROVINCE, "太原", modern["山西省"]),
        ("江蘇", TYPE_PROVINCE, "江寧", unary_union([modern["江苏省"], modern["上海市"]])),
        ("安徽", TYPE_PROVINCE, "安慶", modern["安徽省"]),
        ("江西", TYPE_PROVINCE, "南昌", modern["江西省"]),
        ("福建", TYPE_PROVINCE, "福州", modern["福建省"]),
        ("浙江", TYPE_PROVINCE, "杭縣", modern["浙江省"]),
        ("湖北", TYPE_PROVINCE, "武昌", modern["湖北省"]),
        ("湖南", TYPE_PROVINCE, "長沙", modern["湖南省"]),
        ("陝西", TYPE_PROVINCE, "長安", modern["陕西省"]),
        ("甘肅", TYPE_PROVINCE, "皋蘭", gansu),
        ("四川", TYPE_PROVINCE, "成都", sichuan_1926),
        ("廣東", TYPE_PROVINCE, "廣州", guangdong),
        ("廣西", TYPE_PROVINCE, "南寧", guangxi_1926),
        ("雲南", TYPE_PROVINCE, "昆明", modern["云南省"]),
        ("貴州", TYPE_PROVINCE, "貴陽", modern["贵州省"]),
        ("熱河", TYPE_PROVINCE, "承德", rehe),
        ("察哈爾", TYPE_PROVINCE, "張家口", chahar),
        ("綏遠", TYPE_PROVINCE, "歸綏", suiyuan),
    ]

    def drop_slivers(geom, min_share=0.02):
        """切割難免留下零碎的孤立小塊，一律丟掉，只保留成片的本體。

        用相對面積判斷而不是絕對值：海南島佔廣東約六分之一，必須留下；
        綏遠在阿拉善一帶留下的碎片不到本體的百分之一，該丟。
        """
        if geom.geom_type != "MultiPolygon":
            return geom
        total = geom.area
        parts = [g for g in geom.geoms if g.area >= total * min_share]
        if not parts:
            return max(geom.geoms, key=lambda g: g.area)
        return unary_union(parts)

    playable = load_playable_area()
    clip_area = playable.buffer(CLIP_MARGIN_DEGREES)
    features = []
    for name, unit_type, _seat, geom in units:
        geom = drop_slivers(geom.buffer(0))
        if geom.intersection(playable).area < MIN_PLAYABLE_AREA:
            print(f"  dropped {name}: outside the playable map")
            continue
        geom = drop_slivers(geom.intersection(clip_area).buffer(0))
        if geom.is_empty:
            print(f"  dropped {name}: empty after clipping")
            continue
        features.append({
            "type": "Feature",
            "properties": {"name": name, "type": unit_type},
            "geometry": mapping(geom),
        })

    return features



def sync_strategic_map(features: list[dict]) -> list[str]:
    """Keep strategic_map.json's unit index in step with the geojson, and report any city
    that no longer falls inside the unit it claims."""
    raw = STRATEGIC_MAP.read_text(encoding="utf-8")
    data = json.loads(raw)
    index = [
        {"name": f["properties"]["name"], "type": f["properties"]["type"]}
        for f in features
    ]
    shapes = [(f["properties"]["name"], shape(f["geometry"])) for f in features]
    problems = []
    for city in data["cities"]:
        point = Point(city["lon"], city["lat"])
        holder = next((n for n, g in shapes if g.contains(point)), None)
        if holder != city["province"]:
            problems.append(f"{city['name']} claims {city['province']} but sits in {holder}")

    def rows(items):
        return [
            "    " + json.dumps(x, ensure_ascii=False, separators=(",", ":")) + ("," if i < len(items) - 1 else "")
            for i, x in enumerate(items)
        ]

    lines = ["{", '  "version": "%s",' % data["version"], '  "cities": ['] + rows(data["cities"]) + [
        "  ],",
        '  "provinces_geojson": "frontend/data/provinces_1926.geojson",',
        '  "provinces": [',
    ] + rows(index) + ["  ],", '  "railroads": ['] + rows(data["railroads"]) + ["  ]", "}", ""]
    STRATEGIC_MAP.write_text("\n".join(lines), encoding="utf-8")
    return problems


def main() -> None:
    modern = load_modern()
    features = build(modern)

    OUT.write_text(
        json.dumps(
            {"version": "1926-06", "type": "FeatureCollection", "features": features},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


    problems = sync_strategic_map(features)
    print(f"{OUT.name}: {OUT.stat().st_size / 1024:.0f} KB, {len(features)} units")
    print(f"{STRATEGIC_MAP.name}: unit index synced")
    if problems:
        print("CITY/PROVINCE MISMATCHES:")
        for line in problems:
            print(f"  {line}")
    else:
        print("every city sits inside the unit it claims")
    for feature in features:
        print(f"  {feature['properties']['name']}")


if __name__ == "__main__":
    main()
