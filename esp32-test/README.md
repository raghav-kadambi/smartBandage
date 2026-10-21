# WoundSense mobile app (Tauri + ESP32 + smartwatch)

A phone app for the smart bandage: sign in, live temperature / humidity / moisture from the
ESP32 bandage, heart rate and blood pressure from an MS1020 watch, a wound assessment from the
project's validated model, per-metric history charts, wound-photo scans, an AI assistant grounded in
the PubMed corpus, and a model card with the PhysioNet external-validation results.

The phone uses the **same model and the same RAG corpus as the website**. Only the transport differs
(token auth, readings arriving over BLE). Everything app-specific lives under `esp32-test/` plus:

```
esp32-test/firmware/woundsense_ble/   ESP32 sketch (DHT22 + moisture sensor -> BLE)
esp32-test/app/                       Tauri v2 mobile app (vanilla JS + Vite, no UI framework)
mobile_api.py, mobile_server.py       /api/m/* backend, mounted on the existing Flask app
models/train_scan_model.py            wound-photo model (CLIP embeddings + logistic regression)
models/scan/                          its trained files + metadata.json (metrics and caveats)
tests/test_mobile_api.py              API tests (auth, model gating, model card, RAG, guides)
```

## Screens

Home (assessment with class probabilities, vitals, scan, evidence-based tip) · Trends (24H / 7D / 30D) ·
Scan (centre button) · Assistant · Profile. Profile leads to My wound (care guidance, details form,
sensor guides), Devices, **Model & validation** and the **Research library** (28 PubMed studies).
Metric pages have scrubbable charts, low / average / high and the research behind the sensor.
Light and dark themes follow the phone. Screenshots: `report_screenshots/`.

Design system: tokens in `src/style.css` (`:root`, with a designed dark theme), system font stack,
16 px gutters, 48 px touch targets. Metric colours come from a colour-blind-checked categorical
palette; green / amber / red are reserved for the wound status and always carry an icon and label.

## Run it

1. **Server** (the PC, same Wi-Fi as the phone):
   ```powershell
   cd smartBandage
   venv\Scripts\activate
   python mobile_server.py
   ```
   Allow inbound TCP 5000 once (admin PowerShell):
   `New-NetFirewallRule -DisplayName "WoundSense 5000" -Direction Inbound -Protocol TCP -LocalPort 5000 -Action Allow -Profile Any`
2. **ESP32**: flash `woundsense_ble.ino`. Wire the moisture sensor's AOUT to GPIO 34 and
   **calibrate `ADC_DRY` / `ADC_WET`** (the values in the sketch are placeholders).
3. **App**:
   ```powershell
   cd esp32-test\app
   npm install
   npm run tauri android build -- --debug --apk   # standalone: works with the PC off
   adb install -r src-tauri\gen\android\app\build\outputs\apk\universal\debug\app-universal-debug.apk
   ```
   (`npm run tauri android dev` also works while the PC is on and reachable.)
4. In the app: open **Server address** on the sign-in screen and enter `http://<PC-IP>:5000`
   (`ipconfig` shows it; it changes with the network). Create an account, then use
   **Devices** to connect the bandage, measure on the watch, or switch on demo data.

## How the assessment works

- **Model**: the website's Random Forest (`models/condition_model.pkl`, `healing_model.pkl`) on five
  inputs: temperature and humidity from the bandage, heart rate and systolic / diastolic pressure from
  the watch. 92.9% held-out accuracy; on PhysioNet 2019 (39,745 ICU patients, never used in training)
  patient-level AUROC 0.687 vs 0.648 for SIRS + BP. See the main README for the caveats.
- **When it runs**: the bandage and watch connect one at a time, so each new reading is combined with
  the freshest stored values. An assessment is made only when temperature and humidity are under
  10 minutes old and heart rate / BP under 12 hours old. Otherwise Home shows which inputs are missing.
- **Temperature** is body-equivalent: the firmware adds `SKIN_TO_CORE_OFFSET_C` (3.5 °C, calibrate it),
  the same convention as `firmware/esp32_smart_bandage`.
- **Moisture** is stored and charted for context but is not a model input.
- **Demo data** is stored with `source = "demo"` and is never mixed with real readings.
- **Assistant / RAG**: uses `rag_service.py`, i.e. the 28-paper corpus pulled verbatim from PubMed.
  The server drops any citation tag that was not retrieved for that question.
- `GET /api/m/model` returns the model card (holdout metrics, feature importance, PhysioNet results)
  shown on the *Model & validation* screen.

## Scan wound (photos)

The app's **Scan wound** screen sends a photo to the server (`POST /api/m/scan`), which returns the
wound type, a visual-severity label, photo-quality warnings and a "this doesn't look like the
training photos" flag. It never stores the full photo: only a 192 px thumbnail and the result.

- **Data**: [rupeshsah/wound](https://huggingface.co/datasets/rupeshsah/wound) (Apache-2.0, 1,564
  images, 10 types), downloaded to `data/images/wound_hf/` (git-ignored). Retrain with
  `python models/train_scan_model.py` (uses fastembed's ONNX CLIP encoder, no PyTorch).
- **Honest numbers** (5-fold CV with near-duplicate images grouped, because ~40% of the images are
  near-copies): wound type 77.6% accuracy / macro-F1 0.80 (majority baseline 21%); weakest are
  surgical 56%, pressure 67%, cut 71%. Severity F1 0.77 vs 0.62 for a type-only baseline.
- **What it cannot do**: the data has no infection or healing-time labels, so the scan predicts
  neither. The severity/description text in that dataset looks machine-generated (a "venous" wound
  described with "charred tissue"), so severity is a prediction of those labels, not a clinical
  grade. The "time to heal" figure comes only from the sensor model, not the photo.
- **Home banner** ("Looking steady / Keep an eye on it / Needs attention") is a few plain rules over
  the bandage assessment and the latest photo, not a trained model.
- **Not used yet**: Redscar (infection-labelled post-surgical photos). Its download needs a personal
  code requested through their site. It has only 28 infected images, so an infection head would be weak.

## Known limits

- `tauri-plugin-blec` keeps one BLE connection, so the bandage and watch can't be connected at
  once: the watch is a "measure now" session, then the bandage reconnects.
- The out-of-distribution threshold was calibrated on 350 px web images. Real phone photos may be
  flagged "unreliable" more often than they should be; tune `ood_similarity_threshold` after real use.
- Photo capture uses `<input type="file" capture>`; the Android camera hand-off is untested.
- Not yet run on a phone: the UI was exercised in headless Edge against the real API, and the
  parsers against real captured packets, but BLE, the moisture calibration and the Android
  build of the opener plugin are untested.
