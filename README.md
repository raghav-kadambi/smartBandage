# WoundSense — Smart Wound-Care Bandage

A full-stack capstone demo: login, a live dashboard that runs two trained Random Forest
models on the bandage's sensor readings (simulated with sliders **or** streamed from an
ESP32), a patient chat grounded in verifiable PubMed literature, and an interactive
knowledge graph.

## Results at a glance

| Model | Metric | Result |
|---|---|---|
| Condition classifier (Random Forest) | Test accuracy (held-out 20% split) | **92.9%** |
| Condition classifier | 5-fold cross-validation accuracy | **92.9% ± 0.3%** |
| Condition classifier | Macro-F1 (held-out) | **0.93** |
| Healing-days regressor (Random Forest) | R² / mean absolute error (held-out) | **0.94 / 2.07 days** |
| Classifier, external real-world check | AUROC on 39,745 real ICU patients (PhysioNet 2019, never trained on) | **0.687**, vs 0.648 for the standard SIRS + BP clinical score |

## Sensors

| Signal | Model input | Unit |
|---|---|---|
| Body temperature | `temperature` | °C (skin reading calibrated to core-equivalent on the ESP32) |
| Humidity under the dressing | `humidity` | % RH |
| Heart rate | `heart_rate` | bpm |
| Blood pressure | `systolic_bp`, `diastolic_bp` | mmHg |

pH, exudate and SpO2 were removed: the hardware has no sensors for them.

## What's implemented

- **Auth**: Flask session login/signup, SQLite (`wound_bandage.db`, created and migrated automatically),
  passwords hashed with Werkzeug.
- **Input mode picker**: after login you choose **Simulate with sliders** or **Connect ESP32 bandage**
  (`/choose-mode`; switch any time from the dashboard).
- **ML models** (`models/train_model.py`): `RandomForestClassifier` (healthy / wound_healing / infected)
  and `RandomForestRegressor` (estimated days to heal) on the 5 inputs above.
- **External validation** (`validation/`): both models tested on the official
  **PhysioNet/CinC Challenge 2019** dataset (40,336 real ICU patients), which is never used for training.
  Results are on the *Model insights* page and below.
- **ESP32 integration**: the firmware (`firmware/esp32_smart_bandage/`) POSTs JSON over Wi-Fi to
  `/api/device/reading`, authenticated with a per-user device token shown on the dashboard.
- **Clinical literature RAG (Qdrant + FastEmbed)**: 28 real papers. Title, authors, journal, DOI and
  abstract are pulled **verbatim from PubMed** (`data/build_literature_corpus.py`), and every citation
  in chat links to its PubMed record.
- **Knowledge graph (NetworkX + vis-network)**: papers, the 4 sensors, 7 clinical states and
  10 interventions. Each sensor-to-state threshold names the paper it comes from.
- **Patient chat**: Groq-backed LLM prompted with the live reading, trend, wound details and the
  retrieved literature. It is told to cite only the retrieved papers.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env              # add GROQ_API_KEY for the chat (optional)
