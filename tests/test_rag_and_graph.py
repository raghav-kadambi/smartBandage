"""Automated verification suite for RAG and Knowledge Graph features."""

import unittest
from app import app
import database as db


class TestRAGAndKnowledgeGraph(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        # Set up a test user in session
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
        self.assertIn("elements", data)
        self.assertIn("stats", data)
        self.assertGreaterEqual(data["stats"]["papers"], 20)
        self.assertGreaterEqual(data["stats"]["biomarkers"], 5)
        self.assertGreaterEqual(data["stats"]["citations"], 40)
        self.assertGreaterEqual(len(data["elements"]["nodes"]), 35)
        self.assertGreaterEqual(len(data["elements"]["edges"]), 100)

    def test_knowledge_graph_node_detail_api(self):
        # Test paper node
        resp = self.client.get("/api/graph/node/paper_schneider_2007")
        self.assertEqual(resp.status_code, 200)
        paper_data = resp.get_json()
        self.assertEqual(paper_data["node"]["type"], "paper")
        self.assertIn("Schneider", paper_data["node"]["authors"])
        self.assertIn("connected_to", paper_data)

        # Test biomarker sensor node
        resp_bio = self.client.get("/api/graph/node/biomarker_pH")
        self.assertEqual(resp_bio.status_code, 200)
        bio_data = resp_bio.get_json()
        self.assertEqual(bio_data["node"]["type"], "biomarker")
        self.assertIn("healthy_range", bio_data["node"])

    def test_rag_semantic_search_api(self):
        resp = self.client.get("/api/rag/search?q=skin+temperature+monitoring+infection&limit=3")
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertIn("results", data)
        self.assertGreaterEqual(len(data["results"]), 1)
        top_hit = data["results"][0]
        self.assertIn("title", top_hit)
        self.assertIn("score", top_hit)
        # Should match temperature papers like Armstrong or Fierheller
        titles = [r["title"].lower() for r in data["results"]]
        self.assertTrue(any("temperature" in t for t in titles))

    def test_rag_chat_context_injection(self):
        from rag_service import rag_service
        # Simulate patient with alkaline pH 8.4 and elevated temperature 37.8
        sensor_ctx = {
            "pH": 8.4,
            "temperature": 37.8,
            "humidity": 70.0,
            "exudate_level": 7.0,
            "oxygen_saturation": 52.0,
        }
        res = rag_service.build_rag_context_for_chat(
            "Why is my wound feeling hot and leaking fluid?",
            sensor_readings=sensor_ctx,
            limit=3,
        )
        self.assertIn("prompt_text", res)
        self.assertIn("citations", res)
        self.assertGreaterEqual(len(res["citations"]), 1)
        # Verify prompt text contains literature excerpts and thresholds
        prompt_text = res["prompt_text"]
        self.assertIn("Findings:", prompt_text)


if __name__ == "__main__":
    unittest.main()
