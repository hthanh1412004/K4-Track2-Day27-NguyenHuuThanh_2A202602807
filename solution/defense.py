"""Streaming checks using only the documented, sandbox-safe toolkit."""
from api import Verdict


# GUIDE.md separates natural feature variation (< 0.472 sigma) from skew.
FEATURE_SHIFT_LIMIT = 0.65
EMBEDDING_SHIFT_LIMIT = 0.040
CORPUS_AGE_LIMIT_DAYS = 45.0
BATCH_DISTANCE_LIMIT = 1.30


def register(ctx):
    ctx.on("data_batch", check_data_batch)
    ctx.on("contract_checkpoint", check_contract_checkpoint)
    ctx.on("lineage_run", check_lineage_run)
    ctx.on("feature_materialization", check_feature_materialization)
    ctx.on("embedding_batch", check_embedding_batch)


def check_data_batch(payload, ctx):
    profile = ctx.tools.batch_profile(payload["batch_id"])
    if "error" in profile:
        return tool_error(ctx, "checks", profile)

    baseline = ctx.baseline
    rows = profile["row_count"]
    amount = profile["mean_amount"]
    null_rate = profile["null_rate"]["customer_id"]
    stale = profile["staleness_min"]
    reasons = []
    if not baseline["row_count_min"] <= rows <= baseline["row_count_max"]:
        reasons.append("row count outside baseline range")
    if null_rate > baseline["null_rate_max"]:
        reasons.append("customer_id null rate exceeds baseline")
    if not baseline["mean_amount_min"] <= amount <= baseline["mean_amount_max"]:
        reasons.append("mean amount outside baseline range")
    if stale > baseline["staleness_min_max"]:
        reasons.append("batch freshness lag exceeds baseline")

    # Normalize by each published half-range (3 sigma), not by 1 sigma:
    # the 1.30 cutoff describes distance relative to the baseline envelope.
    row_mid = (baseline["row_count_min"] + baseline["row_count_max"]) / 2
    row_radius = (baseline["row_count_max"] - baseline["row_count_min"]) / 2
    amount_mid = (baseline["mean_amount_min"] + baseline["mean_amount_max"]) / 2
    amount_radius = (baseline["mean_amount_max"] - baseline["mean_amount_min"]) / 2
    distance_squared = (
        ((rows - row_mid) / row_radius) ** 2
        + ((amount - amount_mid) / amount_radius) ** 2
        + (null_rate / baseline["null_rate_max"]) ** 2
        + (stale / baseline["staleness_min_max"]) ** 2
    )
    if distance_squared > BATCH_DISTANCE_LIMIT ** 2:
        reasons.append("combined batch deviation exceeds baseline envelope")
    return decide(ctx, "checks", reasons)


def check_contract_checkpoint(payload, ctx):
    diff = ctx.tools.contract_diff(payload["contract_id"], payload["checkpoint_batch_id"])
    if "error" in diff:
        return tool_error(ctx, "contracts", diff)
    reasons = [str(violation) for violation in diff["violations"]]
    freshness_limit = ctx.baseline["freshness_delay_max_min"]
    declared_limit = payload.get("declared_sla", {}).get("freshness_min")
    if declared_limit is not None:
        freshness_limit = min(freshness_limit, declared_limit)
    if diff["freshness_delay_min"] > freshness_limit:
        reasons.append("contract freshness delay exceeds SLA or baseline")
    return decide(ctx, "contracts", reasons)


def check_lineage_run(payload, ctx):
    graph = ctx.tools.lineage_graph_slice(payload["run_id"])
    if "error" in graph:
        return tool_error(ctx, "lineage", graph)
    reasons = []
    # Required dependencies of the lab's stg_orders transformation (GUIDE.md).
    missing = {"raw.orders", "raw.customers"} - set(graph["actual_upstream"])
    if missing:
        reasons.append("missing upstream: " + ", ".join(sorted(missing)))
    if graph["actual_downstream_count"] == 0:
        reasons.append("orphan output has no downstream consumer")
    if graph["duration_ms"] > ctx.baseline["lineage_duration_ms_max"]:
        reasons.append("lineage runtime exceeds baseline")
    return decide(ctx, "lineage", reasons)


def check_feature_materialization(payload, ctx):
    drift = ctx.tools.feature_drift(payload["feature_view"], payload["batch_id"])
    if "error" in drift:
        return tool_error(ctx, "ai_infra", drift)
    reasons = []
    limit = max(ctx.baseline["feature_mean_shift_sigma_max"], FEATURE_SHIFT_LIMIT)
    if abs(drift["mean_shift_sigma"]) > limit:
        reasons.append("training-serving mean shift exceeds calibrated limit")
    return decide(ctx, "ai_infra", reasons)


def check_embedding_batch(payload, ctx):
    drift = ctx.tools.embedding_drift(payload["corpus"], payload["chunk_batch_id"])
    if "error" in drift:
        return tool_error(ctx, "ai_infra", drift)
    reasons = []
    shift_limit = min(ctx.baseline["embedding_centroid_shift_max"], EMBEDDING_SHIFT_LIMIT)
    age_limit = min(ctx.baseline["corpus_avg_doc_age_days_max"], CORPUS_AGE_LIMIT_DAYS)
    if drift["centroid_shift"] > shift_limit:
        reasons.append("embedding centroid drift exceeds calibrated limit")
    if drift["avg_doc_age_days"] > age_limit:
        reasons.append("RAG corpus documents are stale")
    return decide(ctx, "ai_infra", reasons)


def decide(ctx, pillar, reasons):
    """Keep free per-pillar counters without retaining event IDs or labels."""
    counts = ctx.state.setdefault("counts", {})
    stats = counts.setdefault(pillar, {"events": 0, "alerts": 0})
    stats["events"] += 1
    stats["alerts"] += int(bool(reasons))
    return Verdict(alert=bool(reasons), pillar=pillar, reason="; ".join(reasons))


def tool_error(ctx, pillar, result):
    """A failed measurement is not evidence of a pipeline fault; do not retry."""
    errors = ctx.state.setdefault("tool_errors", {})
    errors[pillar] = errors.get(pillar, 0) + 1
    return Verdict(alert=False, pillar=pillar, reason="measurement unavailable: " + str(result["error"]))
