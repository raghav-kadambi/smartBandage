"""Knowledge Graph Builder and Query Engine for Smart Bandage Medical Literature.
Uses NetworkX to construct an interconnected clinical graph connecting:
- Papers (Peer-reviewed literature)
- Biomarkers / Sensors (Temperature, Humidity, Heart Rate, Blood Pressure)
- Clinical States (Healthy, Healing, Local Infection, Systemic Infection, Delayed Healing,
  Maceration, Desiccation)
- Clinical Interventions (Clinician review, Antibiotics, Dressings, Offloading, BP control, ...)

Also computes graph metrics (Degree Centrality, PageRank) and serializes
data for browser-based interactive force-directed visualization.
"""

import json
from typing import Dict, Any, List, Optional
import networkx as nx

from data.literature_data import PAPERS, BIOMARKER_SPECS, CLINICAL_STATES, INTERVENTIONS


class WoundKnowledgeGraph:
    """Manages the clinical knowledge graph connecting literature, sensors, and conditions."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self.build_graph()

    def build_graph(self):
        """Construct the multi-relational knowledge graph."""
        self.graph.clear()

        # 1. Add Biomarker / Sensor Nodes
        for bio_id, spec in BIOMARKER_SPECS.items():
            node_id = f"biomarker_{bio_id}"
            self.graph.add_node(
                node_id,
                id=node_id,
                label=f"{spec['name']}",
                short_name=bio_id,
                type="biomarker",
                color="#2f6f62",
                unit=spec["unit"],
                description=spec["description"],
                healthy_range=spec.get("healthy_range"),
                healing_range=spec.get("healing_range"),
                warning_threshold=spec.get("warning_threshold") or spec.get("warning_high"),
                pathophysiology=spec["pathophysiology"],
            )

        # 2. Add Clinical State Nodes
        for state_id, spec in CLINICAL_STATES.items():
            node_id = f"state_{state_id}"
            self.graph.add_node(
                node_id,
                id=node_id,
                label=spec["label"],
                short_name=state_id,
                type="condition",
                color=spec["color"],
                description=spec["description"],
            )

        # 3. Add Clinical Intervention Nodes
        for tx_id, spec in INTERVENTIONS.items():
            node_id = f"tx_{tx_id}"
            self.graph.add_node(
                node_id,
                id=node_id,
                label=spec["name"],
                short_name=tx_id,
                type="intervention",
                color="#5b6ee1",
                description=spec["description"],
            )
            # Add TREATS edges from Intervention to target Clinical States
            for target_state in spec["target_states"]:
                target_node = f"state_{target_state}"
                if target_node in self.graph:
                    self.graph.add_edge(
                        node_id,
                        target_node,
                        relation="TREATS",
                        label="Treats / Manages",
                    )

        # 4. Add Biomarker -> Clinical State (INDICATES) edges with clinical thresholds
        # Thresholds come from the papers in data/literature_data.py (source in brackets)
        sensor_to_state_links = [
            ("temperature", "systemic_infection", "Temp > 38 or < 36 °C (SIRS) [Bone 1992]"),
            ("temperature", "infected", "Local wound heat vs control site [Fierheller 2010]"),
            ("temperature", "delayed_healing", "Wound warmer than periwound skin, RR 2.25 [Nakagami 2010]"),
            ("temperature", "wound_healing", "Wound bed ≥ 33 °C for cell activity [McGuiness 2004]"),
            ("humidity", "wound_healing", "Moist wound bed epithelizes faster [Winter 1962]"),
            ("humidity", "wound_desiccation", "Dry bed forms scab, slows closure [Junker 2013]"),
            ("humidity", "periwound_maceration", "Prolonged saturation macerates skin [Cutting 2002]"),
            ("humidity", "infected", "Increased exudate with bacterial burden [Woo 2009]"),
            ("heart_rate", "systemic_infection", "HR > 90 bpm (SIRS) [Bone 1992]"),
            ("heart_rate", "delayed_healing", "Stress response slows repair [Gouin 2011]"),
            ("blood_pressure", "systemic_infection", "Systolic ≤ 100 mmHg (qSOFA) [Singer 2016]"),
            ("blood_pressure", "delayed_healing", "Hypertension: 3.8 vs 2.0 days to dry wound [Ahmed 2011]"),
        ]

        for bio_key, state_key, rule_label in sensor_to_state_links:
            source = f"biomarker_{bio_key}"
            target = f"state_{state_key}"
            if source in self.graph and target in self.graph:
                self.graph.add_edge(
                    source,
                    target,
                    relation="INDICATES",
                    label=rule_label,
                )

        # 5. Add Paper Nodes and Edges
        paper_id_map = {p["id"]: f"paper_{p['id']}" for p in PAPERS}

        for paper in PAPERS:
            paper_node_id = paper_id_map[paper["id"]]
            first_author = paper["authors"].split(",")[0].split()[0]
            display_label = f"{first_author} ({paper['year']})"

            self.graph.add_node(
                paper_node_id,
                id=paper_node_id,
                label=display_label,
                short_name=paper["id"],
                type="paper",
                color="#0f766e",
                title=paper["title"],
                authors=paper["authors"],
                year=paper["year"],
                journal=paper["journal"],
                doi=paper["doi"],
                pmid=paper.get("pmid", ""),
                pubmed_url=paper.get("pubmed_url", ""),
                abstract=paper["abstract"],
                key_findings=paper["key_findings"],
                biomarkers=paper["biomarkers"],
                thresholds=paper.get("sensor_thresholds", {}),
            )

            # Paper -[:INVESTIGATES]-> Biomarker
            for bio in paper["biomarkers"]:
                bio_node_id = f"biomarker_{bio}"
                if bio_node_id in self.graph:
                    self.graph.add_edge(
                        paper_node_id,
                        bio_node_id,
                        relation="INVESTIGATES",
                        label=f"Investigates {bio.replace('_', ' ')}",
                    )

            # Paper -[:EVIDENCES]-> Clinical Condition
            for cond in paper.get("clinical_conditions", []):
                cond_node_id = f"state_{cond}"
                if cond_node_id in self.graph:
                    self.graph.add_edge(
                        paper_node_id,
                        cond_node_id,
                        relation="EVIDENCES",
                        label="Clinical Evidence",
                    )

            # Paper -[:RECOMMENDS]-> Intervention
            for tx in paper.get("interventions", []):
                tx_node_id = f"tx_{tx}"
                if tx_node_id in self.graph:
                    self.graph.add_edge(
                        paper_node_id,
                        tx_node_id,
                        relation="RECOMMENDS",
                        label="Recommends",
                    )

            # Paper -[:CITES]-> Paper (Interconnected citation network)
            for cited_id in paper.get("cites", []):
                if cited_id in paper_id_map:
                    target_paper_node = paper_id_map[cited_id]
                    self.graph.add_edge(
                        paper_node_id,
                        target_paper_node,
                        relation="CITES",
                        label="Cites",
                    )

    def to_cytoscape_json(self) -> Dict[str, Any]:
        """Export graph formatted for Cytoscape.js or Force-Graph visualization."""
        # Calculate centrality metrics
        centralities = nx.degree_centrality(self.graph)
        try:
            pagerank = nx.pagerank(self.graph, alpha=0.85)
        except Exception:
            pagerank = {n: 1.0 for n in self.graph.nodes()}

        nodes = []
        for node_id, data in self.graph.nodes(data=True):
            deg = self.graph.degree(node_id)
            pr = pagerank.get(node_id, 0.0)
            score = centralities.get(node_id, 0.0)

            # Calculate adaptive node visual size
            base_size = 28
            if data["type"] == "biomarker":
                base_size = 36 + int(deg * 2)
            elif data["type"] == "condition":
                base_size = 32 + int(deg * 1.5)
            elif data["type"] == "paper":
                base_size = 22 + int(deg * 2.2)

            node_dict = {
                "data": {
                    **data,
                    "degree": deg,
                    "centrality": round(score, 3),
                    "pagerank": round(pr, 4),
                    "visual_size": base_size,
                }
            }
            nodes.append(node_dict)

        edges = []
        for u, v, data in self.graph.edges(data=True):
            edge_id = f"{u}->{v}"
            edges.append({
                "data": {
                    "id": edge_id,
                    "source": u,
                    "target": v,
                    "relation": data.get("relation", "CONNECTS"),
                    "label": data.get("label", ""),
                }
            })

        counts = {
            "papers": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "paper"),
            "biomarkers": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "biomarker"),
            "conditions": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "condition"),
            "interventions": sum(1 for _, d in self.graph.nodes(data=True) if d.get("type") == "intervention"),
            "citations": sum(1 for _, _, d in self.graph.edges(data=True) if d.get("relation") == "CITES"),
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
        }

        return {
            "elements": {
                "nodes": nodes,
                "edges": edges,
            },
            "stats": counts,
        }

    def get_node_details(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve full details of a specific node and its immediate neighborhood."""
        if node_id not in self.graph:
            return None

        node_data = dict(self.graph.nodes[node_id])
        successors = []
        predecessors = []

        for target in self.graph.successors(node_id):
            edge_data = self.graph.get_edge_data(node_id, target)
            successors.append({
                "id": target,
                "label": self.graph.nodes[target].get("label", target),
                "type": self.graph.nodes[target].get("type", "unknown"),
                "relation": edge_data.get("relation", ""),
                "label_edge": edge_data.get("label", ""),
            })

        for source in self.graph.predecessors(node_id):
            edge_data = self.graph.get_edge_data(source, node_id)
            predecessors.append({
                "id": source,
                "label": self.graph.nodes[source].get("label", source),
                "type": self.graph.nodes[source].get("type", "unknown"),
                "relation": edge_data.get("relation", ""),
                "label_edge": edge_data.get("label", ""),
            })

        return {
            "node": node_data,
            "connected_to": successors,
            "connected_from": predecessors,
            "total_connections": len(successors) + len(predecessors),
        }

    def get_biomarker_subgraph(self, biomarker_name: str) -> Dict[str, Any]:
        """Get the localized neighborhood surrounding a specific sensor biomarker."""
        bio_node = f"biomarker_{biomarker_name}"
        if bio_node not in self.graph:
            return {"nodes": [], "edges": []}

        neighbors = set([bio_node])
        neighbors.update(self.graph.neighbors(bio_node))
        neighbors.update(self.graph.predecessors(bio_node))

        subg = self.graph.subgraph(neighbors)
        nodes = [{"data": dict(subg.nodes[n])} for n in subg.nodes()]
        edges = [
            {"data": {"id": f"{u}->{v}", "source": u, "target": v, **d}}
            for u, v, d in subg.edges(data=True)
        ]
        return {"nodes": nodes, "edges": edges}


# Global singleton instance
kg = WoundKnowledgeGraph()
