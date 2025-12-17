import requests
import time

BASE_URL = "https://services.gisqatar.org.qa/server/rest/services/Vector/GeonamesE/MapServer/0/query"

PARAMS = {
    "f": "json",
    "returnGeometry": "false",
    "spatialRel": "esriSpatialRelIntersects",
    "geometryType": "esriGeometryEnvelope",
    "inSR": 2932,
    "outSR": 2932,
    "outFields": "*",
    "where": "1=1",
    "resultRecordCount": 1000
}

GEOMETRY = {
    "xmin": 150000,
    "ymin": 300000,
    "xmax": 320000,
    "ymax": 500000,
    "spatialReference": {"wkid": 2932}
}

all_features = []
offset = 0

while True:
    PARAMS["geometry"] = GEOMETRY
    PARAMS["resultOffset"] = offset

    resp = requests.get(BASE_URL, params=PARAMS, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    features = data.get("features", [])
    if not features:
        break

    all_features.extend(features)
    offset += len(features)

    print(f"Fetched {len(features)} features (total: {len(all_features)})")
    time.sleep(0.2)

print("\n=== DEBUG: FIRST FEATURE ATTRIBUTES KEYS ===")

if not all_features:
    print("NO FEATURES — THIS WOULD BE A HARD FAILURE")
else:
    attrs = all_features[0].get("attributes", {})
    print("Attribute keys:")
    for k in attrs.keys():
        print("-", k)

    print("\nSample values:")
    for k, v in list(attrs.items())[:20]:
        print(k, "=", v)

print("\n=== DELIVERY-RELEVANT AREAS ===")

seen = set()
count = 0

for f in all_features:
    a = f.get("attributes", {})

    geo_en = a.get("GEO_NAME_E")
    geo_ar = a.get("GEO_NAME_A")
    geo_code = a.get("GEO_CODE")

    mun_en = a.get("MUN_NAME_E")
    mun_ar = a.get("MUN_NAME_A")

    # HARD FILTER: ignore tiny/local feature names
    if not geo_en or not geo_code:
        continue

    key = (geo_code, geo_en)
    if key in seen:
        continue

    seen.add(key)

    print(
        geo_code,
        "|",
        geo_en,
        "|",
        geo_ar,
        "|",
        mun_en
    )

    count += 1
    if count >= 50:
        break
