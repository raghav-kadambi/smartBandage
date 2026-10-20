"""Curated, verifiable medical literature for the WoundSense smart bandage.

The bandage measures four signals:
- temperature   (body temperature, degC)
- humidity      (relative humidity under the dressing, %)
- heart_rate    (beats per minute)
- blood_pressure (systolic / diastolic, mmHg)

Every paper below is a real PubMed record. Title, authors, journal, year, DOI and abstract
are NOT typed by hand -- they are pulled from PubMed by `data/build_literature_corpus.py`
into `data/literature_corpus.json`. This file only holds our annotations (which sensor a
paper informs, which numbers it reports, and how it links into the knowledge graph).
Every `key_findings` / `sensor_thresholds` entry paraphrases a statement that appears in
that paper's PubMed abstract, so a reviewer can check it by clicking the PubMed link.
"""

import json
from pathlib import Path

CORPUS_FILE = Path(__file__).resolve().parent / "literature_corpus.json"

PAPER_ANNOTATIONS = [
    # ---------------- temperature: local wound / periwound heat ----------------
    {
        "id": "fierheller_2010",
        "pmid": "20631603",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Cross-sectional study of 40 chronic leg ulcers vs 20 controls: increased periwound skin "
            "temperature (measured as the difference to a contralateral site with a handheld infrared "
            "thermometer) was significantly associated with wound infection (ANOVA F = 44.2, P < .001); "
            "the thermometer was reliable (r = 0.939)."
        ),
        "sensor_thresholds": {
            "temperature": {"clinical_rule": "A raised wound-site temperature relative to a matched control site is a quantitative sign of deep/surrounding infection."}
        },
        "clinical_conditions": ["infected"],
        "interventions": ["clinician_review"],
        "cites": ["woo_2009"],
    },
    {
        "id": "mufti_2018",
        "pmid": "29240589",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Prospective study of 100 patients with open wounds comparing four non-contact infrared "
            "thermometers: all devices detected a clinically meaningful 3 degF (and 4 degF) periwound "
            "temperature difference similarly, with strong agreement between devices (r > 0.80)."
        ),
        "sensor_thresholds": {
            "temperature": {"clinical_rule": "A wound-vs-contralateral difference of about 3-4 degF (~1.7-2.2 degC) is used as the clinically meaningful infection signal."}
        },
        "clinical_conditions": ["infected"],
        "interventions": ["clinician_review"],
        "cites": ["fierheller_2010"],
    },
    {
        "id": "woo_2009",
        "pmid": "19717855",
        "biomarkers": ["temperature", "humidity"],
        "key_findings": (
            "Validation of the NERDS/STONEES checklists in 112 patients: wounds with elevated temperature "
            "were eight times more likely to have moderate or heavy bacterial growth, while debris, "
            "increased exudate and friable tissue indicated light growth (critical colonisation)."
        ),
        "sensor_thresholds": {
            "temperature": {"clinical_rule": "Elevated wound temperature carried an ~8x higher likelihood of moderate/heavy bacterial growth."}
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["antimicrobial_dressing", "clinician_review"],
        "cites": [],
    },
    {
        "id": "chanmugam_2017",
        "pmid": "28817451",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Long-wave infrared thermography case series: clinically infected wounds were +4 to +5 degC "
            "warmer than healthy skin, inflamed wounds +1.5 to +2.2 degC, and normal controls +1.1 to "
            "+1.2 degC; temperature returned toward normal after effective antibiotic treatment."
        ),
        "sensor_thresholds": {
            "temperature": {
                "normal_delta_c": [1.1, 1.2],
                "inflammation_delta_c": [1.5, 2.2],
                "infection_delta_c": [4.0, 5.0],
                "clinical_rule": "Wound-to-skin temperature rise of 4-5 degC accompanied clinical infection; 1.5-2.2 degC accompanied inflammation.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing", "healthy"],
        "interventions": ["systemic_antibiotics"],
        "cites": ["fierheller_2010"],
    },
    {
        "id": "nakagami_2010",
        "pmid": "21135794",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Prospective cohort of 35 pressure-ulcer patients: wounds warmer than their periwound skin had "
            "a 2.25x relative risk of delayed healing at 3 weeks (95% CI 1.13-4.47; specificity 0.82), "
            "even when wounds looked the same clinically."
        ),
        "sensor_thresholds": {
            "temperature": {"clinical_rule": "Wound bed warmer than periwound skin predicted delayed healing (RR 2.25)."}
        },
        "clinical_conditions": ["wound_healing", "infected"],
        "interventions": ["clinician_review"],
        "cites": [],
    },
    {
        "id": "dini_2015",
        "pmid": "26479211",
        "biomarkers": ["temperature"],
        "key_findings": (
            "In 24 venous leg ulcers, wound bed temperature after dressing removal ranged 31-35 degC and "
            "increased with the clinical wound bed score; 33 degC is cited as the temperature needed for "
            "normal cellular activity."
        ),
        "sensor_thresholds": {
            "temperature": {"wound_bed_range_c": [31.0, 35.0], "clinical_rule": "Wound bed below ~33 degC is associated with poorer healing status."}
        },
        "clinical_conditions": ["wound_healing"],
        "interventions": ["keep_dressing_warm"],
        "cites": ["mcguiness_2004"],
    },
    {
        "id": "mcguiness_2004",
        "pmid": "15517749",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Across 133 dressing changes, the wound bed averaged 32.7 degC before and 29.9 degC after the "
            "change, taking ~23 minutes to recover; below 33 degC neutrophil, fibroblast and epithelial "
            "cell activity decreases."
        ),
        "sensor_thresholds": {
            "temperature": {"normothermic_threshold_c": 33.0, "clinical_rule": "Each dressing change cools the wound by ~2 degC for ~20-30 minutes."}
        },
        "clinical_conditions": ["wound_healing"],
        "interventions": ["keep_dressing_warm"],
        "cites": [],
    },
    {
        "id": "armstrong_2007",
        "pmid": "18060924",
        "biomarkers": ["temperature"],
        "key_findings": (
            "RCT of 225 high-risk diabetic patients: twice-daily foot skin thermometry with a >4 degF "
            "left-right difference as the alert made ulceration about three times less likely "
            "(4.7% vs 12.2%); ulcerating sites showed a 3.5 degF difference in the preceding week."
        ),
        "sensor_thresholds": {
            "temperature": {"alert_delta_f": 4.0, "clinical_rule": "Temperature difference > 4 degF (~2.2 degC) between matching sites signals inflammation and impending ulceration."}
        },
        "clinical_conditions": ["infected"],
        "interventions": ["offloading"],
        "cites": ["lavery_2004"],
    },
    {
        "id": "lavery_2004",
        "pmid": "15504999",
        "biomarkers": ["temperature"],
        "key_findings": (
            "RCT of 85 high-risk diabetic patients: at-home infrared foot temperature monitoring "
            "(>4 degF difference = at risk) cut foot complications from 20% to 2% over 6 months."
        ),
        "sensor_thresholds": {
            "temperature": {"alert_delta_f": 4.0, "clinical_rule": "> 4 degF over the opposite foot marks inflammation at the measured site."}
        },
        "clinical_conditions": ["infected"],
        "interventions": ["offloading"],
        "cites": [],
    },
    {
        "id": "kanazawa_2016",
        "pmid": "27064366",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Pilot study: a low-cost smartphone-attached thermal camera (FLIR ONE) matched a hospital "
            "thermography device for detecting relative temperature increase (kappa 1.00) in pressure "
            "ulcers and diabetic feet -- low-cost thermal sensing can track subclinical inflammation."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["clinician_review"],
        "cites": ["nakagami_2010"],
    },
    # ---------------- humidity / moisture balance ----------------
    {
        "id": "winter_1962",
        "pmid": "14007593",
        "biomarkers": ["humidity"],
        "key_findings": (
            "Landmark Nature study in pigs comparing scab formation and epithelization speed: wounds kept "
            "moist under occlusive film epithelized faster than air-exposed wounds that formed a dry scab "
            "(no abstract is indexed on PubMed; see the original paper via DOI)."
        ),
        "sensor_thresholds": {
            "humidity": {"clinical_rule": "A moist (high-humidity) wound bed re-epithelizes faster than a dry, scabbed wound."}
        },
        "clinical_conditions": ["wound_healing", "wound_desiccation"],
        "interventions": ["moisture_retentive_dressing"],
        "cites": [],
    },
    {
        "id": "junker_2013",
        "pmid": "24587972",
        "biomarkers": ["humidity"],
        "key_findings": (
            "Review: wet or moist wound treatment promotes re-epithelialization and reduces scarring "
            "compared with dry treatment, and needs continuous monitoring of the wound environment."
        ),
        "sensor_thresholds": {
            "humidity": {"clinical_rule": "Moist/wet environments outperform dry ones for healing; dry wound beds delay closure."}
        },
        "clinical_conditions": ["wound_healing", "wound_desiccation"],
        "interventions": ["moisture_retentive_dressing"],
        "cites": ["winter_1962"],
    },
    {
        "id": "okan_2007",
        "pmid": "17195786",
        "biomarkers": ["humidity"],
        "key_findings": (
            "CME review on moisture balance: wound assessment should match dressing choice to the wound's "
            "moisture level -- neither too dry nor too wet."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["wound_healing", "periwound_maceration", "wound_desiccation"],
        "interventions": ["moisture_retentive_dressing", "absorbent_foam_dressing"],
        "cites": ["winter_1962"],
    },
    {
        "id": "cutting_2002",
        "pmid": "12192848",
        "biomarkers": ["humidity"],
        "key_findings": (
            "Review of how maceration happens: prolonged exposure to moisture softens and breaks down skin "
            "and can complicate healing, especially in chronic wounds."
        ),
        "sensor_thresholds": {
            "humidity": {"clinical_rule": "Persistently saturated (very high humidity) conditions under a dressing risk periwound maceration."}
        },
        "clinical_conditions": ["periwound_maceration"],
        "interventions": ["absorbent_foam_dressing"],
        "cites": [],
    },
    # ---------------- smart bandage engineering ----------------
    {
        "id": "mostafalu_2018",
        "pmid": "29978547",
        "biomarkers": ["temperature"],
        "key_findings": (
            "Flexible smart dressing with integrated temperature (and pH) sensors, a microcontroller that "
            "processes readings in real time, and a heater-triggered drug release for closed-loop, "
            "on-demand treatment of chronic wounds."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["antimicrobial_dressing"],
        "cites": ["derakhshandeh_2018"],
    },
    {
        "id": "derakhshandeh_2018",
        "pmid": "30197225",
        "biomarkers": ["temperature", "humidity"],
        "key_findings": (
            "Review of smart bandages: chronic wounds are dynamic, so actively monitoring the wound "
            "environment and pairing it with controlled drug delivery is key to timely therapy."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["antimicrobial_dressing", "moisture_retentive_dressing"],
        "cites": [],
    },
    # ---------------- systemic vital signs: heart rate, BP, fever ----------------
    {
        "id": "bone_1992",
        "pmid": "1303622",
        "biomarkers": ["temperature", "heart_rate"],
        "key_findings": (
            "ACCP/SCCM consensus that defined the systemic inflammatory response syndrome (SIRS) with "
            "physiologic parameters, and defined sepsis, septic shock and hypotension. The full text sets the SIRS "
            "criteria used worldwide: temperature > 38 or < 36 degC, heart rate > 90 bpm, respiratory rate > 20, "
            "abnormal white cell count."
        ),
        "sensor_thresholds": {
            "temperature": {"fever_c": 38.0, "hypothermia_c": 36.0, "clinical_rule": "SIRS temperature criterion: > 38 degC or < 36 degC."},
            "heart_rate": {"tachycardia_bpm": 90, "clinical_rule": "SIRS heart-rate criterion: > 90 beats/min."},
        },
        "clinical_conditions": ["infected", "systemic_infection"],
        "interventions": ["urgent_medical_review"],
        "cites": [],
    },
    {
        "id": "singer_2016",
        "pmid": "26903338",
        "biomarkers": ["blood_pressure"],
        "key_findings": (
            "Sepsis-3: sepsis is life-threatening organ dysfunction from a dysregulated response to infection. "
            "Outside the ICU, qSOFA flags high-risk patients using systolic BP <= 100 mmHg, respiratory rate "
            ">= 22/min and altered mentation; septic shock needs vasopressors to keep MAP >= 65 mmHg."
        ),
        "sensor_thresholds": {
            "blood_pressure": {"qsofa_sbp_mmhg": 100, "shock_map_mmhg": 65, "clinical_rule": "Systolic BP <= 100 mmHg is one of the qSOFA criteria for sepsis risk."}
        },
        "clinical_conditions": ["systemic_infection"],
        "interventions": ["urgent_medical_review"],
        "cites": ["bone_1992", "seymour_2016"],
    },
    {
        "id": "seymour_2016",
        "pmid": "26903335",
        "biomarkers": ["blood_pressure", "heart_rate", "temperature"],
        "key_findings": (
            "Validated sepsis criteria in 148,907 encounters with suspected infection: outside the ICU qSOFA "
            "(including systolic BP <= 100 mmHg) predicted mortality with AUROC 0.81 vs 0.76 for SIRS; inside "
            "the ICU, SIRS (0.64) and qSOFA (0.66) were weaker than SOFA (0.74)."
        ),
        "sensor_thresholds": {
            "blood_pressure": {"qsofa_sbp_mmhg": 100, "clinical_rule": "qSOFA >= 2 carried a 3- to 14-fold rise in hospital mortality."}
        },
        "clinical_conditions": ["systemic_infection"],
        "interventions": ["urgent_medical_review"],
        "cites": ["bone_1992"],
    },
    {
        "id": "kaukonen_2015",
        "pmid": "25776936",
        "biomarkers": ["heart_rate", "temperature"],
        "key_findings": (
            "In 109,663 ICU patients with infection and organ failure, 1 in 8 did not meet >= 2 SIRS "
            "criteria; mortality rose linearly with each extra SIRS criterion (OR 1.13 each) with no step "
            "at two -- vital-sign criteria are informative but imperfect on their own."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["systemic_infection"],
        "interventions": ["urgent_medical_review"],
        "cites": ["bone_1992"],
    },
    {
        "id": "churpek_2017",
        "pmid": "27649072",
        "biomarkers": ["heart_rate", "blood_pressure", "temperature"],
        "key_findings": (
            "In 30,677 infected ward/ED patients, vital-sign scores predicted death: NEWS AUC 0.77, MEWS 0.73, "
            "qSOFA 0.69, SIRS 0.65. Patients met >= 2 SIRS criteria about 17 hours before deterioration."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["systemic_infection", "infected"],
        "interventions": ["urgent_medical_review"],
        "cites": ["seymour_2016", "smith_2013"],
    },
    {
        "id": "smith_2013",
        "pmid": "23295778",
        "biomarkers": ["heart_rate", "blood_pressure", "temperature"],
        "key_findings": (
            "Across 198,755 vital-sign sets, the National Early Warning Score (NEWS) -- built from routine "
            "vitals including heart rate, systolic BP and temperature -- discriminated death within 24 h "
            "with AUROC 0.894, better than 33 other early-warning scores."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["systemic_infection"],
        "interventions": ["urgent_medical_review"],
        "cites": [],
    },
    {
        "id": "reyna_2020",
        "pmid": "31939789",
        "biomarkers": ["heart_rate", "blood_pressure", "temperature"],
        "key_findings": (
            "Describes the PhysioNet/CinC 2019 Challenge: over 60,000 ICU patients with hourly vitals and labs, "
            "labelled with Sepsis-3 onset. This is the official open dataset WoundSense uses as its external "
            "test set; generalising across hospital systems was the main difficulty."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["systemic_infection"],
        "interventions": [],
        "cites": ["singer_2016", "seymour_2016"],
    },
    # ---------------- wound infection guidelines linking local + systemic signs ----------------
    {
        "id": "lipsky_2012",
        "pmid": "22619242",
        "biomarkers": ["temperature", "heart_rate"],
        "key_findings": (
            "IDSA guideline: a wound is infected when >= 2 classic signs of inflammation (including warmth) or "
            "pus are present; infections are graded mild, moderate, or severe -- severe meaning accompanied by "
            "systemic signs or metabolic perturbations."
        ),
        "sensor_thresholds": {
            "temperature": {"clinical_rule": "Local warmth is one of the classic inflammatory signs that define wound infection."}
        },
        "clinical_conditions": ["infected", "systemic_infection"],
        "interventions": ["systemic_antibiotics", "clinician_review"],
        "cites": ["bone_1992"],
    },
    {
        "id": "senneville_2023",
        "pmid": "37779457",
        "biomarkers": ["temperature", "heart_rate"],
        "key_findings": (
            "IWGDF/IDSA 2023 GRADE-based update for diabetes-related foot infections (149 studies): keeps "
            "clinical diagnosis from local inflammatory signs and systemic findings for severity grading."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["infected", "systemic_infection"],
        "interventions": ["systemic_antibiotics", "clinician_review"],
        "cites": ["lipsky_2012"],
    },
    # ---------------- blood pressure / heart rate and healing speed ----------------
    {
        "id": "ahmed_2011",
        "pmid": "21853091",
        "biomarkers": ["blood_pressure"],
        "key_findings": (
            "Propensity-matched study of 120 hip-arthroplasty patients: hypertensive patients (mean SBP 150 "
            "mmHg) needed 3.79 days for a dry wound vs 2.03 days for normotensive patients (mean SBP 120 "
            "mmHg); hypertension raised the odds of prolonged wound discharge (OR 1.65)."
        ),
        "sensor_thresholds": {
            "blood_pressure": {"hypertensive_sbp_mean": 150.1, "normotensive_sbp_mean": 120.3, "clinical_rule": "Hypertension is associated with slower wound drying and higher infection risk."}
        },
        "clinical_conditions": ["wound_healing", "delayed_healing"],
        "interventions": ["blood_pressure_control"],
        "cites": [],
    },
    {
        "id": "guo_2010",
        "pmid": "20139336",
        "biomarkers": ["heart_rate", "blood_pressure"],
        "key_findings": (
            "Review of factors that impair wound healing across hemostasis, inflammation, proliferation and "
            "remodeling: oxygenation (perfusion), infection, age, stress, diabetes, obesity, medication, "
            "smoking and nutrition."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["wound_healing", "delayed_healing", "infected"],
        "interventions": ["blood_pressure_control", "stress_reduction"],
        "cites": ["gouin_2011"],
    },
    {
        "id": "gouin_2011",
        "pmid": "21094925",
        "biomarkers": ["heart_rate"],
        "key_findings": (
            "Review of experimental wound models: psychological stress measurably slows wound repair through "
            "physiological stress responses and by promoting health-damaging behaviours."
        ),
        "sensor_thresholds": {},
        "clinical_conditions": ["delayed_healing"],
        "interventions": ["stress_reduction"],
        "cites": [],
    },
]


def _load_papers():
    """Merge PubMed metadata (source of truth) with our annotations."""
    if not CORPUS_FILE.exists():
        raise FileNotFoundError(
            f"{CORPUS_FILE.name} missing -- run `python data/build_literature_corpus.py` once to pull it from PubMed."
        )
    corpus = json.loads(CORPUS_FILE.read_text(encoding="utf-8"))
    papers = []
    for ann in PAPER_ANNOTATIONS:
        rec = corpus[ann["pmid"]]
        papers.append({**rec, **ann, "abstract": rec["abstract"] or ann["key_findings"]})
    return papers


PAPERS = _load_papers() if CORPUS_FILE.exists() else []

# Biomarker reference definitions. Ranges are for an adult at rest; sources are listed
# per biomarker so the knowledge-graph inspector can show where each number comes from.
BIOMARKER_SPECS = {
    "temperature": {
        "unit": "°C",
        "name": "Body Temperature",
        "description": "Body temperature from the bandage (skin reading calibrated to core-equivalent on the ESP32). Fever or hypothermia are systemic signs of infection; local wound heat is a classic sign of infection.",
        "healthy_range": [36.1, 37.5],
        "healing_range": [36.5, 37.8],
        "warning_threshold": 38.0,
        "critical_threshold": 39.0,
        "pathophysiology": "Infection releases pyrogenic cytokines that raise the hypothalamic set-point (fever); local inflammation increases blood flow and heat at the wound.",
        "sources": ["bone_1992", "fierheller_2010", "chanmugam_2017"],
    },
    "humidity": {
        "unit": "%",
        "name": "Sub-Bandage Relative Humidity",
        "description": "Moisture balance under the dressing. A moist wound bed heals faster than a dry one; persistent saturation from heavy drainage macerates the surrounding skin.",
        "healthy_range": [40.0, 65.0],
        "healing_range": [65.0, 85.0],
        "warning_low": 40.0,
        "warning_high": 90.0,
        "pathophysiology": "Dry wounds form a scab that slows epithelial migration; excess fluid softens and breaks down periwound skin.",
        "sources": ["winter_1962", "junker_2013", "cutting_2002"],
    },
    "heart_rate": {
        "unit": "bpm",
        "name": "Heart Rate",
        "description": "Resting pulse. Tachycardia above 90 bpm is a SIRS criterion and an early sign of systemic spread of infection.",
        "healthy_range": [60.0, 90.0],
        "healing_range": [60.0, 95.0],
        "warning_threshold": 90.0,
        "critical_threshold": 120.0,
        "pathophysiology": "Fever and inflammatory vasodilation increase metabolic demand and lower vascular resistance, so the heart beats faster to keep up perfusion.",
        "sources": ["bone_1992", "churpek_2017", "smith_2013"],
    },
    "blood_pressure": {
        "unit": "mmHg",
        "name": "Blood Pressure (Systolic / Diastolic)",
        "description": "Systolic and diastolic pressure. Systolic <= 100 mmHg is a qSOFA sepsis-risk criterion; sustained hypertension is associated with slower wound healing.",
        "healthy_range": [90.0, 130.0],
        "healing_range": [100.0, 139.0],
        "warning_threshold": 140.0,
        "warning_low": 100.0,
        "critical_threshold": 90.0,
        "pathophysiology": "Sepsis-driven vasodilation drops pressure and tissue perfusion; chronic hypertension damages small vessels and delays wound drying.",
        "sources": ["singer_2016", "seymour_2016", "ahmed_2011"],
    },
}

CLINICAL_STATES = {
    "healthy": {
        "label": "Healthy / Closed Skin",
        "color": "#2f8f5b",
        "description": "Normal body temperature, resting heart rate and blood pressure, with a dry-to-normal skin microclimate.",
    },
    "wound_healing": {
        "label": "Active Healing",
        "color": "#2f6f62",
        "description": "Moist, balanced wound bed with normal vital signs; mild local warmth from normal inflammation can be present.",
    },
    "infected": {
        "label": "Local Wound Infection",
        "color": "#d9483f",
        "description": "Classic inflammatory signs (warmth, swelling, pain, pus) at the wound, often with wetter dressings from increased drainage.",
    },
    "systemic_infection": {
        "label": "Systemic Infection / Sepsis Risk",
        "color": "#a12d25",
        "description": "Infection spreading beyond the wound: fever or hypothermia, tachycardia, and in severe cases falling blood pressure.",
    },
    "delayed_healing": {
        "label": "Delayed Healing",
        "color": "#7b3fa8",
        "description": "Healing slower than expected, linked to factors such as hypertension, stress, poor perfusion or a cold wound bed.",
    },
    "periwound_maceration": {
        "label": "Periwound Maceration",
        "color": "#c8862b",
        "description": "Softened, breaking-down skin around the wound from prolonged exposure to moisture.",
    },
    "wound_desiccation": {
        "label": "Wound Desiccation",
        "color": "#8c6b38",
        "description": "A dried-out wound bed forming a scab that slows epithelial migration.",
    },
}

INTERVENTIONS = {
    "clinician_review": {
        "name": "Clinician Wound Review",
        "target_states": ["infected", "delayed_healing"],
        "description": "Bedside assessment of inflammatory signs, swab/culture if needed, and a treatment decision.",
    },
    "urgent_medical_review": {
        "name": "Urgent Medical Review",
        "target_states": ["systemic_infection"],
        "description": "Same-day escalation when vital signs suggest the infection may be spreading (fever, tachycardia, low BP).",
    },
    "systemic_antibiotics": {
        "name": "Systemic Antibiotics",
        "target_states": ["infected", "systemic_infection"],
        "description": "Prescribed antibiotic therapy for clinically infected wounds, guided by severity and culture.",
    },
    "antimicrobial_dressing": {
        "name": "Antimicrobial Dressing",
        "target_states": ["infected"],
        "description": "Silver-, iodine- or PHMB-containing dressings that reduce bacterial burden at the wound surface.",
    },
    "moisture_retentive_dressing": {
        "name": "Moisture-Retentive Dressing",
        "target_states": ["wound_desiccation", "wound_healing"],
        "description": "Hydrogel, hydrocolloid or film dressings that keep the wound bed moist.",
    },
    "absorbent_foam_dressing": {
        "name": "Absorbent Foam Dressing",
        "target_states": ["periwound_maceration"],
        "description": "Absorbs excess fluid to protect surrounding skin while keeping the bed moist.",
    },
    "keep_dressing_warm": {
        "name": "Minimise Dressing-Change Cooling",
        "target_states": ["delayed_healing", "wound_healing"],
        "description": "Limit how often and how long the wound is exposed so the bed stays near 33 degC.",
    },
    "offloading": {
        "name": "Pressure Offloading / Rest",
        "target_states": ["infected", "delayed_healing"],
        "description": "Reduce load and activity on a warm, inflamed site until temperature normalises.",
    },
    "blood_pressure_control": {
        "name": "Blood Pressure Management",
        "target_states": ["delayed_healing"],
        "description": "Keep hypertension under control, which is associated with faster wound drying.",
    },
    "stress_reduction": {
        "name": "Stress Reduction",
        "target_states": ["delayed_healing"],
        "description": "Sleep, pain control and stress management, since stress measurably slows wound repair.",
    },
}
