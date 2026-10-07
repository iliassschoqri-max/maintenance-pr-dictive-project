import urllib.request
import json
import base64

credentials = base64.b64encode(b"admin:admin").decode()
headers = {"Authorization": f"Basic {credentials}", "Content-Type": "application/json"}

# Check datasource
req = urllib.request.Request("http://127.0.0.1:3000/api/datasources", headers={"Authorization": f"Basic {credentials}"})
resp = urllib.request.urlopen(req)
ds_list = json.loads(resp.read())
for ds in ds_list:
    print(f"Datasource: ID={ds['id']} UID={ds['uid']} Name={ds['name']}")
    print(f"  secureJsonFields: {ds.get('secureJsonFields', {})}")
    print(f"  jsonData: {ds.get('jsonData', {})}")

# Test query
q = 'from(bucket: "sensors") |> range(start: -5m) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "health_score") |> last() |> group()'
data = json.dumps({
    "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"}, "query": q}],
    "from": "now-5m", "to": "now"
}).encode()
req2 = urllib.request.Request("http://127.0.0.1:3000/api/ds/query", data=data, headers=headers)
try:
    resp2 = urllib.request.urlopen(req2)
    frames = json.loads(resp2.read()).get("results", {}).get("A", {}).get("frames", [])
    print(f"\nQuery test: {len(frames)} frames returned")
    for f in frames[:5]:
        labels = f.get("schema", {}).get("fields", [{}])[0].get("labels", {})
        vals = f.get("data", {}).get("values", [[], []])
        print(f"  {labels.get('machine_id', '?')}: {vals[1][0] if len(vals) > 1 and vals[1] else 'EMPTY'}")
except urllib.error.HTTPError as e:
    print(f"\nQuery ERROR: {e.code} {e.read().decode()[:300]}")
