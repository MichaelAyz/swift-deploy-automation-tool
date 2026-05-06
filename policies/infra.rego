package infra

import rego.v1

# allow is true only when no violations exist
default allow := false

allow if {
    count(violations) == 0
}

# Collect all violations as a set of reason strings
violations contains reason if {
    input.disk_free_gb < data.thresholds.infra.min_disk_free_gb
    reason := sprintf(
        "disk free %.1fGB is below minimum %.1fGB",
        [input.disk_free_gb, data.thresholds.infra.min_disk_free_gb]
    )
}

violations contains reason if {
    input.cpu_load > data.thresholds.infra.max_cpu_load
    reason := sprintf(
        "CPU load %.2f exceeds maximum %.2f",
        [input.cpu_load, data.thresholds.infra.max_cpu_load]
    )
}

# decision is the full response object the CLI reads
decision := {
    "allow": allow,
    "violations": violations,
    "summary": summary,
}

summary := "all infrastructure checks passed" if {
    count(violations) == 0
}

summary := sprintf("%d infrastructure check(s) failed", [count(violations)]) if {
    count(violations) > 0
}
