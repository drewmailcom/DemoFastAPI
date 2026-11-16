"""Fictional demo data used by the seed and the demo scripts."""

DEMO_PASSWORD = "demo1234"

USERS = [
    ("admin", "ADMIN"),
    ("analyst1", "ANALYST"),
    ("analyst2", "ANALYST"),
    ("support", "READ_ONLY"),
]

# Inserted in this order, so their ids are 1..5.
CUSTOMERS = [
    ("Alpha Bank", 5),
    ("Beta Hospital", 4),
    ("Gamma Retail", 3),
    ("Delta Logistics", 2),
    ("Epsilon Blog", 1),
]

# (name, priority, conditions); ids are 1..6 in this order.
SIGNATURES = [
    ("Mimikatz credential dumping", 5, {"process.name": "mimikatz.exe"}),
    ("LSASS memory access", 4, {"event_type": "process_access", "target.process": "lsass.exe"}),
    ("Encoded PowerShell command", 3, {"process.name": "powershell.exe", "process.encoded_command": "true"}),
    ("RDP brute force", 3, {"event_type": "auth_failure_burst", "service": "rdp"}),
    # Overlaps with "Encoded PowerShell command" on purpose, to demo multiple matches.
    ("PowerShell execution", 2, {"process.name": "powershell.exe"}),
    ("EICAR test file", 1, {"file.name": "eicar.com"}),
]

INCIDENTS = [
    {"customer_id": 1, "host": "bank-dc01", "process": {"name": "mimikatz.exe", "user": "svc_backup"}},
    {"customer_id": 2, "host": "hosp-ws17", "process": {"name": "powershell.exe", "encoded_command": True}},
    {"customer_id": 3, "host": "pos-112", "event_type": "auth_failure_burst", "service": "rdp", "attempts": 450},
    {"customer_id": 4, "host": "wh-srv02", "event_type": "process_access", "target": {"process": "lsass.exe"}},
    {"customer_id": 5, "host": "blog-web", "file": {"name": "eicar.com", "path": "/tmp/eicar.com"}},
    {"customer_id": 3, "host": "pos-207", "process": {"name": "powershell.exe", "encoded_command": False}},
    {"customer_id": 1, "host": "bank-ws42", "process": {"name": "powershell.exe", "encoded_command": True}},
    {"customer_id": 2, "host": "hosp-ws03", "process": {"name": "notepad.exe"}},  # no signature
    {"customer_id": 99, "host": "unknown", "process": {"name": "mimikatz.exe"}},  # unknown customer
]
