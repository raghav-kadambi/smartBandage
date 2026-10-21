# WoundSense mobile app (Tauri + ESP32 + smartwatch)

A phone app for the smart bandage: sign in, live temperature / humidity / moisture from the
ESP32 bandage, heart rate and blood pressure from an MS1020 watch, per-metric history charts,
a wound-status estimate, an AI chat grounded in cited papers, and a wound-info/evidence page.

Everything lives under `esp32-test/` plus three new backend files; the website (`app.py`,
`templates/`, existing models and RAG data) is not modified.

```
esp32-test/firmware/woundsense_ble/   ESP32 sketch (DHT22 + moisture sensor -> BLE)
esp32-test/app/                       Tauri v2 mobile app (vanilla JS + Vite)
mobile_api.py, mobile_server.py       /api/m/* backend, mounted on the existing Flask app
models/train_mobile_model.py          3-feature model (temperature, humidity, moisture)
models/mobile/                        its trained files + metadata.json
models/train_scan_model.py            wound-photo model (CLIP embeddings + logistic regression)
models/scan/                          its trained files + metadata.json (metrics and caveats)
data/literature_verified.json         20 papers, metadata verified against PubMed
```

## Screens

Home (status, live tiles, tip of the day) · Trends (24h / 7d / 30d) · Scan (centre button) · Ask AI ·
You (account, My wound, Devices, server address). My wound has Overview (care tips with citations),
Details (wound form) and Learn (sensor guides, research library). Metric pages show scrubbable charts.

## Run it

1. **Server** (the PC, same Wi-Fi as the phone):
   ```powershell
   cd C:\Users\Tanu\Code\bandage
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

## What is real and what is not

- **Model**: trained on `data/augmented_training_data.csv` using only temperature, humidity and
  the moisture reading (assumed to stand in for `exudate_level`, 0-10). The CSV's provenance
  should be confirmed; ~98% holdout accuracy is not clinical validation. Days-to-heal comes
  from a severity heuristic, not patient outcomes. The app says so on screen.
- **Heart rate / blood pressure** are shown and given to the chat as context. They do not
  feed the model. The watch packet layout was decoded from observed traffic (see `ble.js`).
- **Demo data** is stored with `source = "demo"` and is never mixed with real readings.
- **Literature**: titles, authors, journals, DOIs and PMIDs were checked against NCBI; each
  summary restates only what that paper's abstract says. Humidity/moisture thresholds are
  deliberately not claimed because none of the papers establish one.
- **Your original 20-paper set** (`data/literature_data.py`) is untouched and still drives the
  website and knowledge graph. 17 of its 20 PMIDs are wrong (15 resolve to unrelated papers,
  e.g. a plant-biology paper; one to a different wound paper; one doesn't exist), and the
  Nakagami DOI is wrong too, so it should be rebuilt before it is shown to a reviewer.

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
  grade. The "time to heal" figure still comes only from the bandage-sensor heuristic.
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
