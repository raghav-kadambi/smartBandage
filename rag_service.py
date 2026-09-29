"""Medical Literature RAG (Retrieval-Augmented Generation) Service using Qdrant.
Embeds clinical literature using FastEmbed (BAAI/bge-small-en-v1.5, 384 dims)
and stores them in an embedded, file-persisted Qdrant database.
Provides semantic retrieval to ground LLM patient/clinician conversations in peer-reviewed evidence.
"""

import os
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from fastembed import TextEmbedding

from data.literature_data import PAPERS, BIOMARKER_SPECS

ROOT = Path(__file__).resolve().parent
CACHE_FILE = ROOT / "data" / "literature_embeddings.pkl"
COLLECTION_NAME = "wound_clinical_literature"
VECTOR_DIM = 384


class LiteratureRAGService:
    """Manages vector indexing and semantic retrieval for wound care literature.
    Uses in-memory Qdrant with precomputed embedding cache to ensure instant,
    lock-free concurrent access across Flask reloader and multiple worker processes.
    """

    def __init__(self):
        # Use in-memory Qdrant instance to eliminate Windows file-locking collisions
        self.client = QdrantClient(location=":memory:")
        self.embedder = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
        self._init_collection()

    def _init_collection(self):
        """Create collection and populate from cached or newly computed embeddings."""
        self.client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        self.index_literature()

    def index_literature(self):
        """Build chunks and index all papers into Qdrant (cached for instant startup)."""
        if CACHE_FILE.exists():
            try:
                with open(CACHE_FILE, "rb") as f:
                    cached_points = pickle.load(f)
                if len(cached_points) == len(PAPERS):
                    self.client.upsert(
                        collection_name=COLLECTION_NAME,
                        points=cached_points,
                    )
                    return
            except Exception:
                pass

        texts_to_embed = []
        points = []

        for idx, paper in enumerate(PAPERS):
            # Format comprehensive text representation for dense embedding
            threshold_texts = []
            for b, t in paper.get("sensor_thresholds", {}).items():
                if isinstance(t, dict) and "clinical_rule" in t:
                    threshold_texts.append(f"{b}: {t['clinical_rule']}")
                else:
                    threshold_texts.append(f"{b}: {t}")

            threshold_summary = "; ".join(threshold_texts)
            chunk_text = (
                f"Title: {paper['title']}. "
                f"Authors: {paper['authors']} ({paper['year']}), Journal: {paper['journal']}. "
                f"Biomarkers & Sensors: {', '.join(paper['biomarkers'])}. "
                f"Clinical Conditions: {', '.join(paper.get('clinical_conditions', []))}. "
                f"Clinical Thresholds: {threshold_summary}. "
                f"Key Findings: {paper['key_findings']} "
                f"Abstract: {paper['abstract']}"
            )
            texts_to_embed.append(chunk_text)

        # Batch embed using FastEmbed
        embeddings = list(self.embedder.embed(texts_to_embed))

        for idx, (paper, emb, chunk_text) in enumerate(zip(PAPERS, embeddings, texts_to_embed)):
            payload = {
                "paper_id": paper["id"],
                "title": paper["title"],
                "authors": paper["authors"],
                "year": paper["year"],
                "journal": paper["journal"],
                "doi": paper["doi"],
                "pmid": paper.get("pmid", ""),
                "biomarkers": paper["biomarkers"],
                "clinical_conditions": paper.get("clinical_conditions", []),
                "sensor_thresholds": paper.get("sensor_thresholds", {}),
                "key_findings": paper["key_findings"],
                "abstract": paper["abstract"],
                "chunk_text": chunk_text,
            }
            points.append(
                PointStruct(
                    id=idx + 1,
                    vector=emb.tolist(),
                    payload=payload,
                )
            )

        # Cache to disk for instant subsequent startups
        try:
            with open(CACHE_FILE, "wb") as f:
                pickle.dump(points, f)
        except Exception:
            pass

        self.client.upsert(
            collection_name=COLLECTION_NAME,
            points=points,
        )

    def search(
        self,
        query: str,
        limit: int = 3,
        biomarker_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Perform semantic vector search in Qdrant."""
        if not query.strip():
            return []

        query_emb = list(self.embedder.embed([query]))[0].tolist()

        search_filter = None
        if biomarker_filter:
            search_filter = Filter(
                must=[
                    FieldCondition(
                        key="biomarkers",
                        match=MatchValue(value=biomarker_filter),
                    )
                ]
            )

        search_result = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_emb,
            query_filter=search_filter,
            limit=limit,
        )

        results = []
        for point in search_result.points:
            p = point.payload
            results.append({
                "score": round(float(point.score), 3),
                "paper_id": p.get("paper_id"),
                "title": p.get("title"),
                "authors": p.get("authors"),
                "year": p.get("year"),
                "journal": p.get("journal"),
                "doi": p.get("doi"),
                "pmid": p.get("pmid"),
                "biomarkers": p.get("biomarkers", []),
                "key_findings": p.get("key_findings"),
                "abstract": p.get("abstract"),
                "sensor_thresholds": p.get("sensor_thresholds", {}),
            })

        return results

    def build_rag_context_for_chat(
        self,
        user_query: str,
        sensor_readings: Optional[Dict[str, Any]] = None,
        limit: int = 3,
    ) -> Dict[str, Any]:
        """Formulate augmented search query taking current sensor readings into account,
        retrieve relevant literature, and format context for the LLM prompt.
        """
        # Augment search query with sensor anomalies if present
        query_terms = [user_query]
        relevant_biomarker = None

        if sensor_readings:
            ph = sensor_readings.get("pH")
            temp = sensor_readings.get("temperature")
            hum = sensor_readings.get("humidity")
            exudate = sensor_readings.get("exudate_level")
            o2 = sensor_readings.get("oxygen_saturation")

            if ph is not None and float(ph) > 7.3:
                query_terms.append(f"elevated alkaline wound pH {ph} infection biofilm")
                relevant_biomarker = "pH"
            if temp is not None and float(temp) > 35.0:
                query_terms.append(f"elevated wound temperature {temp}C inflammation infection")
            if exudate is not None and float(exudate) > 5.0:
                query_terms.append(f"heavy wound exudate level {exudate} proteases MMPs")
            if hum is not None and float(hum) > 85.0:
                query_terms.append(f"high humidity {hum}% maceration moisture")
            elif hum is not None and float(hum) < 50.0:
                query_terms.append(f"low humidity {hum}% dry desiccation")
            if o2 is not None and float(o2) < 65.0:
                query_terms.append(f"low tissue oxygen saturation {o2}% ischemia hypoxia")

        full_search_query = " ".join(query_terms)
        papers = self.search(full_search_query, limit=limit)

        if not papers:
            # Fallback search purely on user query
            papers = self.search(user_query, limit=limit)

        # Build prompt injection section
        context_lines = []
        citations_for_ui = []

        for p in papers:
            author_short = p['authors'].split(',')[0].split()[0]
            citation_tag = f"[{author_short} et al., {p['year']}]"
            citations_for_ui.append({
                "tag": citation_tag,
                "paper_id": p["paper_id"],
                "title": p["title"],
                "authors": p["authors"],
                "year": p["year"],
                "journal": p["journal"],
                "doi": p["doi"],
                "score": p["score"],
                "biomarkers": p["biomarkers"],
                "key_findings": p["key_findings"],
            })

            threshold_desc = ""
            if p.get("sensor_thresholds"):
                threshold_desc = f"Sensor Rules / Thresholds: {p['sensor_thresholds']}"

            context_lines.append(
                f"- Paper {citation_tag}: '{p['title']}' ({p['journal']} {p['year']})\n"
                f"  Findings: {p['key_findings']}\n"
                f"  {threshold_desc}\n"
                f"  Abstract excerpt: {p['abstract'][:250]}..."
            )

        formatted_context = "\n\n".join(context_lines)

        return {
            "prompt_text": formatted_context,
            "citations": citations_for_ui,
            "matched_papers": papers,
        }

    def close(self):
        try:
            if hasattr(self, "client") and self.client is not None:
                self.client.close()
        except Exception:
            pass


# Global singleton instance
import atexit

rag_service = LiteratureRAGService()
atexit.register(rag_service.close)

