import os
import re
import json

from dotenv import load_dotenv
load_dotenv()

from groq import Groq

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

_SYSTEM_PROMPT = (
    "You are a clinical trial criteria parser. Convert free-text trial inclusion/exclusion "
    "criteria into structured JSON. Only output JSON, no prose. Use null for unspecified fields."
)

_USER_TEMPLATE = """Convert the following trial criteria into JSON matching this exact schema:
{
  "inclusion": {
    "age_min": <int or null>,
    "age_max": <int or null>,
    "gender": <"M"|"F"|null>,
    "icu_los_min_hours": <float or null>,
    "icu_los_max_hours": <float or null>,
    "required_conditions": [<str>],
    "required_interventions": [<str>]
  },
  "exclusion": {
    "conditions": [<str>],
    "interventions": [<str>],
    "age_under": <int or null>
  }
}

Criteria:
{criteria}"""


def fallback_parse(text: str) -> dict:
    """Regex-based fallback when Groq is unavailable."""
    result = {
        "inclusion": {
            "age_min": None,
            "age_max": None,
            "gender": None,
            "icu_los_min_hours": None,
            "icu_los_max_hours": None,
            "required_conditions": [],
            "required_interventions": [],
        },
        "exclusion": {
            "conditions": [],
            "interventions": [],
            "age_under": None,
        },
    }
    t = text.lower()

    # Age range: "aged 18-75", "age 18 to 75", "18–75 years"
    m = re.search(r"age[d\s]*[:\s]*(\d+)\s*[-–to]+\s*(\d+)", t)
    if m:
        result["inclusion"]["age_min"] = int(m.group(1))
        result["inclusion"]["age_max"] = int(m.group(2))

    # Age minimum only: "≥18", ">= 18", "older than 18", "at least 18"
    if result["inclusion"]["age_min"] is None:
        m = re.search(r"(?:>=|≥|older than|at least)\s*(\d+)\s*(?:year|yr)?", t)
        if m:
            result["inclusion"]["age_min"] = int(m.group(1))

    # ICU LOS minimum: "at least 24 hours", "≥24h", ">= 48 hours"
    m = re.search(r"(?:at least|>=|≥|minimum|min)\s*(\d+(?:\.\d+)?)\s*h(?:ours?)?", t)
    if m:
        result["inclusion"]["icu_los_min_hours"] = float(m.group(1))

    # ICU LOS from plain "X hours in ICU"
    if result["inclusion"]["icu_los_min_hours"] is None:
        m = re.search(r"(\d+(?:\.\d+)?)\s*h(?:ours?)?\s+(?:in|on)\s+(?:the\s+)?icu", t)
        if m:
            result["inclusion"]["icu_los_min_hours"] = float(m.group(1))

    # Gender
    if re.search(r"\bmale\b", t) and not re.search(r"\bfemale\b", t):
        result["inclusion"]["gender"] = "M"
    elif re.search(r"\bfemale\b", t) and not re.search(r"\bmale\b", t):
        result["inclusion"]["gender"] = "F"

    # Required interventions
    interventions = {
        "mechanical_ventilation": [r"mechanical.?ventil", r"\bventilat", r"\bintubat"],
        "sedation": [r"\bsedat"],
        "vasopressors": [r"\bvasopressor"],
        "renal_replacement_therapy": [r"\bdialysis\b", r"\brrt\b", r"renal.?replacement"],
        "tracheostomy": [r"\btracheostomy\b"],
    }
    for label, patterns in interventions.items():
        if any(re.search(p, t) for p in patterns):
            result["inclusion"]["required_interventions"].append(label)

    # Exclusion conditions
    excl_section = ""
    m = re.search(r"exclud[e\s]+(.*?)(?:\.|$)", t)
    if m:
        excl_section = m.group(1)

    exclusion_keywords = {
        "delirium": [r"\bdelirium\b"],
        "dementia": [r"\bdementia\b"],
        "coma": [r"\bcoma\b"],
        "pregnancy": [r"\bpregnant\b", r"\bpregnancy\b"],
        "traumatic_brain_injury": [r"\btraumatic brain\b", r"\btbi\b"],
        "liver_failure": [r"\bliver fail", r"\bhepatic fail"],
        "end_stage_renal_disease": [r"\besrd\b", r"end.?stage renal"],
    }
    for label, patterns in exclusion_keywords.items():
        search_in = excl_section or t
        if any(re.search(p, search_in) for p in patterns):
            result["exclusion"]["conditions"].append(label)

    # Exclusion age_under: "exclude patients under 18", "< 18 years"
    m = re.search(r"(?:under|<|younger than)\s*(\d+)\s*(?:year|yr)?", t)
    if m:
        result["exclusion"]["age_under"] = int(m.group(1))

    return result


class CriteriaParser:
    def __init__(self):
        self._client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

    def parse_criteria(self, free_text: str) -> dict:
        if not self._client:
            parsed = fallback_parse(free_text)
            parsed["_source"] = "fallback_no_key"
            return parsed

        try:
            response = self._client.chat.completions.create(
                model="llama-3.1-70b-versatile",
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": _USER_TEMPLATE.format(criteria=free_text)},
                ],
                response_format={"type": "json_object"},
                temperature=0,
            )
            raw_content = response.choices[0].message.content
            print("=== GROQ RAW RESPONSE ===")
            print(type(raw_content))
            print(repr(raw_content))
            print("=== END RAW ===")
            content = raw_content.strip().strip("```json").strip("```").strip()
            print(f"[CriteriaParser] raw Groq content:\n{content}")
            result = json.loads(content)
            result["_source"] = "groq"
            return result

        except Exception as exc:
            fallback = fallback_parse(free_text)
            fallback["_source"] = "fallback_groq_error"
            fallback["error"] = str(exc)
            fallback["raw"] = free_text
            return fallback


if __name__ == "__main__":
    test_criteria = (
        "Adults aged 18-75 in ICU for at least 24 hours, on mechanical ventilation. "
        "Exclude patients with active delirium or dementia."
    )

    parser = CriteriaParser()
    result = parser.parse_criteria(test_criteria)
    print(json.dumps(result, indent=2))
