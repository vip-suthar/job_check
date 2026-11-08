from marshmallow import Schema, fields, pre_load, validate

from app.forms import MAX_LENGTH, MIN_LENGTH, clean_whitespace
from detector.rules import EXPLANATIONS


class CheckRequestSchema(Schema):
    text = fields.String(required=True, validate=validate.Length(min=MIN_LENGTH, max=MAX_LENGTH))

    @pre_load
    def clean_text(self, data, **kwargs):
        if isinstance(data, dict) and isinstance(data.get("text"), str):
            data = {**data, "text": clean_whitespace(data["text"])}
        return data


class RuleHitSchema(Schema):
    rule_id = fields.String()
    explanation = fields.Function(lambda h: EXPLANATIONS.get(h.rule_id, h.rule_id))
    matched_text = fields.String()
    start = fields.Integer(attribute="span_start")
    end = fields.Integer(attribute="span_end")


class CheckSchema(Schema):
    id = fields.Integer()
    created_at = fields.DateTime()
    source = fields.String()
    score = fields.Integer(attribute="rule_score")
    indicator = fields.String()
    label = fields.String()
    hits = fields.List(fields.Nested(RuleHitSchema))
