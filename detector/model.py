"""TF-IDF + logistic regression baseline, trained only on posting text.

Train with: python -m detector.model [--input data/processed/emscad_train.csv]
The app uses the saved model when it exists and falls back to the rules alone otherwise.
"""
import argparse
from functools import lru_cache
from pathlib import Path

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "instance" / "model.joblib"
TEXT_COLS = ["title", "company_profile", "description", "requirements", "benefits"]


def posting_text(df):
    """Join the EMSCAD text fields of each row; metadata columns are not used, since pasted text has none."""
    return df[TEXT_COLS].fillna("").astype(str).agg(" ".join, axis=1)


def train(texts, labels):
    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True, stop_words="english"),
        LogisticRegression(class_weight="balanced", max_iter=1000),
    )
    return model.fit(texts, labels)


@lru_cache(maxsize=1)
def load():
    return joblib.load(MODEL_PATH) if MODEL_PATH.exists() else None


def probability(text):
    model = load()
    return None if model is None else float(model.predict_proba([text])[0, 1])


def main():
    parser = argparse.ArgumentParser(description="Train the ML baseline on the EMSCAD training split.")
    parser.add_argument("--input", default=str(ROOT / "data" / "processed" / "emscad_train.csv"))
    parser.add_argument("--output", default=str(MODEL_PATH))
    args = parser.parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit(f"Training data not found: {source}\nRun prepare_emscad.py first.")
    df = pd.read_csv(source, low_memory=False)
    model = train(posting_text(df), df["fraudulent"].astype(int))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output)
    print(f"Trained on {len(df)} rows; saved model to {output}")


if __name__ == "__main__":
    main()
