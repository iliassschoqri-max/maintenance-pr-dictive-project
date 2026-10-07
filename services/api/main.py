import os
import uuid
from datetime import datetime, timezone

import pandas as pd

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from influxdb_client import InfluxDBClient
from pydantic import BaseModel

from ml_models.anomaly_detection.predict import AnomalyPredictor
from ml_models.health_score import HealthScoreCalculator
from ml_models.predictive_maintenance.predict import RULPredictor
from storage.delta_writer import DeltaLakeManager

from fastapi.responses import StreamingResponse
from fpdf import FPDF
import csv
import io

delta_mgr = DeltaLakeManager()

app = FastAPI(title="PFA Orhan - API Maintenance Predictive")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

INFLUXDB_URL = os.getenv("INFLUXDB_URL", "http://localhost:8086")
INFLUXDB_TOKEN = os.getenv("INFLUXDB_TOKEN", "admin123admin123admin123admin123ad==")
INFLUXDB_ORG = os.getenv("INFLUXDB_ORG", "orhan")
INFLUXDB_BUCKET = os.getenv("INFLUXDB_BUCKET", "sensors")

try:
    influx = InfluxDBClient(url=INFLUXDB_URL, token=INFLUXDB_TOKEN, org=INFLUXDB_ORG)
    query_api = influx.query_api()
    write_api = influx.write_api()
except Exception:
    influx = None
    query_api = None
    write_api = None

try:
    anomaly_predictor = AnomalyPredictor()
except Exception:
    anomaly_predictor = None

try:
    rul_predictor = RULPredictor()
except Exception:
    rul_predictor = None

health_calc = HealthScoreCalculator()

MACHINES = {
    "INJ-01": {"type": "injection_plastique", "label": "Presse injection 1"},
    "INJ-02": {"type": "injection_plastique", "label": "Presse injection 2"},
    "SOUD-01": {"type": "soudure", "label": "Poste soudure"},
    "ASSY-01": {"type": "assemblage", "label": "Ligne assemblage"},
    "PEINT-01": {"type": "peinture", "label": "Cabine peinture"},
    "FRAIS-01": {"type": "fraisage_cnc", "label": "Centre de fraisage CNC"},
    "TOUR-01": {"type": "tour_cnc", "label": "Tour CNC"},
}
MACHINE_IDS = list(MACHINES.keys())

SENSORS = [
    "temperature_bearing", "temperature_motor", "temperature_hydraulic",
    "temperature_ambient", "vibration_axial", "vibration_radial",
    "vibration_vertical", "pressure_hydraulic", "pressure_pneumatic",
    "pressure_lubrication", "current_motor", "current_servo",
    "rpm_spindle", "rpm_fan", "torque_output", "power_consumption",
    "acoustic_emission", "oil_particle_count", "coolant_flow",
    "electrical_resistance", "displacement_linear",
]


def influx_health_score(machine_id):
    try:
        q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r.machine_id == "{machine_id}") |> last()'
        tables = query_api.query(q)
        data = {}
        for t in tables:
            for r in t.records:
                data[r.get_field()] = r.get_value()
        return data
    except Exception:
        return {}


def influx_alerts(status=None):
    try:
        status_filter = f'|> filter(fn: (r) => r.status == "{status}")' if status else ""
        q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -30d) |> filter(fn: (r) => r._measurement == "anomalies") {status_filter} |> sort(columns: ["_time"], desc: true)'
        tables = query_api.query(q)
        rows = {}
        for t in tables:
            for r in t.records:
                aid = r.values.get("alert_id", r.get_time().isoformat())
                if aid not in rows:
                    rows[aid] = {
                        "alert_id": aid,
                        "machine_id": r.values.get("machine_id", ""),
                        "timestamp": r.get_time().isoformat(),
                        "severity": r.values.get("severity", "low"),
                        "status": r.values.get("status", "active"),
                        "capteur": "",
                        "anomaly_score": 0,
                        "comment": "",
                    }
                field = r.get_field()
                if field == "capteur":
                    rows[aid]["capteur"] = r.get_value()
                elif field == "anomaly_score":
                    rows[aid]["anomaly_score"] = r.get_value()
                elif field == "comment":
                    rows[aid]["comment"] = r.get_value()
        return list(rows.values())
    except Exception:
        return []


# ── Endpoints ──────────────────────────────────────────

