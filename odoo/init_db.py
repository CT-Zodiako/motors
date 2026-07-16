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
    # query-categories change: idempotent migration steps (order matters)
    execute("""
        CREATE TABLE IF NOT EXISTS query_categories (
            id          SERIAL PRIMARY KEY,
            name        VARCHAR(100) NOT NULL UNIQUE,
            description TEXT,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    execute("""
        ALTER TABLE odoo_queries
        ADD COLUMN IF NOT EXISTS category_id INTEGER REFERENCES query_categories(id)
    """)
    execute("""
        INSERT INTO query_categories (name, description)
        VALUES ('General', 'Default category')
        ON CONFLICT (name) DO NOTHING
    """)
    execute("""
        UPDATE odoo_queries
        SET category_id = (SELECT id FROM query_categories WHERE name = 'General')
        WHERE category_id IS NULL
    """)
    print("Tables odoo_queries, query_categories ready.")

if __name__ == "__main__":
    init()
