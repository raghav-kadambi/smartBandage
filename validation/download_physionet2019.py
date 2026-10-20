"""
Download the official PhysioNet / Computing in Cardiology Challenge 2019 dataset
("Early Prediction of Sepsis from Clinical Data", v1.0.0, CC-BY 4.0) and condense it
into one CSV holding only the columns our bandage can measure.

Source:  https://physionet.org/content/challenge-2019/1.0.0/
Paper:   Reyna MA et al. Early Prediction of Sepsis From Clinical Data: The PhysioNet/
         Computing in Cardiology Challenge 2019. Crit Care Med. 2020;48(2):210-217.
         doi:10.1097/CCM.0000000000004145

This data is used ONLY as an external test set -- it is never used for training.

Usage:
    python validation/download_physionet2019.py            # all 40,336 patients
    python validation/download_physionet2019.py --limit 500  # quick smoke test
"""

import argparse
import io
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "physionet_2019" / "raw"
OUT_CSV = ROOT / "data" / "physionet_2019" / "physionet2019_vitals.csv"

# PhysioNet's official open-data mirror on AWS (identical files, much faster than
# physionet.org for 40k small requests); physionet.org is the fallback.
BASE_URL = "https://physionet-open.s3.amazonaws.com/challenge-2019/1.0.0/training"
FALLBACK_URL = "https://physionet.org/files/challenge-2019/1.0.0/training"
# Patient id ranges published on the dataset page
SETS = {
    "training_setA": range(1, 20644),        # p000001 .. p020643
    "training_setB": range(100001, 120001),  # p100001 .. p120000
}
KEEP_COLS = ["HR", "Temp", "SBP", "DBP", "MAP", "ICULOS", "SepsisLabel"]


def patient_files(limit=None):
    files = [(s, f"p{pid:06d}.psv") for s, ids in SETS.items() for pid in ids]
    return files[:limit] if limit else files


def fetch(session, set_name, fname):
    dest = RAW_DIR / set_name / fname
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    resp = None
    for base in (BASE_URL, FALLBACK_URL):
        try:
            resp = session.get(f"{base}/{set_name}/{fname}", timeout=60)
        except requests.RequestException:
            continue
        if resp.ok:
            break
    if resp is None or not resp.ok:
        return None  # a few ids in the published ranges are absent
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(resp.content)
    return dest


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=24)
    args = ap.parse_args()

    files = patient_files(args.limit)
    print(f"Fetching {len(files)} patient files from {BASE_URL}")
    session = requests.Session()
    done, paths = 0, []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(fetch, session, s, f) for s, f in files]
        for fut in as_completed(futures):
            p = fut.result()
            if p is not None:
                paths.append(p)
            done += 1
            if done % 2000 == 0:
                print(f"  {done}/{len(files)}")

    frames = []
    for p in sorted(paths):
        df = pd.read_csv(io.StringIO(p.read_text()), sep="|", usecols=KEEP_COLS)
        df.insert(0, "patient_id", p.stem)
        df.insert(1, "source_set", p.parent.name)
        frames.append(df)
    full = pd.concat(frames, ignore_index=True)
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(OUT_CSV, index=False)
    print(f"Wrote {len(full):,} hourly rows from {full['patient_id'].nunique():,} patients -> {OUT_CSV}")


if __name__ == "__main__":
    main()