@app.get("/machines")
def list_machines():
    results = []
    for mid in MACHINE_IDS:
        hs = influx_health_score(mid)
        health = hs.get("health_score", 50)
        rul = hs.get("rul_days", 0)

        if not rul or rul <= 0:
            try:
                q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r.machine_id == "{mid}") |> filter(fn: (r) => r._field == "anomaly_score") |> mean()'
                tables = query_api.query(q)
                for t in tables:
                    for r in t.records:
                        avg_anomaly = r.get_value()
                        rul = max(10, round(150 * (1 - min(abs(avg_anomaly) / 5, 1)), 1))
            except Exception:
                rul = 150.0

        if health >= 70:
            status = "normal"
        elif health >= 30:
            status = "warning"
        else:
            status = "critical"
        results.append({
            "machine_id": mid,
            "machine_type": MACHINES[mid]["type"],
            "label": MACHINES[mid]["label"],
            "health_score": round(health, 1),
            "rul_days": round(rul, 1),
            "status": status,
        })
    return {"machines": results}


@app.get("/alerts")
def get_alerts(status: str = Query("active", pattern="^(active|resolved|false_positive|all)$")):
    s = None if status == "all" else status
    alerts = influx_alerts(s)
    return {"alerts": alerts, "count": len(alerts)}


@app.get("/machine/{machine_id}/health")
def get_health(machine_id: str):
    if machine_id not in MACHINE_IDS:
        raise HTTPException(404, f"Machine {machine_id} inconnue")

    hs = influx_health_score(machine_id)

    anomaly_score = hs.get("anomaly_score", -5.0)
    rul_pred = hs.get("rul_days", 150.0)

    if anomaly_predictor and not hs:
        try:
            result = anomaly_predictor.predict({"temperature_bearing": 65, "vibration_axial": 0.03, "pressure_hydraulic": 5, "current_motor": 12})
            anomaly_score = result["anomaly_score"]
        except Exception:
            pass

    if (not rul_pred or rul_pred <= 0) and rul_predictor:
        try:
            q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "health_score") |> filter(fn: (r) => r.machine_id == "{machine_id}") |> filter(fn: (r) => r._field == "anomaly_score") |> mean()'
            tables = query_api.query(q)
            for t in tables:
                for r in t.records:
                    avg_anomaly = r.get_value()
                    rul_pred = max(10, round(150 * (1 - min(abs(avg_anomaly) / 5, 1)), 1))
        except Exception:
            rul_pred = 150.0

    health = health_calc.compute(anomaly_score, rul_pred)

    last_values = {}
    try:
        q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "sensors_raw") |> filter(fn: (r) => r.machine_id == "{machine_id}") |> last()'
        tables = query_api.query(q)
        for t in tables:
            for r in t.records:
                if r.get_field() in SENSORS:
                    last_values[r.get_field()] = r.get_value()
    except Exception:
        pass

    return {
        "machine_id": machine_id,
        "machine_type": MACHINES[machine_id]["type"],
        "label": MACHINES[machine_id]["label"],
        **health,
        "anomaly_score": round(anomaly_score, 4),
        "rul_days": round(rul_pred, 1),
        "last_values": last_values,
    }


@app.get("/machine/{machine_id}/history")
def get_history(machine_id: str, hours: int = Query(24, ge=1, le=168)):
    if machine_id not in MACHINE_IDS:
        raise HTTPException(404, f"Machine {machine_id} inconnue")
    try:
        q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -{hours}h) |> filter(fn: (r) => r._measurement == "sensors_raw") |> filter(fn: (r) => r.machine_id == "{machine_id}") |> pivot(rowKey: ["_time"], columnKey: ["_field"], valueColumn: "_value")'
        tables = query_api.query(q)
        results = []
        for t in tables:
            for r in t.records:
                row = {"time": r.get_time().isoformat()}
                for s in SENSORS:
                    row[s] = r.values.get(s)
                results.append(row)
        return {"machine_id": machine_id, "records": results, "count": len(results)}
    except Exception:
        return {"machine_id": machine_id, "records": [], "count": 0, "note": "InfluxDB indisponible"}


class AlertFeedbackPayload(BaseModel):
    decision: str
    comment: str = ""


