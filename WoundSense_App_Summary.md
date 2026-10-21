# WoundSense: smart-bandage companion app (project summary)

## 1. What it is

WoundSense is a mobile-app prototype that follows a wound's progress. It combines three sources:

1. **A smart bandage** (ESP32 microcontroller with a DHT22 temperature/humidity sensor and a moisture sensor) streaming live readings over Bluetooth Low Energy.
2. **A smartwatch** (model MS1020) worn beside the wound, giving heart rate and blood pressure over Bluetooth.
3. **Wound photos** taken with the phone and analysed by an image model.

It turns these into a wound-status estimate, an estimated time to heal, history charts, research-backed guidance, and an AI assistant that answers questions using the patient's own data and cited studies.

The project is a prototype for demonstrating what such a system could do. It is not a medical device and has not been used with patients.

## 2. Architecture

```
ESP32 bandage ──BLE──┐
MS1020 watch ──BLE───┼──> Phone app (Tauri v2) ──HTTPS/HTTP──> Flask server ──> SQLite
Phone camera ────────┘                                           ├─ Sensor ML models
                                                                 ├─ Wound-photo model
                                                                 └─ RAG + LLM chat
```

| Layer | Technology |
|---|---|
| Mobile app | Tauri v2 (Rust shell, Android), vanilla JavaScript, Vite, hand-written SVG charts |
| Bluetooth | `tauri-plugin-blec` (btleplug); one connection at a time, so the watch is a short "measure now" session |
| Firmware | Arduino C++ on ESP32, BLE notifications every 2 s: `temperature,humidity,moisture` |
| Backend | Flask blueprint (`/api/m`), token auth (signed tokens), SQLite |
| Sensor model | scikit-learn RandomForest classifier + regressor (shared with the website), externally tested on PhysioNet 2019 |
| Photo model | CLIP ViT-B/32 image embeddings (ONNX, via fastembed) + logistic regression |
| Chat | Retrieval-augmented generation over 28 PubMed papers: bge-small embeddings, in-memory Qdrant, Groq-hosted LLM |

## 3. What the user sees

- **Sign in / create account.** Server address is configurable.
- **Home.** Wound status (On track / Healing / Needs attention) with a trend, model confidence and class probabilities, the estimated days to heal, and a checklist of missing inputs when an assessment cannot run yet. Vitals tiles for temperature, humidity, heart rate, blood pressure and moisture with sparklines, a rule-based alert banner, a scan shortcut and a cited daily tip.
- **Trends.** 24 h / 7 d / 30 d views: a days-to-heal chart plus a card per metric (average, range, direction of change).
- **Metric pages.** Scrubbable charts with min / average / max, a plain-language guide and the research behind each sensor.
- **Scan wound (centre button).** Take or choose a photo; it returns the wound type with confidence bars and a visual-severity label, warns about dark, blurry or small photos, and flags photos it cannot match. Scans are kept as thumbnails with history.
- **My wound.** Overview (latest scan, day counter, cited care tips), Details (cause, severity, pain, itching, days since onset, notes), Learn (sensor guides with their PubMed studies).
- **Model & validation.** Holdout metrics, feature importance, and the PhysioNet external test compared with SIRS and qSOFA rules, plus limitations.
- **Research library.** All 28 PubMed studies, filterable by sensor, each linked to its PubMed record.
- **Assistant.** A chat that sees the latest readings, wound details and scan. It cites only studies retrieved for that question. Conversations are not stored.
- **Devices.** Connect the bandage, measure on the watch, or switch on demo data (stored separately from real readings).

## 4. How each part works

**Sensors.** The ESP32 reads the DHT22 and an analog moisture sensor (scaled to 0-10 after calibration) and notifies a short text payload. The app posts readings to the server at most every 15 s.

**Watch.** The MS1020 uses a proprietary protocol. Packets on characteristic `0xCC04` were captured with nRF Connect and decoded: a packet starting `0x20` carries heart rate in byte 10; one starting `0xF3` carries systolic and diastolic pressure in bytes 2 and 3. Values are range-checked and unknown packets ignored. The decoding was verified against captured packets and against the watch's own readings.

