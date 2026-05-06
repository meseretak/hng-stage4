package swiftdeploy.canary

# All threshold values come from data.json — never hardcoded here.

default allow = false

allow {
    count(violations) == 0
}

violations[msg] {
    input.error_rate_percent > data.canary.max_error_rate_percent
    msg := sprintf(
        "Error rate %.2f%% exceeds maximum %.2f%%",
        [input.error_rate_percent, data.canary.max_error_rate_percent]
    )
}

violations[msg] {
    input.p99_latency_ms > data.canary.max_p99_latency_ms
    msg := sprintf(
        "P99 latency %.0fms exceeds maximum %.0fms",
        [input.p99_latency_ms, data.canary.max_p99_latency_ms]
    )
}