@app.post("/alerts/{alert_id}/feedback")
def post_alert_feedback(alert_id: str, payload: AlertFeedbackPayload):
    if payload.decision not in ("confirmed", "false_positive"):
        raise HTTPException(400, "decision must be 'confirmed' or 'false_positive'")

    new_status = "resolved" if payload.decision == "confirmed" else "false_positive"

    # Update in InfluxDB
    try:
        from influxdb_client import Point
        from influxdb_client.client.write_api import SYNCHRONOUS
        wp = write_api if write_api else influx.write_api(write_options=SYNCHRONOUS)
        pt = (Point("anomalies")
              .tag("machine_id", alert_id.rsplit("-", 1)[0] if "-" in alert_id else "unknown")
              .tag("severity", "info")
              .tag("status", new_status)
              .field("alert_id", alert_id)
              .field("comment", payload.comment)
              .time(datetime.now(timezone.utc)))
        wp.write(bucket=INFLUXDB_BUCKET, record=pt)
    except Exception:
        pass

    # Also save to CSV for Airflow retraining
    feedback_path = os.path.join(os.path.dirname(__file__), "..", "data", "feedback.csv")
    os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
    with open(feedback_path, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()},{alert_id},{payload.decision},{payload.comment}\n")

    # Write to Delta Lake
    try:
        from datetime import datetime as dt_delta
        delta_mgr.write_feedback({
            "alert_id": alert_id,
            "machine_id": alert_id.rsplit("-", 1)[0] if "-" in alert_id else "unknown",
            "decision": payload.decision,
            "comment": payload.comment,
            "timestamp": pd.Timestamp(dt_delta.now(timezone.utc)),
            "original_severity": "",
            "original_score": 0.0,
        })
    except Exception:
        pass

    return {
        "status": "ok",
        "alert_id": alert_id,
        "new_status": new_status,
        "message": "Decision enregistree",
    }


class MachineFeedbackPayload(BaseModel):
    machine_id: str
    is_anomaly: bool
    comment: str = ""


@app.post("/machine/{machine_id}/feedback")
def post_machine_feedback(machine_id: str, payload: MachineFeedbackPayload):
    if machine_id not in MACHINE_IDS:
        raise HTTPException(404, f"Machine {machine_id} inconnue")
    feedback_path = os.path.join(os.path.dirname(__file__), "..", "data", "feedback.csv")
    os.makedirs(os.path.dirname(feedback_path), exist_ok=True)
    with open(feedback_path, "a") as f:
        f.write(f"{datetime.now(timezone.utc).isoformat()},{machine_id},{payload.is_anomaly},{payload.comment}\n")
    try:
        from datetime import datetime as dt_delta
        delta_mgr.write_feedback({
            "alert_id": f"{machine_id}-manual",
            "machine_id": machine_id,
            "decision": "confirmed" if payload.is_anomaly else "false_positive",
            "comment": payload.comment,
            "timestamp": pd.Timestamp(dt_delta.now(timezone.utc)),
            "original_severity": "manual",
            "original_score": 0.0,
        })
    except Exception:
        pass
    return {"status": "ok", "message": "Feedback enregistre"}


@app.get("/stats/model-performance")
def model_performance():
    alerts = influx_alerts("resolved") + influx_alerts("false_positive")
    total = len(alerts)
    fp_count = sum(1 for a in alerts if a["status"] == "false_positive")
    fp_rate = round(fp_count / total * 100, 1) if total > 0 else 0

    # Weekly breakdown
    from collections import defaultdict
    weeks = defaultdict(lambda: {"total": 0, "false_positive": 0})
    for a in alerts:
        ts = a["timestamp"][:7]
        weeks[ts]["total"] += 1
        if a["status"] == "false_positive":
            weeks[ts]["false_positive"] += 1

    weekly = [
        {"week": w, "total": d["total"], "false_positive": d["false_positive"],
         "fp_rate": round(d["false_positive"] / d["total"] * 100, 1) if d["total"] > 0 else 0}
        for w, d in sorted(weeks.items())
    ]

    return {
        "total_validations": total,
        "false_positive_count": fp_count,
        "false_positive_rate": fp_rate,
        "weekly": weekly,
    }


def compute_sensor_stats():
    try:
        q = f'from(bucket: "{INFLUXDB_BUCKET}") |> range(start: -24h) |> filter(fn: (r) => r._measurement == "sensors_raw") |> mean()'
        tables = query_api.query(q)
        avgs = {}
        for t in tables:
            for r in t.records:
                avgs[r.get_field()] = round(r.get_value(), 2)
        return avgs
    except Exception:
        return {}

def compute_alert_breakdown():
    alerts = influx_alerts("all")
    breakdown = {"high": 0, "medium": 0, "low": 0}
    for a in alerts:
        sev = a.get("severity", "low")
        breakdown[sev] = breakdown.get(sev, 0) + 1
    breakdown["total"] = len(alerts)
    breakdown["resolved"] = sum(1 for a in alerts if a.get("status") == "resolved")
    breakdown["false_positive"] = sum(1 for a in alerts if a.get("status") == "false_positive")
    breakdown["active"] = sum(1 for a in alerts if a.get("status") == "active")
    return breakdown


