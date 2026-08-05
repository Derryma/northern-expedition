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

# Clip boxes: (min_lon, min_lat, max_lon, max_lat)
SUIYUAN_BOX = (106.0, 37.0, 113.2, 43.0)      # 綏遠：歸綏、包頭、河套、鄂爾多斯
CHAHAR_MENG_BOX = (112.0, 40.0, 118.5, 46.5)  # 察哈爾：錫林郭勒、烏蘭察布東部
CHAHAR_HEBEI_BOX = (113.0, 40.2, 116.7, 42.5)  # 察哈爾：張家口口北三廳
REHE_MENG_BOX = (116.5, 41.0, 122.5, 45.5)    # 熱河：昭烏達盟（赤峰）
REHE_HEBEI_BOX = (115.8, 40.2, 119.6, 42.7)   # 熱河：承德
# 熱河在奉天境內僅及朝陽、阜新；錦州仍屬奉天，故此處用折線而非矩形
REHE_LIAONING_RING = [
    [118.8, 40.6], [120.0, 40.6], [120.6, 41.4], [121.3, 41.8],
    [122.3, 42.2], [122.3, 43.0], [118.8, 43.0], [118.8, 40.6],
]
FENGTIAN_MENG_BOX = (119.0, 42.0, 126.0, 46.5)  # 奉天：哲里木盟（通遼、科爾沁）
HEILONGJIANG_MENG_BOX = (115.0, 46.0, 126.5, 54.0)  # 黑龍江：呼倫貝爾
ALXA_BOX = (96.0, 37.0, 106.0, 43.0)          # 甘肅：阿拉善、額濟納旗
# 吉林轄今黑龍江省東南部（濱江、雙城、依蘭、三姓、寧安）；龍江、訥河、璦琿仍屬黑龍江
JILIN_HLJ_RING = [
    [124.5, 43.0], [125.6, 44.5], [126.0, 46.2], [128.0, 47.6], [130.0, 48.6],
    [135.5, 48.6], [135.5, 43.0], [124.5, 43.0],
]
QINLIAN_BOX = (107.0, 20.0, 110.3, 22.6)      # 廣東：欽廉道（欽州、北海、防城）

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

    suiyuan = clip(inner_mongolia, SUIYUAN_BOX)
    chahar = unary_union([clip(inner_mongolia, CHAHAR_MENG_BOX), clip(hebei, CHAHAR_HEBEI_BOX)])
    chahar = chahar.difference(suiyuan)
    rehe = unary_union([
        clip(inner_mongolia, REHE_MENG_BOX),
        clip(hebei, REHE_HEBEI_BOX),
        liaoning.intersection(Polygon(REHE_LIAONING_RING)),
    ]).difference(chahar)

    zhili = unary_union([hebei, modern["北京市"], modern["天津市"]]).difference(
        unary_union([chahar, rehe])
    )

    fengtian = unary_union([liaoning, clip(inner_mongolia, FENGTIAN_MENG_BOX)]).difference(rehe)
    jilin = unary_union([
        modern["吉林省"],
        heilongjiang.intersection(Polygon(JILIN_HLJ_RING)),
    ])
    heilongjiang_1926 = unary_union([
        heilongjiang,
        clip(inner_mongolia, HEILONGJIANG_MENG_BOX),
    ]).difference(jilin)

    gansu = unary_union([
        modern["甘肃省"],
        modern["宁夏回族自治区"],
        modern["青海省"],
        clip(inner_mongolia, ALXA_BOX),
    ]).difference(suiyuan)

    sichuan_1926 = unary_union([sichuan, modern["重庆市"]])

    guangdong = unary_union([
        modern["广东省"],
        modern["海南省"],
        clip(guangxi, QINLIAN_BOX),
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

    playable = load_playable_area()
    clip_area = playable.buffer(CLIP_MARGIN_DEGREES)
    features = []
    for name, unit_type, _seat, geom in units:
        geom = geom.buffer(0)
        if geom.intersection(playable).area < MIN_PLAYABLE_AREA:
            print(f"  dropped {name}: outside the playable map")
            continue
        geom = geom.intersection(clip_area).buffer(0)
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
