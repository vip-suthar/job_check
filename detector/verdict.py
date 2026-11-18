"""Combined detector: flags a posting if the rule score or the model probability crosses its threshold.

check(text) returns the rules' result plus "probability" (None without a trained model, in which
case the indicator comes from the rules alone). Rule hits are always returned, so a model-triggered
flag still shows whatever phrases the rules found.
"""
from detector import model, rules

MODEL_THRESHOLD = 0.5


def flagged(score, probability, rule_threshold=rules.THRESHOLD, model_threshold=MODEL_THRESHOLD):
    return score >= rule_threshold or (probability is not None and probability >= model_threshold)


def check(text):
    result = rules.check(text)
    p = model.probability(text)
    return {**result, "probability": p, "indicator": "red_flags" if flagged(result["score"], p) else "no_flags"}