# ── Reports ────────────────────────────────────────────

@app.get("/report/csv")
def report_csv(type: str = Query("summary", pattern="^(summary|alerts|machines|anomalies)$")):
    buf = io.StringIO()
    w = csv.writer(buf)

    if type == "alerts":
        alerts = influx_alerts("all")
        w.writerow(["alert_id", "machine_id", "capteur", "anomaly_score", "severity", "status", "timestamp", "comment"])
        for a in alerts:
            w.writerow([a.get("alert_id"), a.get("machine_id"), a.get("capteur"), a.get("anomaly_score"), a.get("severity"), a.get("status"), a.get("timestamp"), a.get("comment")])
    elif type == "machines":
        machines = list_machines()["machines"]
        w.writerow(["machine_id", "machine_type", "label", "health_score", "rul_days", "status"])
        for m in machines:
            w.writerow([m["machine_id"], m["machine_type"], m["label"], m["health_score"], m["rul_days"], m["status"]])
    elif type == "anomalies":
        alerts = influx_alerts("all")
        anomalies = [a for a in alerts if a.get("severity") in ("high", "medium")]
        w.writerow(["alert_id", "machine_id", "capteur", "anomaly_score", "severity", "timestamp"])
        for a in anomalies:
            w.writerow([a.get("alert_id"), a.get("machine_id"), a.get("capteur"), a.get("anomaly_score"), a.get("severity"), a.get("timestamp")])
    else:
        machines = list_machines()["machines"]
        stats = model_performance()
        sensor_avgs = compute_sensor_stats()
        alert_brk = compute_alert_breakdown()

        w.writerow(["Rapport Resume - Orhan Automotive"])
        w.writerow([])
        w.writerow(["--- Parc machines ---"])
        w.writerow(["Machines totales", len(machines)])
        w.writerow(["Health Score moyen", round(sum(m.get("health_score", 0) for m in machines) / len(machines), 1) if machines else 0])
        w.writerow(["RUL moyen (jours)", round(sum(m.get("rul_days", 0) for m in machines) / len(machines), 1) if machines else 0])
        w.writerow(["Machines critiques", sum(1 for m in machines if m.get("status") == "critical")])
        w.writerow(["Machines warning", sum(1 for m in machines if m.get("status") == "warning")])
        w.writerow(["Machines normales", sum(1 for m in machines if m.get("status") == "normal")])
        w.writerow([])
        w.writerow(["--- Alertes ---"])
        w.writerow(["Alertes totales (30j)", alert_brk.get("total", 0)])
        w.writerow(["Alertes actives", alert_brk.get("active", 0)])
        w.writerow(["Alertes resolues", alert_brk.get("resolved", 0)])
        w.writerow(["Faux positifs", alert_brk.get("false_positive", 0)])
        w.writerow(["Taux FP (%)", stats.get("false_positive_rate", 0)])
        w.writerow(["Haute severite", alert_brk.get("high", 0)])
        w.writerow(["Severite moyenne", alert_brk.get("medium", 0)])
        w.writerow(["Faible severite", alert_brk.get("low", 0)])
        w.writerow([])
        w.writerow(["--- Capteurs (moyennes 24h) ---"])
        for s in SENSORS:
            w.writerow([f"Moyenne {s}", sensor_avgs.get(s, "N/A")])
        w.writerow([])
        w.writerow(["--- Detail par machine ---"])
        w.writerow(["Machine", "Type", "Health Score", "RUL (j)", "Statut"])
        for m in machines:
            w.writerow([m["machine_id"], m["machine_type"], m["health_score"], m["rul_days"], m["status"]])

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rapport_{type}.csv"},
    )


