import json
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).parent
DATA = ROOT / "data"

def load(name):
    with open(DATA / name, encoding="utf-8") as f:
        return json.load(f)

def save(name, data):
    with open(DATA / name, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

pipeline = load("apps_pipeline_output.json")
old_final = load("apps_final.json")

# Preserve the two genuine human spot-check records
human_names = {"Attio", "Otter AI"}

human_records = {
    r["name"]: r
    for r in old_final
    if r.get("name") in human_names and r.get("verified") is True
}

final = []

for record in pipeline:
    name = record["name"]

    # Preserve genuine human verification
    if name in human_records:
        merged = human_records[name].copy()
        merged["source"] = "human-spot-checked"
        merged["verified"] = True
        final.append(merged)
        continue

    # Everything else comes from the latest pipeline run
    merged = record.copy()

    status = merged.get("fetch_status", "")

    if status == "ok":
        merged["source"] = "pipeline-fetched"
    else:
        merged["source"] = "pipeline-failed"

        # Never present a failed fetch as a researched fact
        merged["verdict"] = "Unclear"
        merged["confidence"] = "Low"

        if not merged.get("blocker") or merged["blocker"] == "—":
            merged["blocker"] = (
                f"Live fetch failed ({status}); manual verification required."
            )

    merged["verified"] = False
    final.append(merged)

# Safety check
assert len(final) == 100, f"Expected 100 records, got {len(final)}"

# ---------------------------------------------------------
# VERIFICATION QUEUE
# ---------------------------------------------------------

queue = []

for r in final:
    if r.get("verified") is True:
        continue

    reasons = []

    if r.get("source") == "pipeline-failed":
        reasons.append("fetch failed")

    confidence = str(r.get("confidence", "")).lower()

    if confidence in {"low", "medium"}:
        reasons.append(f"confidence={r.get('confidence')}")

    if r.get("verdict") == "Unclear":
        reasons.append("verdict=Unclear")

    if reasons:
        queue.append({
            "id": r["id"],
            "name": r["name"],
            "reason": "; ".join(reasons),
            "evidence": r.get("evidence", ""),
            "source": r.get("source", "")
        })

# ---------------------------------------------------------
# ANALYTICS
# ---------------------------------------------------------

def distribution(field):
    return dict(Counter(
        r.get(field, "Unknown")
        for r in final
    ))

def nested_distribution(field_a, field_b):
    result = defaultdict(Counter)

    for r in final:
        result[r.get(field_a, "Unknown")][r.get(field_b, "Unknown")] += 1

    return {
        category: dict(counts)
        for category, counts in result.items()
    }

source_distribution = distribution("source")

analytics = {
    "evidence_note": (
        "Analytics are based on the latest 100-record pipeline output plus two "
        "previously human spot-checked records. A successful fetch means the page "
        "was reachable; it does not mean every extracted field was independently "
        "verified. Low/medium-confidence records remain candidates for human review."
    ),

    "evidence_coverage": {
        "total_apps": len(final),
        "pipeline_fetched": sum(
            r.get("source") == "pipeline-fetched" for r in final
        ),
        "pipeline_failed": sum(
            r.get("source") == "pipeline-failed" for r in final
        ),
        "human_spot_checked": sum(
            r.get("source") == "human-spot-checked" for r in final
        ),
        "verified": sum(
            r.get("verified") is True for r in final
        ),
        "requires_human_verification": len(queue)
    },

    "source_distribution": source_distribution,

    "auth_distribution": distribution("auth"),
    "verdict_distribution": distribution("verdict"),
    "selfserve_distribution": distribution("selfServe"),
    "mcp_distribution": distribution("mcp"),
    "category_distribution": distribution("category"),

    "category_x_verdict": nested_distribution(
        "category", "verdict"
    ),

    "category_x_selfserve": nested_distribution(
        "category", "selfServe"
    ),

    "low_confidence_or_unclear_apps": [
        r["name"]
        for r in final
        if r.get("confidence") == "Low"
        or r.get("verdict") == "Unclear"
    ],

    "needs_human_verification_count": len(queue)
}

# Save outputs
save("apps_final.json", final)
save("verification_queue.json", queue)
save("analytics.json", analytics)

# ---------------------------------------------------------
# SUMMARY
# ---------------------------------------------------------

print("\nRECONCILIATION COMPLETE")
print("=======================")
print("Total apps:", len(final))
print("Pipeline fetched:", source_distribution.get("pipeline-fetched", 0))
print("Pipeline failed:", source_distribution.get("pipeline-failed", 0))
print("Human spot-checked:", source_distribution.get("human-spot-checked", 0))
print("Verified:", sum(r.get("verified") is True for r in final))
print("Human verification queue:", len(queue))

print("\nSource distribution:")
print(json.dumps(source_distribution, indent=2))

print("\nVerdict distribution:")
print(json.dumps(analytics["verdict_distribution"], indent=2))

print("\nFiles updated:")
print("- data/apps_final.json")
print("- data/verification_queue.json")
print("- data/analytics.json")