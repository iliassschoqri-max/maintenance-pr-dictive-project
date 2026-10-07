import json, subprocess

panels = {
    "01_OV - Health Score per Machine": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "health_score") |> aggregateWindow(every: 2m, fn: mean) |> yield(name: "health")',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "01_OV - Sensor Temperature": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "sensor_reading") |> filter(fn: (r) => r._field == "temperature_bearing") |> aggregateWindow(every: 2m, fn: mean) |> yield(name: "temp")',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "01_OV - Status Count": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "status") |> group(columns: ["_value"]) |> count()',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "02_DT - Single Machine HS": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "health_score") |> filter(fn: (r) => r.machine_id == "INJ-01") |> aggregateWindow(every: 1m, fn: mean)',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "03_AN - Evolution HS (7d)": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "health_score") |> aggregateWindow(every: 2m, fn: mean)',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "03_AN - Anomalies Bar": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "anomalies") |> filter(fn: (r) => r._field == "capteur") |> map(fn: (r) => ({r with _cnt: 1.0})) |> drop(columns: ["_value", "_field", "severity", "status"]) |> rename(columns: {_cnt: "_value"}) |> aggregateWindow(every: 10m, fn: sum, createEmpty: false)',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "03_AN - Anomalies Pie Machine": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "anomalies") |> filter(fn: (r) => r._field == "capteur") |> map(fn: (r) => ({ r with _cnt: 1.0})) |> drop(columns: ["_value", "_field", "severity", "status"]) |> group(columns: ["machine_id"]) |> sum(column: "_cnt") |> rename(columns: {_cnt: "_value"})',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    },
    "03_AN - Dispo BarGauge": {
        "queries": [{"refId": "A", "datasource": {"type": "influxdb", "uid": "P8BA1E8C46CE71D7F"},
            "query": 'from(bucket: "sensors") |> range(start: 2026-07-20T10:00:00Z, stop: 2026-07-20T11:00:00Z) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r._field == "health_score") |> mean() |> group() |> map(fn: (r) => ({ r with _value: float(v: r._value) }))',
            "rawQuery": True}],
        "from": "2026-07-20T10:00:00Z", "to": "2026-07-20T11:00:00Z"
    }
}

print("=" * 70)
print("DASHBOARD PANEL TEST (10:00 - 11:00)")
print("=" * 70)

for name, payload in panels.items():
    body = json.dumps(payload)
    result = subprocess.run(
        ["curl", "-s", "-X", "POST", "-u", "admin:admin", "-H", "Content-Type: application/json",
         "-d", body, "http://localhost:3000/api/ds/query"],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        status = data["results"]["A"]["status"]
        frames = data["results"]["A"].get("frames", [])
        if frames:
            n_rows = len(frames[0]["data"]["values"][0]) if frames[0]["data"]["values"] else 0
            n_series = len(frames)
            print(f"  OK  {name}: {n_series} series, {n_rows} rows")
        else:
            print(f"  NO DATA  {name}: no frames returned")
    except Exception as e:
        print(f"  ERROR  {name}: {e}")

print("=" * 70)
