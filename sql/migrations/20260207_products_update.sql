-- ================================================================
-- MIGRATION: Align products table with SQLAlchemy model
-- Date: 2025-02-07
-- ================================================================
--
-- HOW TO RUN:
--   1. Open Supabase SQL Editor.
--   2. Run STEP 1 (PRECHECK) alone first. Check the results.
--      - If 0 rows returned: no duplicates, proceed to STEP 2.
--      - If rows returned: you have duplicate SKUs. Run STEP 2A
--        (DEDUPE) first, then STEP 2.
--   3. Run STEP 2 (MIGRATION) to add columns, drop NOT NULLs,
--      and switch the unique constraint.
--
-- NOTES:
--   - All statements use IF NOT EXISTS / IF EXISTS guards where
--     possible, so re-running is safe.
--   - Existing data is preserved. No rows are deleted unless you
--     explicitly run the DEDUPE section, and even then they are
--     moved to a backup table first.
-- ================================================================


-- ================================================================
-- STEP 1: PRECHECK - Find duplicate SKUs
-- ================================================================
-- Run this SELECT alone first to see if duplicates exist.
-- If the result set is empty, skip directly to STEP 2.
-- ================================================================

-- SELECT sku, COUNT(*) AS cnt
-- FROM products
-- GROUP BY sku
-- HAVING COUNT(*) > 1
-- ORDER BY cnt DESC;


-- ================================================================
-- STEP 2A (OPTIONAL): DEDUPE - Only run if STEP 1 found duplicates
-- ================================================================
-- This block:
--   a) Creates a backup table products_duplicates_backup.
--   b) Copies duplicate rows (all except the newest per sku) into it.
--   c) Deletes those duplicate rows from products.
--
-- After running, re-run STEP 1 to confirm 0 duplicates remain,
-- then proceed to STEP 2.
-- ================================================================

-- BEGIN;
--
-- -- 2A.1: Create backup table (same structure as products + backup metadata)
-- CREATE TABLE IF NOT EXISTS products_duplicates_backup (
--     backup_id   BIGSERIAL PRIMARY KEY,
--     backed_up_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
--     -- original columns copied verbatim:
--     id          UUID,
--     tenant_id   UUID,
--     sku         VARCHAR(100),
--     name        VARCHAR(255),
--     brand       VARCHAR(255),
--     price       DOUBLE PRECISION,
--     original_price DOUBLE PRECISION,
--     url         VARCHAR(500),
--     image_url   VARCHAR(500),
--     sizes       JSONB,
--     gender      VARCHAR(50),
--     currency    VARCHAR(10),
--     fit_type    VARCHAR(50),
--     fabric_composition JSONB,
--     measurements JSONB,
--     category    VARCHAR(100),
--     is_active   BOOLEAN,
--     created_at  TIMESTAMP WITH TIME ZONE,
--     updated_at  TIMESTAMP WITH TIME ZONE
-- );
--
-- -- 2A.2: Copy duplicates to backup (keep the newest per sku)
-- INSERT INTO products_duplicates_backup (
--     id, tenant_id, sku, name, brand, price, original_price,
--     url, image_url, sizes, gender, currency,
--     fit_type, fabric_composition, measurements,
--     category, is_active, created_at, updated_at
-- )
-- SELECT
--     p.id, p.tenant_id, p.sku, p.name, p.brand, p.price, p.original_price,
--     p.url, p.image_url, p.sizes, p.gender, p.currency,
--     p.fit_type, p.fabric_composition, p.measurements,
--     p.category, p.is_active, p.created_at, p.updated_at
-- FROM products p
-- INNER JOIN (
--     -- For each sku with duplicates, find all rows that are NOT the newest
--     SELECT id
--     FROM (
--         SELECT id,
--                ROW_NUMBER() OVER (
--                    PARTITION BY sku
--                    ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
--                ) AS rn
--         FROM products
--     ) ranked
--     WHERE rn > 1
-- ) dupes ON dupes.id = p.id;
--
-- -- 2A.3: Delete the duplicate rows from products
-- DELETE FROM products
-- WHERE id IN (
--     SELECT id
--     FROM (
--         SELECT id,
--                ROW_NUMBER() OVER (
--                    PARTITION BY sku
--                    ORDER BY COALESCE(updated_at, created_at) DESC, id DESC
--                ) AS rn
--         FROM products
--     ) ranked
--     WHERE rn > 1
-- );
--
-- COMMIT;


-- ================================================================
-- STEP 2: MIGRATION - Column additions, NOT NULL drops, constraint
-- ================================================================
-- Safe to run multiple times (idempotent).
-- ================================================================

BEGIN;

-- ---------------------------------------------------------------
-- 2.1: Add missing columns (IF NOT EXISTS prevents errors on re-run)
-- ---------------------------------------------------------------
ALTER TABLE products ADD COLUMN IF NOT EXISTS brand          VARCHAR(255);
ALTER TABLE products ADD COLUMN IF NOT EXISTS price          DOUBLE PRECISION;
ALTER TABLE products ADD COLUMN IF NOT EXISTS original_price DOUBLE PRECISION;
ALTER TABLE products ADD COLUMN IF NOT EXISTS url            VARCHAR(500);
ALTER TABLE products ADD COLUMN IF NOT EXISTS image_url      VARCHAR(500);
ALTER TABLE products ADD COLUMN IF NOT EXISTS sizes          JSONB;
ALTER TABLE products ADD COLUMN IF NOT EXISTS gender         VARCHAR(50);
ALTER TABLE products ADD COLUMN IF NOT EXISTS currency       VARCHAR(10) DEFAULT 'TRY';

-- ---------------------------------------------------------------
-- 2.2: Drop NOT NULL on columns that the model now allows as NULL
-- ---------------------------------------------------------------
-- These are safe even if the column is already nullable.
ALTER TABLE products ALTER COLUMN tenant_id            DROP NOT NULL;
ALTER TABLE products ALTER COLUMN fit_type             DROP NOT NULL;
ALTER TABLE products ALTER COLUMN fabric_composition   DROP NOT NULL;
ALTER TABLE products ALTER COLUMN measurements         DROP NOT NULL;

-- ---------------------------------------------------------------
-- 2.3: Replace unique constraint
--   Drop old per-tenant constraint, add global unique(sku).
-- ---------------------------------------------------------------
ALTER TABLE products DROP CONSTRAINT IF EXISTS unique_sku_per_tenant;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname   = 'unique_sku'
          AND conrelid  = 'products'::regclass
    ) THEN
        -- This will fail if duplicate skus still exist.
        -- Run STEP 1 precheck & STEP 2A dedupe first in that case.
        ALTER TABLE products ADD CONSTRAINT unique_sku UNIQUE (sku);
    END IF;
END
$$;

COMMIT;
