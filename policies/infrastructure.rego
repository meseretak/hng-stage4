package swiftdeploy.infrastructure

# All threshold values come from data.json — never hardcoded here.

default allow = false

allow {
    count(violations) == 0
}

violations[msg] {
    input.disk_free_gb < data.infrastructure.min_disk_free_gb
    msg := sprintf(
        "Disk free %.1f GB is below minimum %.1f GB",
        [input.disk_free_gb, data.infrastructure.min_disk_free_gb]
    )
}

violations[msg] {
    input.cpu_load > data.infrastructure.max_cpu_load
    msg := sprintf(
        "CPU load %.2f exceeds maximum %.2f",
        [input.cpu_load, data.infrastructure.max_cpu_load]
    )
}

violations[msg] {
    input.mem_percent > data.infrastructure.max_mem_percent
    msg := sprintf(
        "Memory usage %.1f%% exceeds maximum %.1f%%",
        [input.mem_percent, data.infrastructure.max_mem_percent]
    )
}