python app.py                     # http://127.0.0.1:5000
```

Rebuild everything from scratch. The trained models, metrics and PubMed corpus are committed, but
the validation figures in `model_outputs/` are git-ignored. Run the two validation commands once so
the Model insights page can show them:

```bash
python data/generate_training_data.py       # knowledge-based training set
python models/train_model.py                # train both Random Forests
python validation/download_physionet2019.py # ~40k files from PhysioNet's AWS mirror (~10 min)
python validation/validate_physionet2019.py # external test -> models/external_validation.json + figures
python data/build_literature_corpus.py      # re-pull the RAG papers from PubMed
python -m unittest tests.test_rag_and_graph
```

## Connecting the ESP32

1. Run `python app.py` on a laptop on the same Wi-Fi as the ESP32. The server binds to `0.0.0.0`;
   set `HOST=127.0.0.1` for slider-only use. Allow Python through the Windows firewall if prompted.
2. In the app choose **Connect ESP32 bandage**, then copy the *Server endpoint* and *Device token*.
3. Open `firmware/esp32_smart_bandage/esp32_smart_bandage.ino`, fill in Wi-Fi, `SERVER_URL` and
   `DEVICE_TOKEN`, and flash it (board: ESP32 Dev Module, built-in libraries only).
4. Leave `SIMULATE_SENSORS = true` to test the link first. Then set it to `false` and fill in the four
   `read*()` functions for your sensor modules. Set `SKIN_TO_CORE_OFFSET_C` by comparing against a
   clinical thermometer.

The dashboard polls every 3 s and shows connection status, live tiles and the model output.

```
POST /api/device/reading
X-Device-Token: <token>
{"temperature": 37.1, "humidity": 72, "heart_rate": 82, "systolic_bp": 121, "diastolic_bp": 79}
```

## Training data and validation

**Training data.** No public dataset records these signals from a wound dressing with
healthy / healing / infected labels. The training set (`data/wound_data_train.csv`, 18,000 rows)
is therefore *knowledge-based*: each class is sampled from distributions set by published criteria:
SIRS (temp > 38 or < 36 °C, HR > 90), Sepsis-3 / qSOFA (SBP ≤ 100 mmHg), moist wound healing
(humidity), and hypertension slowing healing. All of these sources are in the RAG corpus.

**External test set: PhysioNet/CinC Challenge 2019** ([dataset](https://physionet.org/content/challenge-2019/1.0.0/),
Reyna et al., *Crit Care Med* 2020, doi:10.1097/CCM.0000000000004145, CC-BY 4.0). It has hourly HR,
temperature, SBP and DBP for 40,336 ICU patients from two hospital systems, labelled with Sepsis-3 onset.

- It is used **only for testing**.
- Sepsis is *systemic* infection, so it is a real, officially labelled proxy for the `infected`
  class. It is not local wound infection.
- ICU data has no under-dressing humidity, so the deployed model's output is averaged over the
  training humidity distribution. A vitals-only Random Forest is reported as a check.
- Clinical baselines are scored on the same rows: SIRS vital-sign criteria and the qSOFA BP criterion.

**Results** (39,745 patients with usable vitals, 2,723 with sepsis; 1.35 M hourly rows):

| Model / score | AUROC, patient (95% CI) | AUPRC, patient (chance 0.069) | AUROC, hourly |
|---|---|---|---|
| **WoundSense Random Forest (deployed)** | **0.687 (0.676–0.696)** | **0.144** | **0.665** |
| Random Forest, vitals only | 0.682 | 0.129 | 0.664 |
| SIRS vital-sign criteria ≥ 2 (temp + HR) | 0.639 | 0.102 | 0.610 |
| SIRS vitals + SBP ≤ 100, score ≥ 2 | 0.648 | 0.106 | 0.616 |
| qSOFA systolic BP ≤ 100 | 0.564 | 0.078 | 0.529 |

- Per hospital system: A 0.659 vs SIRS 0.621; B 0.709 vs SIRS 0.653.
- At 80% specificity the model catches 45% of sepsis patients (patient level).
- For context, Seymour et al. (JAMA 2016) report ICU AUROCs of 0.64 for SIRS and 0.66 for qSOFA.
- **Limitation:** at the default decision rule (argmax class) the model is sensitive but not specific
  on ICU patients (sensitivity 0.62 / specificity 0.62 per hour). ICU vitals are abnormal far more
  often than in the bandage's intended outpatient use.
- **Regressor:** predicted days-to-heal is higher during sepsis hours (17.1 vs 13.9 days; AUROC 0.69
  at patient level). It rises only weakly as onset approaches (Spearman ρ = 0.11), which is
  construct-validity evidence, not accuracy.

Figures: `model_outputs/10_*.png` to `14_*.png`. Full numbers: `models/external_validation.json`.

## Project layout

```
smartBandage/
├── app.py                         # Flask app: auth, mode picker, /api/predict, ESP32 + chat APIs
├── database.py                    # SQLite helpers (users, readings, devices, chat, wound context)
├── rag_service.py                 # Qdrant + FastEmbed retrieval over the PubMed corpus
├── knowledge_graph.py             # NetworkX graph of papers / sensors / states / interventions
├── data/
│   ├── generate_training_data.py  # knowledge-based training set
│   ├── wound_data_train.csv
│   ├── build_literature_corpus.py # pulls papers from PubMed E-utilities
│   ├── literature_corpus.json     # verbatim PubMed metadata + abstracts
│   └── literature_data.py         # our annotations per PMID, sensor specs, states
├── models/                        # train_model.py, *.pkl, metadata.json, external_validation.json
├── validation/                    # PhysioNet 2019 download + external validation
├── firmware/esp32_smart_bandage/  # Arduino sketch for the ESP32
├── model_outputs/                 # validation figures
├── model_training.ipynb           # walkthrough: generate -> train -> validate
├── static/, templates/            # front end (mode_select.html, dashboard.html, ...)
└── tests/test_rag_and_graph.py
```

## Notes for the review

- **Days-to-heal is a heuristic**: no dataset records wound healing time. The regressor is checked
  for construct validity on PhysioNet (does predicted recovery time rise with sepsis?), not for accuracy.
- **Headline accuracy: 92.9%** on the held-out test split (cross-validated 92.9% ± 0.3%).
  The PhysioNet result is an additional real-patient check. There the model beats the standard
  clinical sepsis score (AUROC 0.687 vs 0.648) on data it never saw. AUROC is the right metric there
  because only 1.8% of ICU hours are septic, so raw accuracy on that data is dominated by the
  majority class.
- **Every RAG document is checkable**: click a source pill in chat or *PubMed ↗* in the graph inspector.

## System Design Overview

```mermaid
flowchart LR
  subgraph Client[Browser]
    Pages["Flask-rendered pages<br/>login, input-mode picker, dashboard,<br/>patient chat, wound details, insights, graph"]
    BrowserJS["JavaScript + CSS<br/>fetch APIs, update views,<br/>stream chat, draw graph"]
    Pages --> BrowserJS
  end

  subgraph Runtime[Flask application - app.py]
    Routes["Page routes + JSON APIs<br/>session-protected workflows"]
    Auth["Signup / login<br/>password hashing + session"]
    Predict["/api/predict + /api/device/reading<br/>validate 5 sensor values"]
    Models["Loaded model artifacts<br/>RandomForest classifier<br/>RandomForest regressor<br/>LabelEncoder"]
    Chat["/api/chat<br/>assemble patient context + stream"]
    Prompt["Clinical prompt<br/>sensor reading + trend + wound details<br/>+ retrieved literature"]
    RAG["LiteratureRAGService<br/>FastEmbed query vectors + semantic search"]
    Qdrant["Embedded Qdrant collection<br/>in-process memory"]
    KGAPI["Knowledge graph APIs<br/>data + node detail"]
    KG["NetworkX graph<br/>built in-process"]
    Metrics["Model info / metrics APIs"]

    Routes --> Auth
    Routes --> Predict
    Predict --> Models
    Routes --> Chat
    Chat --> RAG
    RAG --> Qdrant
    Chat --> Prompt
    RAG --> Prompt
    Routes --> KGAPI
    KGAPI --> KG
    Routes --> Metrics
  end

  subgraph Storage[Local files]
    SQLite[("SQLite: wound_bandage.db<br/>users, readings, devices, chat, wound context")]
    Artifacts["models/*.pkl + metadata.json"]
    Corpus["data/literature_corpus.json (PubMed)<br/>+ literature_data.py annotations"]
    EmbedCache["data/literature_embeddings.pkl<br/>embedding/index cache"]
    TrainingCSV["data/wound_data_train.csv<br/>knowledge-based training set"]
    TrainingOutputs["models/*.pkl + metadata.json"]
    NotebookOutputs["model_outputs/ figures<br/>models/external_validation.json"]
    PhysioNet[("PhysioNet 2019<br/>40,336 ICU patients<br/>TEST ONLY")]
  end

  subgraph Training[Offline training and analysis]
    Trainer["models/train_model.py<br/>fit/evaluate Random Forests"]
    Validator["validation/validate_physionet2019.py<br/>external test vs SIRS / qSOFA baselines"]
    Generator["data/generate_training_data.py<br/>literature-parameterised classes"]
    Generator --> TrainingCSV
    TrainingCSV --> Trainer
    Trainer --> TrainingOutputs
    TrainingOutputs --> Validator
    PhysioNet --> Validator
    Validator --> NotebookOutputs
  end

  Groq["Optional Groq API<br/>GROQ_API_KEY required for LLM"]
  Vis["vis-network CDN"]

  BrowserJS <-->|"HTTP / JSON"| Routes
  BrowserJS -->|"simulated slider values"| Predict
  ESP32["ESP32 bandage<br/>Wi-Fi JSON POST + device token"] -->|"live readings"| Predict
  Predict -->|"prediction + confidence + estimate"| BrowserJS
  Predict -->|"save each reading"| SQLite
  Auth <-->|"users"| SQLite
  Chat <-->|"read context + persist messages"| SQLite
  Prompt -->|"when configured"| Groq
  Groq -->|"streamed answer"| Chat
  Chat -->|"answer + citation marker"| BrowserJS
  RAG -->|"load corpus"| Corpus
  RAG <-->|"load/save cache"| EmbedCache
  KG -->|"load graph facts"| Corpus
  Models <--|"load at startup"| Artifacts
  TrainingOutputs --> Artifacts
  Metrics -->|"metadata.json + external_validation.json"| Artifacts
  KGAPI -->|"graph JSON"| BrowserJS
  BrowserJS -->|"render interactive graph"| Vis
```

Sensor inputs come from dashboard sliders (simulate mode) or from the ESP32 over Wi-Fi (ESP32 mode); both go through the same validation and models. Qdrant is created in memory at startup; `data/literature_embeddings.pkl` caches the embeddings (keyed by a hash of the corpus) and `wound_bandage.db` stores user and patient data.

Data flow:
```
Sliders or ESP32 POST -> validation -> Random Forest models -> dashboard
Sensor readings + user question -> RAG (PubMed corpus) -> literature block -> LLM prompt
  -> streamed answer -> __CITATIONS__ marker -> chat UI renders PubMed-linked source pills
```
