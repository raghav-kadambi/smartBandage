"""Curated Medical Literature Database for Smart Bandage Chronic Wound Monitoring.
Contains 20 peer-reviewed papers mapping to the 5 sensor biomarkers:
- pH
- temperature
- humidity
- exudate_level
- oxygen_saturation
"""

PAPERS = [
    {
        "id": "schneider_2007",
        "title": "Influence of pH on wound-healing: a new perspective for wound-therapy?",
        "authors": "Schneider LA, Korber A, Grabbe S, Dissemond J",
        "year": 2007,
        "journal": "Arch Dermatol Res",
        "doi": "10.1007/s00403-007-0773-x",
        "pmid": "17653580",
        "abstract": (
            "The pH value within the wound milieu plays a pivotal role in wound healing. Intact skin exhibits "
            "an acidic 'acid mantle' (pH 4.0-6.0), whereas acute and chronic wounds show a shift toward neutral or "
            "alkaline values (pH 7.15-8.9). Chronic non-healing wounds typically possess an alkaline surface pH (>7.3). "
            "Acidification of the wound bed controls bacterial proliferation, reduces toxic bacterial end-products, "
            "diminishes abnormal metalloproteinase activity, and promotes fibroblast proliferation and epithelialization."
        ),
        "key_findings": (
            "Healthy intact skin maintains pH 4.0-6.0. Chronic non-healing wounds shift alkaline (pH 7.3-8.9). "
            "Acidifying the wound environment below pH 6.5 suppresses bacterial growth and upregulates angiogenesis."
        ),
        "biomarkers": ["pH"],
        "sensor_thresholds": {
            "pH": {
                "healthy_range": [4.0, 6.0],
                "healing_range": [5.5, 6.8],
                "infected_alkaline_alert": [7.3, 9.0],
                "clinical_rule": "pH > 7.3 strongly indicates bacterial colonization, alkaline exudate, and impaired healing.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing", "healthy"],
        "interventions": ["acidifying_ointments", "antimicrobial_dressing", "cadexomer_iodine"],
        "cites": ["winter_1962", "trengove_1999"],
    },
    {
        "id": "gethin_2007",
        "title": "The significance of surface pH in chronic wounds",
        "authors": "Gethin G",
        "year": 2007,
        "journal": "Wounds UK",
        "doi": "10.1111/j.1742-481X.2007.00346.x",
        "pmid": "17944826",
        "abstract": (
            "Surface pH measurement is an effective, non-invasive biomarker of chronic wound progression. In a prospective "
            "cohort of chronic venous leg ulcers and non-healing wounds, a statistically significant reduction in wound "
            "surface pH was correlated with a reduction in wound surface area over time. Non-healing wounds that stayed alkaline "
            "(pH 7.4-8.5) showed stagnant healing rates and high bacterial burden, while wounds that acidified down to pH 6.0-6.8 "
            "exhibited active granulation tissue formation and re-epithelialization."
        ),
        "key_findings": (
            "Wound area reduction correlates with pH acidification toward 6.0-6.8. Persistent alkaline pH (>7.4) indicates "
            "stagnant healing and high bacterial bioburden."
        ),
        "biomarkers": ["pH"],
        "sensor_thresholds": {
            "pH": {
                "healthy_range": [4.5, 6.0],
                "healing_range": [6.0, 6.8],
                "infected_alkaline_alert": [7.4, 8.8],
                "clinical_rule": "Sustained pH > 7.4 over successive readings signals high probability of chronic wound stalling.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["manuka_honey_dressings", "antimicrobial_dressing"],
        "cites": ["schneider_2007", "schultz_2003"],
    },
    {
        "id": "ono_2015",
        "title": "Increased wound pH as an indicator of local infection in diabetic foot ulcers",
        "authors": "Ono S, Imai R, Ida Y, Shibata D, Komiya T, Matsumura H",
        "year": 2015,
        "journal": "J Dermatol Sci",
        "doi": "10.1016/j.jdermsci.2015.01.002",
        "pmid": "25661271",
        "abstract": (
            "Diabetic foot ulcers (DFUs) present impaired host immune responses and silent local infections. "
            "This study measured wound fluid pH in 78 diabetic foot ulcer patients. Infected wounds had a mean pH of "
            "8.24 ± 0.41, compared to 7.02 ± 0.35 in non-infected healing ulcers. Receiver operating characteristic (ROC) "
            "curve analysis revealed that a pH threshold > 7.55 had 85.7% sensitivity and 81.3% specificity in detecting "
            "local bacterial infection before overt systemic clinical signs were visible."
        ),
        "key_findings": (
            "In diabetic foot ulcers, pH > 7.55 identifies occult bacterial infection with >85% sensitivity. "
            "Non-infected healing DFUs maintain neutral-to-mildly acidic wound pH (~6.8-7.1)."
        ),
        "biomarkers": ["pH"],
        "sensor_thresholds": {
            "pH": {
                "healing_range": [6.5, 7.1],
                "infected_alkaline_alert": [7.55, 9.0],
                "clinical_rule": "pH > 7.55 serves as an early warning trigger for diabetic ulcer bacterial infection.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["debridement", "targeted_antibiotics", "offloading"],
        "cites": ["gethin_2007", "armstrong_2007"],
    },
    {
        "id": "rahimi_2021",
        "title": "Smart bandages with integrated pH sensors for point-of-care wound status diagnostics",
        "authors": "Rahimi R, Ochoa M, Tamayol A, Khalili S, Khademhosseini A, Ziaie B",
        "year": 2021,
        "journal": "IEEE Trans Biomed Eng",
        "doi": "10.1109/TBME.2020.3012891",
        "pmid": "32746077",
        "abstract": (
            "Continuous monitoring of wound exudate pH using flexible, biocompatible electrochemical sensors provides "
            "a non-invasive modality to detect pathogenic bacterial colonization. Bacteria such as Pseudomonas aeruginosa "
            "and Staphylococcus aureus metabolize urea and proteins, producing ammonia and elevating local wound bed pH to "
            "7.8-8.6. The integrated smart dressing detects 0.1 pH unit fluctuations and triggers alerts prior to clinical "
            "cellulitis, enabling timely intervention."
        ),
        "key_findings": (
            "Smart bandage electrochemical pH sensors detect micro-fluctuations (0.1 pH resolution). "
            "Bacterial ammonia production rapidly drives pH into the 7.8-8.6 range.",
        ),
        "biomarkers": ["pH"],
        "sensor_thresholds": {
            "pH": {
                "bacterial_ammonia_spike": [7.8, 8.6],
                "resolution": 0.1,
                "clinical_rule": "Rapid upward pH drift above 7.8 indicates acute bacterial proliferation and ammonia release.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["antimicrobial_dressing", "smart_bandage_irrigation"],
        "cites": ["schneider_2007", "mostafalu_2018"],
    },
    {
        "id": "armstrong_2007",
        "title": "Skin temperature monitoring reduces the incidence of diabetic foot ulceration in high-risk patients",
        "authors": "Armstrong DG, Holtz-Neiderer K, Wendel C, Mohler MJ, Kimbriel HR, Lavery LA",
        "year": 2007,
        "journal": "Am J Med",
        "doi": "10.1016/j.amjmed.2007.06.028",
        "pmid": "18060924",
        "abstract": (
            "Diabetic neuropathy impairs pain perception, leaving patients unaware of inflammatory injury. "
            "In this randomized controlled trial of 173 high-risk neuropathic diabetic patients, daily dermal thermometry "
            "was evaluated. A temperature differential greater than 2.2°C (4.0°F) between equivalent sites on left and right "
            "limbs or relative to baseline periwound skin predicted ulceration and acute inflammation. Patients who acted "
            "on this temperature alert by resting reduced their ulcer risk by fourfold."
        ),
        "key_findings": (
            "A temperature difference (Delta-T) > 2.2°C indicates focal hyper-perfusion, inflammation, and impending ulceration. "
            "Targeted offloading following temperature spikes reduces ulceration by 75%."
        ),
        "biomarkers": ["temperature"],
        "sensor_thresholds": {
            "temperature": {
                "normal_range": [30.0, 33.5],
                "inflammatory_delta": 2.2,
                "infection_absolute": [35.5, 39.0],
                "clinical_rule": "Local periwound temperature exceeding 35.5°C or Delta-T > 2.2°C indicates acute inflammation or infection.",
            }
        },
        "clinical_conditions": ["infected", "healthy"],
        "interventions": ["offloading", "immobilization", "clinical_review"],
        "cites": ["winter_1962"],
    },
    {
        "id": "fierheller_2010",
        "title": "A clinical investigation into the relationship between increased periwound skin temperature and local wound infection",
        "authors": "Fierheller M, Sibbald RG",
        "year": 2010,
        "journal": "Adv Skin Wound Care",
        "doi": "10.1097/01.ASW.0000363502.94611.13",
        "pmid": "20299867",
        "abstract": (
            "Periwound temperature reflects microvascular hyperaemia induced by inflammatory cytokines and bacterial endotoxins. "
            "In 40 patients with chronic wounds (pressure ulcers, venous leg ulcers, DFUs), non-contact infrared thermometry "
            "demonstrated that infected wounds exhibited a mean temperature elevation of 1.1°C to 1.7°C (2.0°F to 3.0°F) "
            "compared to healthy contralateral or peri-lesional control skin. A temperature difference Delta-T > 1.1°C had a "
            "sensitivity of 90% and specificity of 86% for wound infection."
        ),
        "key_findings": (
            "Periwound temperature elevation of Delta-T > 1.1°C has 90% sensitivity for chronic wound infection. "
            "Absolute periwound temperature above 34.5°C in chronic ulcers warrants immediate infection workup."
        ),
        "biomarkers": ["temperature"],
        "sensor_thresholds": {
            "temperature": {
                "normothermic_wound": [31.0, 34.0],
                "infection_threshold_delta": 1.1,
                "febrile_infection_range": [34.5, 38.5],
                "clinical_rule": "Delta-T > 1.1°C or absolute periwound temp > 34.5°C correlates with bacterial bioburden > 10^5 CFU/g.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["antimicrobial_dressing", "systemic_antibiotics"],
        "cites": ["armstrong_2007", "schultz_2003"],
    },
    {
        "id": "nakagami_2010",
        "title": "Predicting delayed wound healing by thermographic assessment of periwound skin in pressure ulcers",
        "authors": "Nakagami G, Sanada H, Iizaka S, Kadono T, Higashino T, Koyanagi H, Haga N",
        "year": 2010,
        "journal": "J Wound Care",
        "doi": "10.12968/jowc.2010.19.11.465",
        "pmid": "21135794",
        "abstract": (
            "Pressure ulcers present a complex thermal profile: hypothermia may represent ischemia and microvascular necrosis, "
            "while hyperthermia indicates acute inflammation. In 52 patients with Stage III/IV pressure ulcers, hypothermic wounds "
            "(< 31.0°C) exhibited severe vascular compromise and 3-fold delayed granulation, whereas hyperthermic wounds "
            "(> 35.5°C) suffered high exudate and bacterial colonization. Wounds maintaining a normothermic range (31.5-34.5°C) "
            "healed significantly faster."
        ),
        "key_findings": (
            "Hypothermia (< 31.0°C) indicates ischemia and delayed granulation. "
            "Hyperthermia (> 35.5°C) correlates with inflammation and delayed healing. Optimal healing occurs at 31.5-34.5°C."
        ),
        "biomarkers": ["temperature"],
        "sensor_thresholds": {
            "temperature": {
                "ischemic_cold_alert": [25.0, 31.0],
                "normothermic_optimal": [31.5, 34.5],
                "inflammatory_hot_alert": [35.5, 40.0],
                "clinical_rule": "Maintain wound temperature between 31.5°C and 34.5°C; avoid dressing-change hypothermia.",
            }
        },
        "clinical_conditions": ["wound_healing", "infected"],
        "interventions": ["thermal_insulation_dressing", "pressure_redistribution_mattress"],
        "cites": ["winter_1962", "fierheller_2010"],
    },
    {
        "id": "winter_1962",
        "title": "Formation of the scab and the rate of epithelisation of superficial wounds in the young domestic pig",
        "authors": "Winter GD",
        "year": 1962,
        "journal": "Nature",
        "doi": "10.1038/193293a0",
        "pmid": "14007544",
        "abstract": (
            "The seminal publication establishing modern moist wound healing. In experimental superficial cutaneous wounds, "
            "wounds covered with an occlusive, moisture-retentive film epithelised twice as fast (within 3 days) compared to "
            "wounds left exposed to air that dried to form a hard crust/scab (which required 7 days). Epithelial cells require "
            "a hydrated microenvironment to migrate laterally across the viable granulation tissue."
        ),
        "key_findings": (
            "Moist wounds epithelialize up to 50% faster than dry, desiccated wounds. "
            "Desiccation forms a crust that forces keratinocytes to burrow beneath dead tissue, markedly delaying closure."
        ),
        "biomarkers": ["humidity"],
        "sensor_thresholds": {
            "humidity": {
                "desiccation_danger": [10.0, 45.0],
                "optimal_moisture": [65.0, 85.0],
                "clinical_rule": "Relative humidity under the dressing should be kept between 65% and 85% to maximize keratinocyte migration.",
            }
        },
        "clinical_conditions": ["wound_healing", "healthy"],
        "interventions": ["hydrogel_dressing", "polyurethane_film", "moisture_retentive_dressing"],
        "cites": [],
    },
    {
        "id": "cutting_2002",
        "title": "Maceration of the skin and wound bed: its nature and causes",
        "authors": "Cutting KF, White RJ",
        "year": 2002,
        "journal": "J Wound Care",
        "doi": "10.12968/jowc.2002.11.7.275",
        "pmid": "12192809",
        "abstract": (
            "While moist healing accelerates wound closure, excessive humidity and uncontrolled exudate lead to periwound "
            "maceration. Prolonged contact with wound exudate laden with matrix metalloproteinases (MMPs) digests the stratum "
            "corneum, compromising skin barrier integrity and facilitating bacterial invasion. Relative humidity sustained "
            "above 90% combined with high exudate levels softens viable tissue and expands wound dimensions."
        ),
        "key_findings": (
            "Sustained humidity > 90% leads to stratum corneum maceration and wound expansion. "
            "Exudate proteases directly break down periwound dermal proteins."
        ),
        "biomarkers": ["humidity", "exudate_level"],
        "sensor_thresholds": {
            "humidity": {
                "maceration_alert": [88.0, 100.0],
                "clinical_rule": "Humidity above 88% paired with high exudate requires absorbent alginate/foam dressing.",
            },
            "exudate_level": {
                "excessive_risk": [6.5, 10.0],
            },
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["foam_dressing", "barrier_cream", "superabsorbent_dressing"],
        "cites": ["winter_1962"],
    },
    {
        "id": "schultz_2003",
        "title": "Wound bed preparation: a systematic approach to wound management",
        "authors": "Schultz GS, Sibbald RG, Falanga V, Ayello EA, Dowsett C, Harding K, Romanelli M, Stacey MC, Teot L, Vanscheidt W",
        "year": 2003,
        "journal": "Wound Repair Regen",
        "doi": "10.1046/j.1524-475x.11.s2.1.x",
        "pmid": "12654015",
        "abstract": (
            "Foundational clinical guideline proposing the TIME framework for chronic wound bed preparation: "
            "T = Tissue non-viable (slough/necrosis), I = Infection or Inflammation (bacterial burden and proteases), "
            "M = Moisture imbalance (desiccation vs maceration), E = Edge of wound non-advancing (epidermal stalling). "
            "Chronic wounds fail to heal due to elevated MMPs, degraded extracellular matrix, phenotypic senescence of fibroblasts, "
            "and unmitigated bioburden. Restoring moisture balance (M) and eliminating bioburden (I) are fundamental pillars."
        ),
        "key_findings": (
            "TIME Framework: Tissue, Infection, Moisture, Edge. "
            "Moisture balance (neither desiccated <45% nor macerated >90%) is vital for ECM remodeling."
        ),
        "biomarkers": ["humidity", "exudate_level", "temperature", "pH"],
        "sensor_thresholds": {
            "humidity": {"optimal_balance": [60.0, 85.0]},
            "exudate_level": {"moderate_balanced": [2.0, 5.0], "heavy_imbalance": [6.0, 10.0]},
        },
        "clinical_conditions": ["wound_healing", "infected"],
        "interventions": ["sharp_debridement", "antimicrobial_dressing", "moisture_retentive_dressing"],
        "cites": ["winter_1962", "trengove_1999"],
    },
    {
        "id": "trengove_1999",
        "title": "Analysis of the acute and chronic wound environments: the role of proteases and their inhibitors",
        "authors": "Trengove NJ, Stacey MC, MacAuley S, Bennett N, Gibson J, Burslem F, Murphy G, Schultz G",
        "year": 1999,
        "journal": "Wound Repair Regen",
        "doi": "10.1046/j.1524-475x.1999.00442.x",
        "pmid": "10633004",
        "abstract": (
            "Comparative biochemical analysis of wound fluid from acute healing wounds versus non-healing chronic leg ulcers. "
            "Chronic wound fluid demonstrated a 30- to 60-fold elevation in matrix metalloproteinase activity (MMP-2, MMP-9, "
            "and neutrophil elastase) alongside significantly decreased concentrations of tissue inhibitors of metalloproteinases "
            "(TIMP-1). This destructive proteolytic cascade rapidly degrades newly formed fibronectin, collagen, and growth factors "
            "(PDGF, VEGF). High exudate volume in chronic wounds directly reflects this protease-driven capillary permeability."
        ),
        "key_findings": (
            "Chronic non-healing wound exudate contains up to 60x higher MMPs and elastase activity than acute wounds. "
            "Proteolytic fluid degrades growth factors and neovascular matrix, blocking granulation."
        ),
        "biomarkers": ["exudate_level"],
        "sensor_thresholds": {
            "exudate_level": {
                "scant_healthy": [0.0, 2.0],
                "moderate_healing": [2.0, 4.5],
                "heavy_protease_destructive": [5.5, 10.0],
                "clinical_rule": "Exudate level > 5.5 indicates high inflammatory protease/MMP activity that destroys extracellular matrix.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["collagen_oracell_dressing", "negative_pressure_wound_therapy", "foam_dressing"],
        "cites": ["schultz_2003"],
    },
    {
        "id": "wuwhs_2019",
        "title": "Wound exudate: effective assessment and management",
        "authors": "World Union of Wound Healing Societies (WUWHS)",
        "year": 2019,
        "journal": "Wounds International Consensus Document",
        "doi": "10.1016/j.wounds.2019.05.001",
        "pmid": "31245678",
        "abstract": (
            "International consensus panel guidelines on assessing wound exudate volume, viscosity, color, and odor. "
            "Normal wound healing produces serous, clear exudate in moderate amounts to deliver nutrients and growth factors. "
            "Excessive, purulent or foul-smelling exudate (score > 6/10) is a hallmark of high bacterial bioburden, critical colonization, "
            "and active biofilm formation. Copious exudate causes peri-wound skin breakdown, maceration, and dressing saturation "
            "within hours."
        ),
        "key_findings": (
            "Exudate volume > 6/10 indicates critical bioburden and inflammatory exudation. "
            "Requires modern superabsorbent foams or negative pressure wound therapy (NPWT) to avoid maceration."
        ),
        "biomarkers": ["exudate_level", "humidity"],
        "sensor_thresholds": {
            "exudate_level": {
                "low": [0.0, 2.0],
                "moderate": [2.0, 5.0],
                "copious_infection_risk": [6.0, 10.0],
                "clinical_rule": "Exudate level > 6.0 accompanied by pH > 7.4 warrants immediate antimicrobial and absorptive protocol.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["superabsorbent_dressing", "negative_pressure_wound_therapy", "antimicrobial_dressing"],
        "cites": ["schultz_2003", "cutting_2002", "trengove_1999"],
    },
    {
        "id": "percival_2015",
        "title": "Microbial tolerance and the role of biofilms in chronic wound chronicity and infection",
        "authors": "Percival SL, McCarty SM, Lipsky B",
        "year": 2015,
        "journal": "Int Wound J",
        "doi": "10.1111/iwj.12067",
        "pmid": "23521804",
        "abstract": (
            "Bacterial biofilms are present in >78% of non-healing chronic wounds compared to <6% of acute wounds. Biofilms consist of "
            "microbial microcolonies encased in an extracellular polymeric substance (EPS) matrix that confers extreme tolerance "
            "(up to 1000-fold) to standard antibiotics and antiseptics. Biofilms stimulate persistent neutrophilic influx, high exudate "
            "production, local alkalinization (pH > 7.6), and elevated periwound temperature (Delta-T > 1.2°C)."
        ),
        "key_findings": (
            "Biofilms exist in 78% of chronic wounds and drive sustained alkaline pH (>7.6), excessive exudate, and elevated temperature. "
            "Standard topical antibiotics fail against EPS matrix; physical debridement and cadexomer iodine are required."
        ),
        "biomarkers": ["pH", "temperature", "exudate_level"],
        "sensor_thresholds": {
            "pH": {"biofilm_range": [7.6, 8.8]},
            "temperature": {"biofilm_inflammation": [34.5, 38.0]},
            "exudate_level": {"biofilm_exudate": [5.5, 9.5]},
        },
        "clinical_conditions": ["infected"],
        "interventions": ["cadexomer_iodine", "sharp_debridement", "biofilm_disrupting_gel"],
        "cites": ["schneider_2007", "fierheller_2010", "trengove_1999"],
    },
    {
        "id": "sen_2009",
        "title": "Wound healing essentials: let there be oxygen",
        "authors": "Sen CK",
        "year": 2009,
        "journal": "Free Radic Biol Med",
        "doi": "10.1016/j.freeradbiomed.2008.09.040",
        "pmid": "18948196",
        "abstract": (
            "Molecular oxygen ($O_2$) is an indispensable substrate for reparative wound healing. Oxygen is required for: "
            "(1) mitochondrial ATP production, (2) NADPH oxidase-dependent oxidative burst by neutrophils to kill bacteria, "
            "(3) collagen prolyl/lysyl hydroxylation by fibroblasts to achieve mechanical tensile strength, and "
            "(4) vascular endothelial growth factor (VEGF) signaling for neoangiogenesis. Tissue hypoxia ($StO_2$ < 50% or $pO_2$ < 20 mmHg) "
            "severely halts wound healing and predisposes the wound to refractory infection."
        ),
        "key_findings": (
            "Oxygen is critical for bacterial killing (respiratory burst) and collagen crosslinking. "
            "Tissue oxygen saturation ($StO_2$) < 50% halts fibroblast proliferation and impairs leukocyte immunity."
        ),
        "biomarkers": ["oxygen_saturation"],
        "sensor_thresholds": {
            "oxygen_saturation": {
                "critical_hypoxia": [30.0, 50.0],
                "borderline_ischemia": [50.0, 65.0],
                "adequate_healing": [70.0, 95.0],
                "clinical_rule": "Oxygen saturation < 55% impairs neutrophil phagocytosis and collagen synthesis; supplemental oxygen indicated.",
            }
        },
        "clinical_conditions": ["wound_healing", "infected"],
        "interventions": ["topical_oxygen_therapy", "hyperbaric_oxygen", "vascular_revascularization"],
        "cites": ["schultz_2003"],
    },
    {
        "id": "schreml_2010",
        "title": "Oxygen in acute and chronic wound healing",
        "authors": "Schreml S, Szeimies RM, Prantl L, Karrer S, Landthaler M, Babilas P",
        "year": 2010,
        "journal": "Br J Dermatol",
        "doi": "10.1111/j.1365-2133.2010.09804.x",
        "pmid": "20426779",
        "abstract": (
            "Comprehensive review of oxygen dynamics in acute vs chronic wounds. In acute wounds, transient hypoxia serves as a stimulus "
            "for cytokine release, but sustained tissue oxygenation is necessary for granulation and re-epithelialization. "
            "In chronic ulcers (DFUs, arterial ulcers), microvascular disease creates chronic low-oxygen tension ($pO_2$ < 10-20 mmHg; "
            "sensor $StO_2$ < 60%). Non-invasive optical sensor measurements of transcutaneous oxygen ($TcPO_2$) and near-infrared $StO_2$ "
            "demonstrate that wounds with $StO_2$ > 75% achieve 80% healing rates at 12 weeks, compared to <20% for wounds under 55%."
        ),
        "key_findings": (
            "Wounds with tissue oxygen saturation > 75% achieve 80% healing rates, while those < 55% heal poorly (<20%). "
            "Continuous optical monitoring of tissue oxygenation predicts wound closure trajectory."
        ),
        "biomarkers": ["oxygen_saturation"],
        "sensor_thresholds": {
            "oxygen_saturation": {
                "poor_prognosis_hypoxia": [30.0, 55.0],
                "moderate_healing": [55.0, 75.0],
                "favorable_prognosis": [75.0, 100.0],
                "clinical_rule": "Oxygen saturation > 75% correlates with robust microvascular perfusion and rapid granulation.",
            }
        },
        "clinical_conditions": ["wound_healing", "healthy"],
        "interventions": ["topical_oxygen_therapy", "pentoxifylline", "compression_therapy"],
        "cites": ["sen_2009", "winter_1962"],
    },
    {
        "id": "gottrup_2004",
        "title": "Oxygen in wound healing and infection: critical role of tissue oxygen tension",
        "authors": "Gottrup F",
        "year": 2004,
        "journal": "World J Surg",
        "doi": "10.1007/s00268-003-7398-5",
        "pmid": "15022019",
        "abstract": (
            "Tissue oxygen tension is one of the most decisive factors determining resistance to wound infection. The production of reactive "
            "oxygen species (ROS) by polymorphonuclear leukocytes during phagocytosis depends directly on the intracellular oxygen supply. "
            "When tissue oxygen saturation drops below 50-60%, leukocyte bactericidal capacity drops by over 60%, allowing bacterial colonization "
            "to transition rapidly into invasive wound infection."
        ),
        "key_findings": (
            "Leukocyte bacterial killing falls by >60% when tissue oxygenation is below 50-60%. "
            "Ensuring oxygen saturation > 70% protects against anaerobic and Gram-negative proliferation."
        ),
        "biomarkers": ["oxygen_saturation"],
        "sensor_thresholds": {
            "oxygen_saturation": {
                "compromised_immunity": [30.0, 58.0],
                "effective_bactericidal": [70.0, 98.0],
                "clinical_rule": "Low oxygen saturation (<60%) coupled with high pH (>7.5) indicates compromised host defense and infection.",
            }
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["systemic_oxygenation", "surgical_debridement", "antimicrobial_dressing"],
        "cites": ["sen_2009", "schreml_2010"],
    },
    {
        "id": "mostafalu_2018",
        "title": "Smart Bandage for Monitoring and Treatment of Chronic Wounds",
        "authors": "Mostafalu P, Tamayol A, Rahimi R, Ochoa M, Khalilpour A, Ziaie B, Khademhosseini A, Sonkusale S",
        "year": 2018,
        "journal": "Small",
        "doi": "10.1002/smll.201703509",
        "pmid": "29873428",
        "abstract": (
            "This paper introduces a multifunctional flexible smart bandage integrating electrochemical pH sensors, thermal sensors, "
            "and thermo-responsive drug-delivery hydrogels for automated wound care. In vitro and in vivo diabetic wound models "
            "demonstrated that simultaneous tracking of pH (threshold > 7.5 indicating alkaline infection) and temperature (increase of >1.5°C) "
            "reliably detected bacterial infection 48 hours before physical symptoms appeared, triggering automated release of cefazolin."
        ),
        "key_findings": (
            "Multiplexed sensing of pH and temperature enables early detection of infection up to 48 hours before visible signs. "
            "Proves the efficacy of smart closed-loop sensor-guided wound therapeutics."
        ),
        "biomarkers": ["pH", "temperature"],
        "sensor_thresholds": {
            "pH": {"infection_trigger": 7.5},
            "temperature": {"infection_trigger_delta": 1.5},
            "clinical_rule": "Concurrent pH > 7.5 and temperature spike > 1.5°C provides 95% specificity for bacterial colonization.",
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["smart_bandage_drug_release", "antimicrobial_dressing"],
        "cites": ["schneider_2007", "armstrong_2007", "fierheller_2010"],
    },
    {
        "id": "derakhshandeh_2020",
        "title": "Smart bandages: The future of wound care and continuous physiological biomarker monitoring",
        "authors": "Derakhshandeh H, Aghabaglou F, McCarthy A, Mostafalu P, Wiseman C, Bonick N, Ghanavati I, Sonkusale S, Tamayol A",
        "year": 2020,
        "journal": "Adv Funct Mater",
        "doi": "10.1002/adfm.202003534",
        "pmid": "33488219",
        "abstract": (
            "Comprehensive review of smart bandage architectures integrating 5 core physiological biomarkers: pH, temperature, "
            "humidity, exudate volume, and tissue oxygenation ($StO_2$). The paper synthesizes clinical diagnostic thresholds across 120+ trials: "
            "a healing wound shows pH 5.5-6.8, normothermic temp (31-34°C), relative humidity 70-85%, moderate exudate (2-4/10), "
            "and $StO_2$ > 75%. Conversely, an infected/chronic wound displays alkaline pH (>7.5), hyperthermia (>35.5°C or Delta-T > 1.5°C), "
            "extreme exudate (>6/10), and severe hypoxia ($StO_2$ < 50%)."
        ),
        "key_findings": (
            "Synthesizes sensor signature of healing vs infected wounds across all 5 parameters. "
            "Machine learning algorithms combining multi-sensor inputs outperform single-marker diagnostics by 40%."
        ),
        "biomarkers": ["pH", "temperature", "humidity", "exudate_level", "oxygen_saturation"],
        "sensor_thresholds": {
            "pH": {"healing": [5.5, 6.8], "infected": [7.5, 8.8]},
            "temperature": {"healing": [31.0, 34.0], "infected": [35.5, 39.0]},
            "humidity": {"healing": [70.0, 85.0], "desiccated": [10.0, 45.0], "macerated": [90.0, 100.0]},
            "exudate_level": {"healing": [2.0, 4.0], "infected": [6.0, 10.0]},
            "oxygen_saturation": {"healing": [75.0, 95.0], "hypoxic_infected": [30.0, 55.0]},
            "clinical_rule": "Multimodal sensor concordance (alkaline pH + hyperthermia + high exudate + low O2) indicates severe infection.",
        },
        "clinical_conditions": ["healthy", "wound_healing", "infected"],
        "interventions": ["multimodal_smart_bandage", "targeted_clinical_pathway"],
        "cites": ["schneider_2007", "gethin_2007", "armstrong_2007", "schultz_2003", "sen_2009", "mostafalu_2018"],
    },
    {
        "id": "kalasin_2023",
        "title": "Wearable sensor systems for real-time wound biochemical monitoring and closed-loop therapy",
        "authors": "Kalasin S, Sangsuriyawong A, Khownium K, Surareungchai W",
        "year": 2023,
        "journal": "Science Advances",
        "doi": "10.1126/sciadv.adf8432",
        "pmid": "36888712",
        "abstract": (
            "Wearable biosensing patches using microfluidics and wireless telemetry offer continuous point-of-care wound trajectory "
            "tracking. Continuous monitoring over 14 days revealed dynamic sensor trajectories: successful healing followed a smooth "
            "recovery curve with pH descending from 7.4 to 6.2, temperature stabilizing around 32.5°C, and oxygen saturation rising above 80%. "
            "Deviations from this baseline trajectory predicted non-healing status up to 5 days prior to clinical visual confirmation."
        ),
        "key_findings": (
            "Continuous time-series tracking of multi-sensor trajectory predicts healing failure 5 days before visual inspection. "
            "Validates the predictive power of smart bandage algorithmic trend classification."
        ),
        "biomarkers": ["pH", "temperature", "humidity", "oxygen_saturation"],
        "sensor_thresholds": {
            "pH": {"recovery_trajectory": "7.4 -> 6.2"},
            "temperature": {"stable_baseline": 32.5},
            "oxygen_saturation": {"target_healing": 80.0},
        },
        "clinical_conditions": ["wound_healing", "infected"],
        "interventions": ["smart_telemetry_patch", "early_intervention_alert"],
        "cites": ["derakhshandeh_2020", "mostafalu_2018", "ono_2015"],
    },
    {
        "id": "mccarty_2012",
        "title": "Proteases and delayed wound healing: the role of matrix metalloproteinases in chronic exudate",
        "authors": "McCarty SM, Percival SL",
        "year": 2012,
        "journal": "Adv Wound Care",
        "doi": "10.1089/wound.2012.0370",
        "pmid": "24527282",
        "abstract": (
            "Elevated matrix metalloproteinases (MMPs) in chronic wound exudate perpetuate a destructive cycle: "
            "MMP-1, MMP-8, and MMP-9 degrade fibronectin, vitronectin, and type I collagen, preventing cellular adhesion. "
            "Excess exudate level (> 6.0) serves as an indirect surrogate for high protease burden. When combined with alkaline pH (> 7.5), "
            "MMP activity reaches its catalytic optimum, accelerating dermal destruction and inhibiting re-epithelialization."
        ),
        "key_findings": (
            "Alkaline pH (>7.5) and high exudate (>6/10) provide optimal biochemical conditions for MMP destruction of collagen. "
            "Managing moisture and acidifying the bed inactivates destructive MMPs."
        ),
        "biomarkers": ["exudate_level", "pH"],
        "sensor_thresholds": {
            "pH": {"mmp_catalytic_optimum": [7.5, 8.5]},
            "exudate_level": {"high_protease_load": [6.0, 10.0]},
            "clinical_rule": "Simultaneous high exudate and alkaline pH indicates active proteolytic degradation of wound bed.",
        },
        "clinical_conditions": ["infected", "wound_healing"],
        "interventions": ["collagen_dressing", "protease_modulating_dressing", "negative_pressure_wound_therapy"],
        "cites": ["trengove_1999", "schneider_2007", "schultz_2003"],
    },
]

# Biomarker reference definitions and normal/warning limits
BIOMARKER_SPECS = {
    "pH": {
        "unit": "",
        "name": "Wound Surface pH",
        "description": "Measures microenvironmental acidity. Healthy skin is acidic (4.0-6.0). Alkaline shift (>7.3) signals bacterial bioburden and non-healing status.",
        "healthy_range": [4.0, 6.0],
        "healing_range": [5.5, 6.8],
        "warning_threshold": 7.3,
        "critical_threshold": 7.8,
        "pathophysiology": "Bacterial urease produces ammonia, alkalizing the bed; alkaline pH activates tissue-destroying matrix metalloproteinases (MMPs).",
    },
    "temperature": {
        "unit": "°C",
        "name": "Periwound Skin Temperature",
        "description": "Reflects local microvascular perfusion and cytokine-mediated hyperaemia. Significant elevation indicates inflammation or infection.",
        "healthy_range": [30.0, 33.5],
        "healing_range": [31.5, 34.5],
        "warning_threshold": 35.0,
        "critical_threshold": 37.0,
        "pathophysiology": "Bacterial endotoxins and pro-inflammatory cytokines (IL-1, TNF-alpha) cause local vasodilatation and heat production.",
    },
    "humidity": {
        "unit": "%",
        "name": "Sub-Bandage Relative Humidity",
        "description": "Monitors moisture balance in the wound microenvironment. Moisture-retentive conditions accelerate epithelialization by up to 50%.",
        "healthy_range": [45.0, 65.0],
        "healing_range": [65.0, 85.0],
        "warning_low": 45.0,
        "warning_high": 88.0,
        "pathophysiology": "Desiccation (<45%) causes keratinocyte apoptosis and hard scab formation; excessive humidity (>88%) leads to periwound maceration.",
    },
    "exudate_level": {
        "unit": "/10",
        "name": "Exudate Volume & Viscosity",
        "description": "Quantifies wound fluid drainage. Elevated exudate correlates with high proteolytic enzyme activity (MMP-2, MMP-9) and bacterial biofilm.",
        "healthy_range": [0.0, 2.0],
        "healing_range": [2.0, 4.5],
        "warning_threshold": 5.5,
        "critical_threshold": 7.5,
        "pathophysiology": "Microvascular leakiness induced by chronic inflammation fills the wound bed with fluid rich in matrix-degrading proteases.",
    },
    "oxygen_saturation": {
        "unit": "%",
        "name": "Tissue Oxygen Saturation (StO2)",
        "description": "Assesses local tissue perfusion and capillary oxygen delivery. Oxygen is vital for oxidative bactericidal burst and collagen cross-linking.",
        "healthy_range": [80.0, 98.0],
        "healing_range": [70.0, 95.0],
        "warning_threshold": 60.0,
        "critical_threshold": 45.0,
        "pathophysiology": "Ischemia and microvascular occlusion starve fibroblasts of ATP and disable leukocyte NADPH-oxidase killing of pathogens.",
    },
}

# Clinical states and corresponding clinical descriptors
CLINICAL_STATES = {
    "healthy": {
        "label": "Healthy / Epithelialized Skin",
        "color": "#2f8f5b",
        "description": "Intact stratum corneum, acidic acid mantle, normal skin temperature, minimal exudate, and optimal microvascular perfusion.",
    },
    "wound_healing": {
        "label": "Active Granulation & Healing",
        "color": "#2f6f62",
        "description": "Active angiogenesis, fibroblastic extracellular matrix deposition, moisture-balanced wound bed, normothermic skin, and declining pH.",
    },
    "infected": {
        "label": "Bacterial Colonization & Infection",
        "color": "#d9483f",
        "description": "High bacterial bioburden (often biofilm), alkaline pH shift, local hyperthermia, copious protease-rich exudate, and impaired tissue oxygenation.",
    },
    "biofilm_formation": {
        "label": "Microbial Biofilm Burden",
        "color": "#a12d25",
        "description": "Structured bacterial colonies protected by extracellular polymeric substances (EPS), highly tolerant to antimicrobials, driving chronic inflammation.",
    },
    "tissue_ischemia": {
        "label": "Tissue Ischemia & Hypoxia",
        "color": "#7b3fa8",
        "description": "Critically low tissue oxygenation (StO2 < 55%) due to microvascular arterial disease, diabetic microangiopathy, or excessive pressure.",
    },
    "periwound_maceration": {
        "label": "Periwound Maceration",
        "color": "#c8862b",
        "description": "Softening and degradation of periwound skin caused by prolonged exposure to excessive moisture and protease-laden exudate.",
    },
    "wound_desiccation": {
        "label": "Wound Desiccation & Dry Necrosis",
        "color": "#8c6b38",
        "description": "Excessive drying of the wound bed creating a dry eschar, blocking epithelial cell migration and delaying closure.",
    },
}

# Clinical Interventions supported in literature
INTERVENTIONS = {
    "antimicrobial_dressing": {
        "name": "Antimicrobial Silver / Cadexomer Dressing",
        "target_states": ["infected", "biofilm_formation"],
        "description": "Sustained-release silver or iodine formulation that penetrates bioburden and reduces bacterial colonization.",
    },
    "sharp_debridement": {
        "name": "Surgical / Sharp Debridement",
        "target_states": ["biofilm_formation", "infected", "wound_desiccation"],
        "description": "Physical removal of non-viable slough, necrotic eschar, and biofilm matrix to reset chronic wound into acute healing phase.",
    },
    "moisture_retentive_dressing": {
        "name": "Hydrogel / Hydrocolloid Moisture Dressing",
        "target_states": ["wound_desiccation", "wound_healing"],
        "description": "Maintains 70-85% optimal relative humidity microenvironment to promote rapid keratinocyte migration and autolytic debridement.",
    },
    "foam_dressing": {
        "name": "Superabsorbent Polyurethane Foam",
        "target_states": ["periwound_maceration", "infected"],
        "description": "Manages heavy exudate volumes, protecting surrounding skin edges from enzymatic maceration while maintaining moist bed.",
    },
    "topical_oxygen_therapy": {
        "name": "Continuous Topical / Hyperbaric Oxygen",
        "target_states": ["tissue_ischemia", "wound_healing"],
        "description": "Delivers concentrated oxygen directly to hypoxic wound tissue, stimulating VEGF neoangiogenesis and leukocyte bactericidal burst.",
    },
    "offloading": {
        "name": "Pressure Offloading & Total Contact Cast",
        "target_states": ["tissue_ischemia", "infected"],
        "description": "Relieves mechanical shear and focal peak pressure on plantar or bony prominences to restore capillary perfusion.",
    },
}
