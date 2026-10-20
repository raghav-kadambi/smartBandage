/**
 * Knowledge Graph Interactive Visualization for WoundSense
 * Uses vis-network for smooth force-directed physics, node clustering, and inspector drawer.
 */

document.addEventListener("DOMContentLoaded", () => {
  let network = null;
  let allNodes = [];
  let allEdges = [];
  let nodesDataSet = null;
  let edgesDataSet = null;
  let activeFilter = "all";
  let activeSensor = "all";
  let currentGraphData = null;

  const canvasContainer = document.getElementById("kgCanvas");
  const loadingEl = document.getElementById("kgLoading");
  const inspectorEl = document.getElementById("kgInspector");
  const inspBody = document.getElementById("inspBody");
  const inspBadge = document.getElementById("inspTypeBadge");
  const inspCloseBtn = document.getElementById("inspCloseBtn");
  const searchInput = document.getElementById("kgSearchInput");
  const btnFit = document.getElementById("btnFitGraph");
  const btnReset = document.getElementById("btnResetPhysics");

  // Fetch graph data from Flask backend
  async function loadGraphData() {
    try {
      const resp = await fetch("/api/graph/data");
      if (!resp.ok) throw new Error("Failed to load knowledge graph data.");
      const data = await resp.json();
      currentGraphData = data;

      // Update stat pills
      if (data.stats) {
        document.getElementById("statPapers").textContent = data.stats.papers || 20;
        document.getElementById("statSensors").textContent = data.stats.biomarkers || 5;
        document.getElementById("statConditions").textContent = data.stats.conditions || 7;
        document.getElementById("statCitations").textContent = data.stats.citations || 43;
      }

      initNetwork(data.elements);
      loadingEl.style.display = "none";
    } catch (err) {
      console.error(err);
      loadingEl.innerHTML = `<span style="color:var(--danger)">Error loading knowledge graph: ${err.message}</span>`;
    }
  }

  // Format node styling for vis-network
  function transformNode(n) {
    const d = n.data;
    let background = "#0f766e";
    let border = "#0d5c56";
    let shape = "dot";
    let fontColor = "#1a1a1a";
    let size = d.visual_size || 24;

    if (d.type === "biomarker") {
      background = "#2f6f62";
      border = "#1d473f";
      shape = "hexagon";
      size = Math.max(size, 34);
    } else if (d.type === "condition") {
      background = d.color || "#d9483f";
      border = "#8c2822";
      shape = "diamond";
      size = Math.max(size, 30);
    } else if (d.type === "intervention") {
      background = "#4f46e5";
      border = "#3730a3";
      shape = "box";
      size = 20;
    } else if (d.type === "paper") {
      background = "#ffffff";
      border = "#0f766e";
      shape = "dot";
      size = Math.max(size, 20);
    }

    return {
      id: d.id,
      label: d.label || d.id,
      shape: shape,
      size: size,
      color: {
        background: background,
        border: border,
        highlight: {
          background: "#2f6f62",
          border: "#111827",
        },
        hover: {
          background: "#3b82f6",
          border: "#1d4ed8",
        },
      },
      borderWidth: 2.5,
      borderWidthSelected: 4,
      font: {
        color: fontColor,
        size: d.type === "biomarker" ? 14 : 11,
        face: "-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif",
        strokeWidth: 2,
        strokeColor: "#ffffff",
      },
      raw: d,
    };
  }

  // Format edge styling for vis-network
  function transformEdge(e) {
    const d = e.data;
    let color = "#cbd5e1";
    let width = 1.2;
    let dashes = false;

    if (d.relation === "CITES") {
      color = "#94a3b8";
      dashes = true;
      width = 1.0;
    } else if (d.relation === "INDICATES") {
      color = "#e11d48";
      width = 2.0;
    } else if (d.relation === "INVESTIGATES") {
      color = "#0d9488";
      width = 1.8;
    } else if (d.relation === "TREATS") {
      color = "#6366f1";
      width = 1.6;
    }

    return {
      id: d.id,
      from: d.source,
      to: d.target,
      label: d.relation === "INDICATES" ? "" : d.relation,
      font: { size: 9, color: "#64748b", align: "middle" },
      arrows: {
        to: { enabled: true, scaleFactor: 0.6 },
      },
      color: {
        color: color,
        highlight: "#0f766e",
        hover: "#2563eb",
      },
      width: width,
      dashes: dashes,
      smooth: { type: "continuous", roundness: 0.15 },
      raw: d,
    };
  }

  function initNetwork(elements) {
    allNodes = elements.nodes.map(transformNode);
    allEdges = elements.edges.map(transformEdge);

    nodesDataSet = new vis.DataSet(allNodes);
    edgesDataSet = new vis.DataSet(allEdges);

    const data = {
      nodes: nodesDataSet,
      edges: edgesDataSet,
    };

    const options = {
      nodes: {
        shadow: { enabled: true, color: "rgba(0,0,0,0.06)", size: 6, x: 1, y: 2 },
      },
      edges: {
        smooth: { type: "dynamic" },
      },
      physics: {
        enabled: true,
        solver: "forceAtlas2Based",
        forceAtlas2Based: {
          gravitationalConstant: -70,
          centralGravity: 0.015,
          springLength: 120,
          springConstant: 0.08,
          damping: 0.4,
          avoidOverlap: 0.7,
        },
        stabilization: {
          iterations: 150,
          updateInterval: 25,
        },
      },
      interaction: {
        hover: true,
        tooltipDelay: 150,
        navigationButtons: false,
        keyboard: false,
        zoomView: true,
        dragView: true,
      },
    };

    network = new vis.Network(canvasContainer, data, options);

    // Event listeners
    network.on("click", (params) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        showNodeInspector(nodeId);
      } else {
        resetHighlight();
      }
    });

    network.on("hoverNode", () => {
      canvasContainer.style.cursor = "pointer";
    });

    network.on("blurNode", () => {
      canvasContainer.style.cursor = "default";
    });
  }

  // Node Inspector drawer renderer
  async function showNodeInspector(nodeId) {
    try {
      const resp = await fetch(`/api/graph/node/${encodeURIComponent(nodeId)}`);
      if (!resp.ok) throw new Error("Could not fetch node details");
      const details = await resp.json();
      renderInspectorContent(details);
      highlightNeighborhood(nodeId);
    } catch (e) {
      console.error(e);
    }
  }

  function renderInspectorContent(data) {
    const node = data.node;
    inspectorEl.classList.add("open");

    let badgeClass = "badge-paper";
    let badgeText = "PEER-REVIEWED PAPER";

    if (node.type === "biomarker") {
      badgeClass = "badge-sensor";
      badgeText = "PHYSIOLOGICAL SENSOR";
    } else if (node.type === "condition") {
      badgeClass = "badge-condition";
      badgeText = "CLINICAL PATHOLOGY";
    } else if (node.type === "intervention") {
      badgeClass = "badge-tx";
      badgeText = "CLINICAL INTERVENTION";
    }

    inspBadge.className = `inspector-badge ${badgeClass}`;
    inspBadge.textContent = badgeText;

    let html = "";

    if (node.type === "paper") {
      html = `
        <div class="insp-title">${escapeHtml(node.title || node.label)}</div>
        <div class="insp-meta">
          <strong>${escapeHtml(node.authors || "")}</strong> (${node.year || ""})<br/>
          <em>${escapeHtml(node.journal || "")}</em>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Key Findings</div>
          <p class="insp-text">${escapeHtml(node.key_findings || "No summary available.")}</p>
        </div>

        ${renderThresholds(node.thresholds)}

        <div class="insp-section">
          <div class="insp-section-title">Abstract (verbatim from PubMed)</div>
          <p class="insp-abstract">${escapeHtml(node.abstract || "No abstract available.")}</p>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Connected Biomarkers & States (${data.total_connections})</div>
          <div class="insp-tag-cloud">
            ${data.connected_to.map(c => `
              <span class="insp-chip chip-${c.type}" onclick="window.kgFocusNode('${c.id}')">
                ${escapeHtml(c.relation)}: <strong>${escapeHtml(c.label)}</strong>
              </span>
            `).join("")}
          </div>
        </div>

        <div class="insp-actions">
          ${node.pmid ? `<a href="https://pubmed.ncbi.nlm.nih.gov/${encodeURIComponent(node.pmid)}/" target="_blank" rel="noopener" class="btn-insp btn-outline">PubMed ${escapeHtml(node.pmid)} ↗</a>` : ""}
          ${node.doi ? `<a href="https://doi.org/${node.doi}" target="_blank" rel="noopener" class="btn-insp btn-outline">DOI ↗</a>` : ""}
          <a href="/patient?q=${encodeURIComponent('What does the paper ' + (node.title || '') + ' say about my wound?')}" class="btn-insp btn-primary">Ask in RAG Chat 💬</a>
        </div>
      `;
    } else if (node.type === "biomarker") {
      html = `
        <div class="insp-title">${escapeHtml(node.label)}</div>
        <div class="insp-meta">Sensor Unit: <strong>${node.unit || "N/A"}</strong></div>

        <div class="insp-section">
          <div class="insp-section-title">Clinical Role</div>
          <p class="insp-text">${escapeHtml(node.description || "")}</p>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Pathophysiology</div>
          <p class="insp-text">${escapeHtml(node.pathophysiology || "")}</p>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Reference Thresholds</div>
          <div class="threshold-pill-group">
            ${node.healthy_range ? `<div class="th-pill th-healthy">Healthy: ${node.healthy_range.join(" - ")} ${node.unit || ""}</div>` : ""}
            ${node.healing_range ? `<div class="th-pill th-healing">Healing: ${node.healing_range.join(" - ")} ${node.unit || ""}</div>` : ""}
            ${node.warning_threshold ? `<div class="th-pill th-warning">Alert Threshold: > ${node.warning_threshold} ${node.unit || ""}</div>` : ""}
          </div>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Associated Literature & Indicators (${data.total_connections})</div>
          <div class="insp-tag-cloud">
            ${data.connected_from.map(c => `
              <span class="insp-chip chip-${c.type}" onclick="window.kgFocusNode('${c.id}')">
                ← ${escapeHtml(c.label)}
              </span>
            `).join("")}
            ${data.connected_to.map(c => `
              <span class="insp-chip chip-${c.type}" onclick="window.kgFocusNode('${c.id}')">
                → ${escapeHtml(c.label)} (${escapeHtml(c.label_edge)})
              </span>
            `).join("")}
          </div>
        </div>

        <div class="insp-actions">
          <a href="/patient?q=${encodeURIComponent('How does ' + (node.short_name || '') + ' affect my healing progress?')}" class="btn-insp btn-primary">Ask in RAG Chat 💬</a>
        </div>
      `;
    } else if (node.type === "condition") {
      html = `
        <div class="insp-title">${escapeHtml(node.label)}</div>

        <div class="insp-section">
          <div class="insp-section-title">Clinical Pathology</div>
          <p class="insp-text">${escapeHtml(node.description || "")}</p>
        </div>

        <div class="insp-section">
          <div class="insp-section-title">Diagnostic Indicators & Evidence (${data.total_connections})</div>
          <div class="insp-tag-cloud">
            ${data.connected_from.map(c => `
              <span class="insp-chip chip-${c.type}" onclick="window.kgFocusNode('${c.id}')">
                ← <strong>${escapeHtml(c.label)}</strong>: ${escapeHtml(c.label_edge || c.relation)}
              </span>
            `).join("")}
          </div>
        </div>

        <div class="insp-actions">
          <a href="/patient?q=${encodeURIComponent('What are the clinical guidelines for managing ' + (node.label || '') + '?')}" class="btn-insp btn-primary">Ask in RAG Chat 💬</a>
        </div>
      `;
    } else {
      // Intervention or other
      html = `
        <div class="insp-title">${escapeHtml(node.label)}</div>
        <div class="insp-section">
          <div class="insp-section-title">Description</div>
          <p class="insp-text">${escapeHtml(node.description || "")}</p>
        </div>
        <div class="insp-section">
          <div class="insp-section-title">Connections (${data.total_connections})</div>
          <div class="insp-tag-cloud">
            ${data.connected_to.map(c => `
              <span class="insp-chip chip-${c.type}" onclick="window.kgFocusNode('${c.id}')">
                Treats: <strong>${escapeHtml(c.label)}</strong>
              </span>
            `).join("")}
          </div>
        </div>
      `;
    }

    inspBody.innerHTML = html;
  }

  function renderThresholds(thresholds) {
    if (!thresholds || Object.keys(thresholds).length === 0) return "";
    let items = [];
    for (const [bio, val] of Object.entries(thresholds)) {
      if (typeof val === "object" && val.clinical_rule) {
        items.push(`<div class="th-item"><strong>${escapeHtml(bio)}:</strong> ${escapeHtml(val.clinical_rule)}</div>`);
      } else {
        items.push(`<div class="th-item"><strong>${escapeHtml(bio)}:</strong> ${JSON.stringify(val)}</div>`);
      }
    }
    return `
      <div class="insp-section">
        <div class="insp-section-title">Documented Clinical Thresholds</div>
        <div class="th-box">${items.join("")}</div>
      </div>
    `;
  }

  // Highlight selected node and its neighbors
  function highlightNeighborhood(nodeId) {
    if (!network) return;
    const connectedNodes = network.getConnectedNodes(nodeId);
    connectedNodes.push(nodeId);

    const updateNodes = allNodes.map((n) => {
      const isConnected = connectedNodes.includes(n.id);
      return {
        id: n.id,
        opacity: isConnected ? 1.0 : 0.15,
        font: { ...n.font, color: isConnected ? "#1a1a1a" : "#94a3b8" },
      };
    });

    nodesDataSet.update(updateNodes);
    network.focus(nodeId, { scale: 1.15, animation: { duration: 500, easingFunction: "easeInOutQuad" } });
  }

  function resetHighlight() {
    if (!nodesDataSet) return;
    const resetNodes = allNodes.map((n) => ({
      id: n.id,
      opacity: 1.0,
      font: n.font,
    }));
    nodesDataSet.update(resetNodes);
  }

  // Filter handlers
  document.querySelectorAll(".filter-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".filter-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeFilter = btn.dataset.filter;
      applyFilters();
    });
  });

  document.querySelectorAll(".sensor-pill").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".sensor-pill").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeSensor = btn.dataset.sensor;
      applyFilters();
    });
  });

  function applyFilters() {
    if (!nodesDataSet || !currentGraphData) return;

    const searchTerm = (searchInput.value || "").trim().toLowerCase();

    const filteredNodes = allNodes.filter((n) => {
      const d = n.raw;
      // Category filter
      if (activeFilter !== "all" && d.type !== activeFilter) {
        return false;
      }
      // Sensor filter
      if (activeSensor !== "all") {
        if (d.type === "biomarker" && d.short_name !== activeSensor) {
          return false;
        }
        if (d.type === "paper" && (!d.biomarkers || !d.biomarkers.includes(activeSensor))) {
          return false;
        }
      }
      // Search text filter
      if (searchTerm) {
        const text = `${d.label} ${d.title || ""} ${d.authors || ""} ${d.description || ""} ${d.key_findings || ""}`.toLowerCase();
        if (!text.includes(searchTerm)) {
          return false;
        }
      }
      return true;
    });

    const activeNodeIds = new Set(filteredNodes.map((n) => n.id));

    // Show/hide nodes by updating hidden property
    const updates = allNodes.map((n) => ({
      id: n.id,
      hidden: !activeNodeIds.has(n.id),
    }));
    nodesDataSet.update(updates);

    if (network) {
      network.fit({ animation: { duration: 500, easingFunction: "easeInOutQuad" } });
    }
  }

  searchInput.addEventListener("input", applyFilters);

  btnFit.addEventListener("click", () => {
    if (network) network.fit({ animation: { duration: 400 } });
  });

  btnReset.addEventListener("click", () => {
    if (network) {
      network.stabilize(100);
      network.fit();
    }
  });

  inspCloseBtn.addEventListener("click", () => {
    inspectorEl.classList.remove("open");
    resetHighlight();
  });

  // Global helper for chip clicking inside inspector
  window.kgFocusNode = (nodeId) => {
    showNodeInspector(nodeId);
  };

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  // Initial load
  loadGraphData();
});
