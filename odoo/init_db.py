from db import execute

def init():
    execute("""
        CREATE TABLE IF NOT EXISTS odoo_queries (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            model       VARCHAR(100) NOT NULL,
            method      VARCHAR(50)  NOT NULL DEFAULT 'search_read',
            domain      JSONB        NOT NULL DEFAULT '[]',
            fields      JSONB        NOT NULL DEFAULT '[]',
            limit_val   INTEGER      NOT NULL DEFAULT 100,
            active      BOOLEAN      NOT NULL DEFAULT TRUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS query_schedules (
            id            SERIAL PRIMARY KEY,
            name          VARCHAR(150) NOT NULL,
            query_name    VARCHAR(100) NOT NULL,
            dataset_id    VARCHAR(100) NOT NULL,
            table_id      VARCHAR(100) NOT NULL,
            frequency     VARCHAR(20)  NOT NULL CHECK (frequency IN ('hourly', 'daily', 'weekly', 'monthly')),
            hour          INTEGER      CHECK (hour >= 0 AND hour <= 23),
            minute        INTEGER      CHECK (minute >= 0 AND minute <= 59),
            day_of_week   INTEGER      CHECK (day_of_week >= 0 AND day_of_week <= 6),
            day_of_month  INTEGER      CHECK (day_of_month >= 1 AND day_of_month <= 31),
            interval_hours INTEGER     CHECK (interval_hours >= 1 AND interval_hours <= 24),
            active        BOOLEAN      NOT NULL DEFAULT TRUE,
            last_run_at   TIMESTAMPTZ,
            last_run_status VARCHAR(20),
            last_run_message TEXT,
            created_at    TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    execute("""
        CREATE TABLE IF NOT EXISTS query_schedule_runs (
            id          SERIAL PRIMARY KEY,
            schedule_id INTEGER      NOT NULL REFERENCES query_schedules(id) ON DELETE CASCADE,
            started_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            finished_at TIMESTAMPTZ,
            status      VARCHAR(20)  NOT NULL,
            message     TEXT,
            rows_loaded INTEGER
        )
    """)
    print("Tables odoo_queries, query_schedules, query_schedule_runs ready.")

if __name__ == "__main__":
    init()
