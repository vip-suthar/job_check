from scripts.freeze_indian_split import final_label, stratified_split


def test_final_label_uses_agreement_then_resolution():
    assert final_label({"label_1": "1", "label_2": " 1"}) == "1"
    assert final_label({"label_1": "1", "label_2": "0", "label": "0"}) == "0"
    assert final_label({"label_1": "1", "label_2": "0", "label": ""}) is None
    assert final_label({"label_1": "1", "label_2": ""}) is None


def test_split_is_stratified_and_repeatable():
    rows = [{"text": str(i), "label": "1" if i < 10 else "0"} for i in range(30)]
    dev, test = stratified_split(rows, 0.4, seed=42)
    assert sum(r["label"] == "1" for r in dev) == 4
    assert sum(r["label"] == "0" for r in dev) == 8
    assert len(dev) + len(test) == 30
    assert stratified_split(rows, 0.4, seed=42) == (dev, test)
