-- Phantom Browser — Phase 1 schema
--
-- One row per browser profile. The fingerprint identity is composed of 6
-- persisted JSON blobs (fingerprint_json, seeds_json, webgl_json, fonts_json,
-- voices_json, misc_json) that together produce a stable launch config.
-- See SKILL.md "THE load-bearing insight #2" for why each blob must be locked.
--
-- Identity blobs are generated ONCE on profile create and never regenerated.
-- Per-launch randomisation in `launch_options()` is suppressed by pre-setting
-- every random field into `config=` before the call.

CREATE TABLE IF NOT EXISTS profiles (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    name               TEXT    NOT NULL UNIQUE,
    platform_tag       TEXT    NOT NULL,      -- 'facebook' | 'tiktok' | 'chatgpt' | 'custom'
    status             TEXT    NOT NULL DEFAULT 'idle',   -- idle | running | warming | dead

    -- Proxy (1:1 with profile, mandatory for fb/tiktok)
    proxy_host         TEXT    NOT NULL,
    proxy_port         INTEGER NOT NULL,
    proxy_user         TEXT    NOT NULL,
    proxy_pass         TEXT    NOT NULL,
    proxy_source       TEXT    NOT NULL DEFAULT 'manual', -- 'manual' | 'iproyal' | 'file'

    -- Fingerprint identity blobs (all generated once on create)
    fingerprint_json   TEXT    NOT NULL,      -- BrowserForge Fingerprint.dumps()
    seeds_json         TEXT    NOT NULL,      -- {canvas:seed, audio:seed, fonts:spacing_seed}
    webgl_json         TEXT    NOT NULL,      -- sample_webgl('win') dict (vendor/renderer/params locked)
    fonts_json         TEXT    NOT NULL,      -- _generate_random_font_subset('windows')
    voices_json        TEXT    NOT NULL,      -- _generate_random_voice_subset('windows')
    misc_json          TEXT    NOT NULL,      -- {window.history.length, window.screenY}

    -- Target OS (for fingerprint spoofing; we always spoof 'windows' for now)
    target_os          TEXT    NOT NULL DEFAULT 'windows',

    -- Timezone + locale override (proxy-geo override; wins over GeoIP via setdefault)
    timezone           TEXT,                  -- e.g. 'America/Denver'; NULL = let GeoIP pick
    locale_language    TEXT    NOT NULL DEFAULT 'en',
    locale_region      TEXT    NOT NULL DEFAULT 'US',
    navigator_language TEXT    NOT NULL DEFAULT 'en-US',

    -- Data dir for persistent cookies/session (per-profile)
    user_data_dir      TEXT    NOT NULL,      -- absolute path, created on launch

    notes              TEXT    DEFAULT '',
    created_at         TEXT    NOT NULL DEFAULT (datetime('now')),
    updated_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS running_instances (
    profile_id    INTEGER PRIMARY KEY,
    pid           INTEGER NOT NULL,
    started_at    TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (profile_id) REFERENCES profiles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_profiles_platform ON profiles(platform_tag);
CREATE INDEX IF NOT EXISTS idx_profiles_status   ON profiles(status);
CREATE INDEX IF NOT EXISTS idx_profiles_proxy    ON profiles(proxy_host, proxy_port);
