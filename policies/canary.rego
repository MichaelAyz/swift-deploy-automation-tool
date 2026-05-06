package canary

import rego.v1

# allow is true only when no violations exist
default allow := false

allow if {
    count(violations) == 0
}

# Collect all violations as a set of reason strings
violations contains reason if {
    input.error_rate_pct > data.thresholds.canary.max_error_rate_pct
    reason := sprintf(
        "error rate %.2f%% exceeds maximum %.2f%%",
        [input.error_rate_pct, data.thresholds.canary.max_error_rate_pct]
    )
}

violations contains reason if {
    input.p99_latency_ms > data.thresholds.canary.max_p99_latency_ms
    reason := sprintf(
        "P99 latency %.1fms exceeds maximum %dms",
        [input.p99_latency_ms, data.thresholds.canary.max_p99_latency_ms]
    )
}

# decision is the full response object the CLI reads
decision := {
    "allow": allow,
    "violations": violations,
    "summary": summary,
}

summary := "canary health checks passed" if {
    count(violations) == 0
}

summary := sprintf("%d canary check(s) failed", [count(violations)]) if {
    count(violations) > 0
}