**Sensor model.** The website's validated Random Forest on five inputs: temperature and humidity from the bandage, heart rate and systolic/diastolic blood pressure from the watch. Readings arrive one device at a time, so each reading is combined with the freshest stored values; an assessment runs only when bandage values are under 10 minutes old and watch values under 12 hours old. Output: condition (healthy / wound healing / infected) with class probabilities, and estimated days to heal. Holdout accuracy 92.9% (macro-F1 0.93). External test on PhysioNet/CinC 2019 (39,745 ICU patients, never used in training): patient-level AUROC 0.687 (95% CI 0.676-0.696) against 0.648 for SIRS + BP. Moisture is shown for context and is not a model input. The app's *Model & validation* screen shows these results.

**Photo model.** Trained on 1,564 public wound images (Hugging Face `rupeshsah/wound`, Apache-2.0) in 10 classes: pressure, diabetic, venous, surgical, bruise, burn, abrasion, laceration, cut, normal skin. Roughly 40% of the images are near-duplicates, so evaluation used 5-fold cross-validation with duplicates grouped. Wound-type accuracy 77.6% (macro-F1 0.80) against a 21% majority-class baseline. A visual-severity head scored F1 0.77 against 0.62 for a baseline that knows only the wound type. An out-of-distribution check and photo-quality checks reduce bad results.

**Research library and chat.** 28 papers on wound temperature, moisture balance, sepsis criteria (SIRS, Sepsis-3/qSOFA, NEWS), blood pressure and healing, stress, and smart dressings. Title, authors, journal, DOI and abstract are pulled verbatim from PubMed (`data/build_literature_corpus.py`); the same corpus drives the website chat and knowledge graph. The chat retrieves the most relevant papers for each question, expanded with any out-of-range readings, and the server filters every reply so only those papers' citation tags can appear.

**Overall banner.** A few plain rules over the bandage result and the latest photo, not a trained model.

## 5. Honest scope (include in the report)

- **Training data.** No public dataset records these signals from a wound dressing with healthy/healing/infected labels, so the training set is knowledge-based: each class is sampled from distributions set by published criteria. The PhysioNet test uses sepsis as a proxy for the infected class, which is systemic infection, not local wound infection. Estimated days to heal comes from a severity heuristic, not patient outcomes.
- **No public dataset** was found that pairs wound temperature, moisture, heart rate or blood pressure with a healing outcome. Public image datasets exist, but their labels cover wound type and appearance, not infection or healing time (see section 7).
- **Photo model labels.** Wound type comes from an image collection and is the stronger signal. The severity labels look machine-generated. The scan does not detect infection or predict healing time.
- **Temperature offset.** The bandage reports body-equivalent temperature using a fixed skin-to-core offset (3.5 °C) that should be calibrated per wearer.
- **Smartwatch readings** may be estimates, and the blood-pressure packet layout was decoded from observed traffic, not a specification.
- **Tested:** the API end to end, the interface in a desktop browser at phone size, the parsers on real captured watch packets, and live use of the watch on a phone. **Not yet tested:** a long run on the phone with the ESP32 bandage and calibrated moisture sensor, and the Android camera hand-off for photos.

## 6. Future work

1. Collect real labelled data: sensor readings paired with clinician-assessed status and serial wound-size measurements, the missing ground truth for healing-time prediction.
2. Wound-area tracking from photos with a reference marker, giving a real healing-rate estimate.
3. An infection-labelled image set (for example Redscar or DFUC2021, both by request).
4. Calibrate the moisture sensor against a known wetting range and validate the watch against a reference device.
5. Connect the bandage and watch at the same time, add iOS support and notifications, secure transport (HTTPS), and a clinician view.

## 7. Datasets reviewed

| Source | Content | Use here |
|---|---|---|
| Hugging Face `rupeshsah/wound` | 1,564 wound photos, 10 types | Trained the photo model |
| Redscar (Univ. of the Balearic Islands) | 394 post-surgical photos with infection labels | Not used; needs a personal download code; only 28 infected images |
| DFUC2021 | Diabetic-foot-ulcer photos with infection / ischaemia labels | Not used; access by request |
| FUSeg | 1,210 foot-ulcer photos with outlines | Not used; for future area tracking |
| Chronic Wounds Multimodal Image Database | Photos, thermal images, 3D meshes | Not used; no confirmed outcome labels |
| INAOE Plantar Thermogram Database | Diabetic foot thermal images | Not used; ulcer risk only |
