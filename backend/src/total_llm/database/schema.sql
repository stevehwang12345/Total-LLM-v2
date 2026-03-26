CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    device_type TEXT NOT NULL,
    manufacturer TEXT NOT NULL,
    ip_address TEXT NOT NULL,
    port INTEGER NOT NULL,
    protocol TEXT NOT NULL,
    location TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'online',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    security_grade TEXT NOT NULL DEFAULT 'GRADE_1',
    firmware_version TEXT,
    last_health_check TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS alarms (
    alarm_id TEXT PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    severity TEXT NOT NULL,
    description TEXT NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    acknowledged BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'triggered',
    priority TEXT NOT NULL DEFAULT 'P3',
    analysis_id TEXT,
    resolved_at TIMESTAMPTZ,
    resolved_by TEXT,
    investigation_notes TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    conversation_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
    message_id BIGSERIAL PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS documents_meta (
    doc_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size BIGINT NOT NULL,
    content_type TEXT,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS reports (
    report_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    report_type TEXT NOT NULL DEFAULT 'security',
    file_path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    date_range_start DATE,
    date_range_end DATE,
    generated_by TEXT,
    data_snapshot JSONB
);

CREATE TABLE IF NOT EXISTS analyses (
    analysis_id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    size BIGINT NOT NULL,
    content_type TEXT,
    location TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    result JSONB NOT NULL,
    media_type TEXT NOT NULL DEFAULT 'image'
);

CREATE TABLE IF NOT EXISTS device_health_logs (
    id BIGSERIAL PRIMARY KEY,
    device_id TEXT NOT NULL REFERENCES devices(device_id) ON DELETE CASCADE,
    checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    reachable BOOLEAN NOT NULL,
    port_open BOOLEAN NOT NULL,
    latency_ms INTEGER,
    status TEXT NOT NULL
);

INSERT INTO devices (device_id, device_type, manufacturer, ip_address, port, protocol, location, status)
VALUES
    ('CCTV-001', 'CCTV', 'Hanwha Vision', '192.168.10.11', 554, 'RTSP', 'Gate A', 'online'),
    ('CCTV-002', 'CCTV', 'Axis', '192.168.10.12', 554, 'RTSP', 'Warehouse', 'online'),
    ('ACU-001', 'ACU', 'Honeywell', '192.168.20.21', 502, 'Modbus', 'Control Room', 'online'),
    ('ACU-002', 'ACU', 'Siemens', '192.168.20.22', 502, 'Modbus', 'Server Room', 'maintenance')
ON CONFLICT (device_id) DO NOTHING;