@app.get("/report/pdf")
def report_pdf(type: str = Query("summary", pattern="^(complet|summary)$")):
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 16)
    pdf.cell(0, 12, "Orhan Automotive - Rapport", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.set_font("Helvetica", "", 9)
    pdf.cell(0, 7, f"Genere le {datetime.now().strftime('%d/%m/%Y %H:%M')}", new_x="LMARGIN", new_y="NEXT", align="C")
    pdf.ln(5)

    machines = list_machines()["machines"]
    stats = model_performance()

    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, "Resume des machines", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)

    headers = ["Machine", "Type", "Score", "RUL", "Statut"]
    col_w = [30, 35, 25, 25, 35]
    for h, w in zip(headers, col_w):
        pdf.cell(w, 8, h, border=1)
    pdf.ln()

    for m in machines:
        vals = [m["machine_id"], m["machine_type"], str(m["health_score"]), str(m["rul_days"]), m["status"]]
        for v, w in zip(vals, col_w):
            pdf.cell(w, 7, v, border=1)
        pdf.ln()

    sensor_avgs = compute_sensor_stats()
    alert_brk = compute_alert_breakdown()

    pdf.ln(5)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, "Statistiques du parc", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    rows = [
        ("Machines totales", str(len(machines))),
        ("Health Score moyen", f"{round(sum(m.get('health_score', 0) for m in machines) / len(machines), 1) if machines else 0}%"),
        ("RUL moyen", f"{round(sum(m.get('rul_days', 0) for m in machines) / len(machines), 1) if machines else 0} jours"),
        ("Machines critiques", str(sum(1 for m in machines if m.get('status') == 'critical'))),
        ("Machines warning", str(sum(1 for m in machines if m.get('status') == 'warning'))),
    ]
    for label, val in rows:
        pdf.cell(55, 7, label, border=1)
        pdf.cell(0, 7, val, border=1)
        pdf.ln()

    pdf.ln(3)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 9, "Statistiques des alertes (30j)", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 9)
    rows = [
        ("Alertes totales", str(alert_brk.get("total", 0))),
        ("Actives", str(alert_brk.get("active", 0))),
        ("Resolues", str(alert_brk.get("resolved", 0))),
        ("Faux positifs", str(alert_brk.get("false_positive", 0))),
        ("Taux FP", f"{stats.get('false_positive_rate', 0)}%"),
        ("Haute severite", str(alert_brk.get("high", 0))),
        ("Severite moyenne", str(alert_brk.get("medium", 0))),
    ]
    for label, val in rows:
        pdf.cell(55, 7, label, border=1)
        pdf.cell(0, 7, val, border=1)
        pdf.ln()

    if sensor_avgs:
        pdf.ln(3)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 9, "Moyennes capteurs (24h)", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        units = {
            "temperature_bearing": "°C", "temperature_motor": "°C",
            "temperature_hydraulic": "°C", "temperature_ambient": "°C",
            "vibration_axial": "mm/s", "vibration_radial": "mm/s",
            "vibration_vertical": "mm/s", "pressure_hydraulic": "bar",
            "pressure_pneumatic": "bar", "pressure_lubrication": "bar",
            "current_motor": "A", "current_servo": "A",
            "rpm_spindle": "rpm", "rpm_fan": "rpm",
            "torque_output": "Nm", "power_consumption": "kW",
            "acoustic_emission": "dB", "oil_particle_count": "count/mL",
            "coolant_flow": "L/min", "electrical_resistance": "ohm",
            "displacement_linear": "mm",
        }
        for s in SENSORS:
            v = sensor_avgs.get(s, "N/A")
            u = units.get(s, "")
            pdf.cell(55, 7, s, border=1)
            pdf.cell(0, 7, f"{v} {u}", border=1)
            pdf.ln()

    if type == "complet":
        alerts = influx_alerts("all")
        if alerts:
            pdf.ln(5)
            pdf.set_font("Helvetica", "B", 11)
            pdf.cell(0, 9, "Dernieres alertes", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 8)
            cols = ["Machine", "Score", "Severite", "Statut"]
            cw = [30, 25, 30, 30]
            for h, w in zip(cols, cw):
                pdf.cell(w, 7, h, border=1)
            pdf.ln()
            for a in alerts[:20]:
                vals = [a.get("machine_id", ""), str(a.get("anomaly_score", 0)), a.get("severity", ""), a.get("status", "")]
                for v, w in zip(vals, cw):
                    pdf.cell(w, 6, v, border=1)
                pdf.ln()

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=rapport_{type}.pdf"},
    )


@app.get("/delta/stats")
def delta_stats():
    return {
        "sensors": delta_mgr.get_table_stats("sensors"),
        "feedback": delta_mgr.get_table_stats("feedback"),
    }


@app.get("/delta/sensors")
def delta_sensors(machine_id: str = "", limit: int = 100):
    df = delta_mgr.read_sensors(
        machine_id=machine_id if machine_id else None,
        limit=limit,
    )
    if df.empty:
        return {"records": [], "count": 0}
    return {"records": df.to_dict(orient="records"), "count": len(df)}


@app.get("/delta/feedback")
def delta_feedback(machine_id: str = "", limit: int = 100):
    df = delta_mgr.read_feedback(
        machine_id=machine_id if machine_id else None,
        limit=limit,
    )
    if df.empty:
        return {"records": [], "count": 0}
    return {"records": df.to_dict(orient="records"), "count": len(df)}
