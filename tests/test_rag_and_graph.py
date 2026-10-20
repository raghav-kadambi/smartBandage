"""Automated verification suite for RAG, Knowledge Graph, prediction and ESP32 features."""

import json
import unittest
from pathlib import Path

from app import app
import database as db
from data.literature_data import PAPERS, PAPER_ANNOTATIONS

ROOT = Path(__file__).resolve().parent.parent
REMOVED_SENSORS = ("pH", "exudate", "oxygen_saturation", "spo2")


class TestRAGAndKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Test User"

    def test_knowledge_graph_page_accessible(self):
        resp = self.client.get("/knowledge-graph")
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Clinical Knowledge Graph", resp.data)
        self.assertIn(b"vis-network", resp.data)

    def test_knowledge_graph_data_api(self):
        resp = self.client.get("/api/graph/data")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["stats"]["papers"], len(PAPER_ANNOTATIONS))
        self.assertEqual(data["stats"]["biomarkers"], 4)
        sensor_ids = {n["data"]["short_name"] for n in data["elements"]["nodes"] if n["data"]["type"] == "biomarker"}
        self.assertEqual(sensor_ids, {"temperature", "humidity", "heart_rate", "blood_pressure"})

    def test_knowledge_graph_node_detail_api(self):
        resp = self.client.get("/api/graph/node/paper_fierheller_2010")
        self.assertEqual(resp.status_code, 200)
        paper = resp.get_json()["node"]
        self.assertEqual(paper["type"], "paper")
        self.assertIn("Fierheller", paper["authors"])
        self.assertEqual(paper["pmid"], "20631603")

        resp_bio = self.client.get("/api/graph/node/biomarker_heart_rate")
        self.assertEqual(resp_bio.status_code, 200)
        self.assertIn("healthy_range", resp_bio.get_json()["node"])
        self.assertEqual(self.client.get("/api/graph/node/biomarker_pH").status_code, 404)

    def test_corpus_is_verifiable_pubmed_records(self):
        corpus = json.loads((ROOT / "data" / "literature_corpus.json").read_text(encoding="utf-8"))
        for paper in PAPERS:
            rec = corpus[paper["pmid"]]
            self.assertEqual(paper["title"], rec["title"])          # metadata comes from PubMed, not typed
            self.assertTrue(rec["pubmed_url"].endswith(f"/{paper['pmid']}/"))
            for sensor in paper["biomarkers"]:
                self.assertIn(sensor, ("temperature", "humidity", "heart_rate", "blood_pressure"))

    def test_rag_semantic_search_api(self):
        resp = self.client.get("/api/rag/search?q=skin+temperature+monitoring+infection&limit=3")
        self.assertEqual(resp.status_code, 200)
        results = resp.get_json()["results"]
        self.assertGreaterEqual(len(results), 1)
        self.assertTrue(any("temperature" in r["title"].lower() for r in results))
        self.assertTrue(all(r["pubmed_url"].startswith("https://pubmed.ncbi.nlm.nih.gov/") for r in results))

    def test_rag_chat_context_injection(self):
        from rag_service import rag_service
        sensor_ctx = {"temperature": 38.9, "humidity": 90.0, "heart_rate": 112, "systolic_bp": 96, "diastolic_bp": 58}
        res = rag_service.build_rag_context_for_chat(
            "Do my readings mean the infection is spreading?", sensor_readings=sensor_ctx, limit=3
        )
        self.assertGreaterEqual(len(res["citations"]), 1)
        self.assertIn("Findings:", res["prompt_text"])
        self.assertIn("PMID", res["prompt_text"])
        self.assertTrue(all(c["pmid"] for c in res["citations"]))


class TestPredictionAndDevice(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with self.client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Test User"

    def test_predict_with_new_sensors(self):
        resp = self.client.post("/api/predict", json={
            "temperature": 38.7, "humidity": 89, "heart_rate": 112, "systolic_bp": 100, "diastolic_bp": 60,
        })
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["condition"], "infected")
        self.assertEqual(set(data["features"]), {"temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"})

    def test_predict_rejects_old_ph_payload_and_bad_values(self):
        old = self.client.post("/api/predict", json={"pH": 7.2, "temperature": 36.8, "humidity": 50})
        self.assertEqual(old.status_code, 400)
        bad = self.client.post("/api/predict", json={
            "temperature": 36.8, "humidity": 50, "heart_rate": 70, "systolic_bp": 80, "diastolic_bp": 90,
        })
        self.assertEqual(bad.status_code, 400)

    def test_dashboard_requires_mode_choice(self):
        resp = self.client.get("/dashboard")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/choose-mode", resp.headers["Location"])
        self.assertEqual(self.client.post("/api/mode", json={"mode": "esp32"}).status_code, 200)
        page = self.client.get("/dashboard")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b"ESP32 bandage", page.data)
        self.client.post("/api/mode", json={"mode": "simulate"})
        self.assertIn(b"Sensor inputs (simulated)", self.client.get("/dashboard").data)

    def test_esp32_device_reading_flow(self):
        status = self.client.get("/api/device/status").get_json()
        token = status["token"]
        self.assertTrue(status["endpoint"].endswith("/api/device/reading"))

        device = app.test_client()  # no browser session, like the ESP32
        payload = {"temperature": 36.9, "humidity": 74, "heart_rate": 79, "systolic_bp": 121, "diastolic_bp": 78}
        self.assertEqual(device.post("/api/device/reading", json=payload).status_code, 401)
        self.assertEqual(device.post("/api/device/reading", json=payload, headers={"X-Device-Token": "nope"}).status_code, 401)
        ok = device.post("/api/device/reading", json=payload, headers={"X-Device-Token": token})
        self.assertEqual(ok.status_code, 200)
        self.assertIn(ok.get_json()["condition"], {"healthy", "wound_healing", "infected"})

        after = self.client.get("/api/device/status").get_json()
        self.assertIsNotNone(after["last_seen"])
        self.assertEqual(after["latest"]["source"], "esp32")
        self.assertIn("class_probs", after["latest"])

    def test_templates_have_no_removed_sensors(self):
        for name in ("dashboard.html", "patient.html", "knowledge_graph.html"):
            text = (ROOT / "templates" / name).read_text(encoding="utf-8")
            for word in REMOVED_SENSORS:
                self.assertNotIn(f'data-sensor="{word}', text, name)
        js = (ROOT / "static" / "js" / "dashboard.js").read_text(encoding="utf-8")
        for word in REMOVED_SENSORS:
            self.assertNotIn(word, js)


if __name__ == "__main__":
    db.init_db()
    unittest.main()
