"""Tests for the mobile API (/api/m): auth, model gating, model card, guides and RAG-grounded chat."""

import unittest
import uuid

import database as db
import mobile_api
import mobile_server  # noqa: F401  (registers the /api/m blueprint on the web app)
from app import app
from data.literature_data import PAPERS


class TestMobileAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = app.test_client()
        cls.email = f"mobile-test-{uuid.uuid4().hex[:8]}@example.com"
        r = cls.client.post("/api/m/auth/signup", json={"name": "Mobile Test", "email": cls.email, "password": "secret1"})
        cls.headers = {"Authorization": f"Bearer {r.get_json()['token']}"}

    @classmethod
    def tearDownClass(cls):
        conn = db.get_db()
        uid = conn.execute("SELECT id FROM users WHERE email = ?", (cls.email,)).fetchone()["id"]
        conn.execute("DELETE FROM mobile_readings WHERE user_id = ?", (uid,))
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))
        conn.commit()
        conn.close()

    def post(self, path, body):
        return self.client.post(path, json=body, headers=self.headers)

    def test_requires_token(self):
        self.assertEqual(self.client.get("/api/m/status").status_code, 401)

    def test_assessment_needs_all_five_inputs(self):
        r = self.post("/api/m/readings", {"temperature": 36.9, "humidity": 60, "moisture": 3, "source": "demo"}).get_json()
        self.assertIsNone(r["condition"])
        self.assertEqual(set(r["missing"]), {"heart_rate", "systolic_bp", "diastolic_bp"})

        r = self.post("/api/m/readings", {"bpm": 76, "systolic": 118, "diastolic": 76, "source": "demo"}).get_json()
        self.assertEqual(r["missing"], [])
        self.assertIn(r["condition"], {"healthy", "wound_healing", "infected"})
        self.assertAlmostEqual(sum(r["probs"].values()), 1.0, places=2)

    def test_fever_tachycardia_hypotension_flags_infection(self):
        r = self.post("/api/m/readings", {"temperature": 39.4, "humidity": 90, "bpm": 118, "systolic": 92,
                                           "diastolic": 58, "source": "test"}).get_json()
        self.assertEqual(r["condition"], "infected")
        status = self.client.get("/api/m/status?demo=0", headers=self.headers).get_json()
        self.assertEqual(status["wound"]["condition"], "infected")
        self.assertEqual(status["overall"]["level"], "alert")

    def test_out_of_range_values_dropped(self):
        r = self.post("/api/m/readings", {"temperature": 80, "source": "test"})
        self.assertEqual(r.status_code, 400)

    def test_model_card_reports_external_validation(self):
        card = self.client.get("/api/m/model", headers=self.headers).get_json()
        self.assertEqual(card["features"], ["temperature", "humidity", "heart_rate", "systolic_bp", "diastolic_bp"])
        ours = [r for r in card["external"]["patient_auroc"] if r["ours"]][0]
        baselines = [r["auroc"] for r in card["external"]["patient_auroc"] if not r["ours"]]
        self.assertGreater(ours["auroc"], max(baselines))
        self.assertNotIn(".py", " ".join([card["training"]["source"], card["training"]["healing_days_source"]]))

    def test_guides_cite_pubmed_corpus(self):
        info = self.client.get("/api/m/wound-info", headers=self.headers).get_json()
        ids = {p["id"] for p in PAPERS}
        self.assertEqual(len(info["papers"]), len(PAPERS))
        for guide in info["guides"].values():
            self.assertTrue(guide["papers"])
            self.assertTrue(set(guide["papers"]) <= ids)
        self.assertTrue(all(p["url"].startswith("https://") for p in info["papers"]))

    def test_chat_cites_only_retrieved_pubmed_papers(self):
        saved = mobile_api._state["groq"]
        mobile_api._state["groq"] = None  # no network: the reply is the fallback text plus citations
        try:
            out = self.post("/api/m/chat", {"message": "Is a warm wound a sign of infection?"}).get_data(as_text=True)
        finally:
            mobile_api._state["groq"] = saved
        self.assertIn("__CITATIONS__:", out)
        import json
        cites = json.loads(out.split("__CITATIONS__:")[1])
        ids = {p["id"] for p in PAPERS}
        self.assertTrue(cites)
        self.assertTrue(all(c["id"] in ids and "pubmed" in c["url"] for c in cites))

    def test_cite_filter_drops_unretrieved_tags(self):
        f = mobile_api.CiteFilter({"[Fierheller & Sibbald, 2010]"})
        out = f.feed("Warmth matters [Fierheller & Sibbald, 2010] and [Made Up et al., 2019].") + f.flush()
        self.assertIn("[Fierheller & Sibbald, 2010]", out)
        self.assertNotIn("Made Up", out)


if __name__ == "__main__":
    unittest.main()
