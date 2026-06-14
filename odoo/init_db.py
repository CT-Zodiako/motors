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
    print("Table odoo_queries ready.")

if __name__ == "__main__":
    init()
