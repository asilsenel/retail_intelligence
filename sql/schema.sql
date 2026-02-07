-- ============================================
-- FitEngine API - PostgreSQL/Supabase Schema
-- ============================================
-- 
-- Run this in your Supabase SQL Editor or 
-- directly against your PostgreSQL database.
--
-- Tables:
--   1. tenants - Brand/client information
--   2. products - Product measurement data
--   3. size_charts - Base size guides
--   4. widget_events - Analytics/tracking
-- ============================================

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================
-- TENANTS TABLE
-- Stores brand/client information and API keys
-- ============================================
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL,
    api_key VARCHAR(64) UNIQUE NOT NULL,
    api_secret VARCHAR(128) NOT NULL,
    contact_email VARCHAR(255),
    website_url VARCHAR(500),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Index for API key lookups (most common query)
CREATE INDEX idx_tenants_api_key ON tenants(api_key);
CREATE INDEX idx_tenants_is_active ON tenants(is_active);

-- Trigger to update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tenants_updated_at
    BEFORE UPDATE ON tenants
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- PRODUCTS TABLE
-- Product catalog with measurement specifications
-- ============================================
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID REFERENCES tenants(id) ON DELETE CASCADE,
    sku VARCHAR(100) NOT NULL,
    name VARCHAR(255) NOT NULL,
    brand VARCHAR(255),
    price DOUBLE PRECISION,
    original_price DOUBLE PRECISION,
    url VARCHAR(500),
    image_url VARCHAR(500),
    sizes JSONB,
    gender VARCHAR(50),
    currency VARCHAR(10) DEFAULT 'TRY',
    fit_type VARCHAR(50) CHECK (fit_type IN ('slim_fit', 'regular_fit', 'loose_fit', 'oversized')),
    fabric_composition JSONB,
    -- Example: {"cotton": 95, "elastane": 5}
    measurements JSONB,
    -- Example: {"S": {"chest_width": 104, "length": 72}, "M": {...}}
    category VARCHAR(100),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    -- Unique SKU (global)
    CONSTRAINT unique_sku UNIQUE (sku)
);

-- Indexes for common queries
CREATE INDEX idx_products_tenant_id ON products(tenant_id);
CREATE INDEX idx_products_sku ON products(sku);
CREATE INDEX idx_products_is_active ON products(is_active);
CREATE INDEX idx_products_category ON products(category);

-- GIN index for JSONB queries
CREATE INDEX idx_products_measurements ON products USING GIN (measurements);

CREATE TRIGGER update_products_updated_at
    BEFORE UPDATE ON products
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- SIZE_CHARTS TABLE
-- Base size guides for brands (fallback)
-- ============================================
CREATE TABLE size_charts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    category VARCHAR(100) NOT NULL,
    size_code VARCHAR(10) NOT NULL,
    measurements JSONB NOT NULL,
    -- Example: {"chest_min": 96, "chest_max": 102, "length_min": 70, "length_max": 73}
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    
    -- Unique size per chart per tenant
    CONSTRAINT unique_size_per_chart UNIQUE (tenant_id, name, size_code)
);

CREATE INDEX idx_size_charts_tenant_id ON size_charts(tenant_id);
CREATE INDEX idx_size_charts_category ON size_charts(category);

-- ============================================
-- WIDGET_EVENTS TABLE
-- Analytics for tracking widget interactions
-- ============================================
CREATE TABLE widget_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    product_id UUID NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL,
    -- Denormalized for performance
    recommended_size VARCHAR(10) NOT NULL,
    confidence_score INTEGER NOT NULL CHECK (confidence_score >= 0 AND confidence_score <= 100),
    user_input JSONB NOT NULL,
    -- Example: {"height": 180, "weight": 85, "body_shape": "average"}
    user_agent TEXT,
    referrer_url VARCHAR(500),
    session_id VARCHAR(100),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);

-- Indexes for analytics queries
CREATE INDEX idx_widget_events_product_id ON widget_events(product_id);
CREATE INDEX idx_widget_events_tenant_id ON widget_events(tenant_id);
CREATE INDEX idx_widget_events_created_at ON widget_events(created_at);
CREATE INDEX idx_widget_events_recommended_size ON widget_events(recommended_size);

-- Composite index for common analytics query
CREATE INDEX idx_widget_events_tenant_date ON widget_events(tenant_id, created_at);

-- ============================================
-- ROW LEVEL SECURITY (RLS) FOR SUPABASE
-- ============================================

-- Enable RLS on all tables
ALTER TABLE tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE products ENABLE ROW LEVEL SECURITY;
ALTER TABLE size_charts ENABLE ROW LEVEL SECURITY;
ALTER TABLE widget_events ENABLE ROW LEVEL SECURITY;

-- Policies (adjust based on your auth setup)
-- These are examples - customize for your needs

-- Service role has full access
CREATE POLICY "Service role full access on tenants"
    ON tenants FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on products"
    ON products FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on size_charts"
    ON size_charts FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access on widget_events"
    ON widget_events FOR ALL
    USING (auth.role() = 'service_role');

-- ============================================
-- SAMPLE DATA (for testing)
-- ============================================

-- Insert test tenant
INSERT INTO tenants (id, name, api_key, api_secret, contact_email, website_url, is_active)
VALUES (
    '00000000-0000-0000-0000-000000000001',
    'Test Brand',
    'test-api-key',
    'test-api-secret-hash',
    'test@example.com',
    'https://testbrand.com',
    TRUE
);

-- Insert sample product
INSERT INTO products (id, tenant_id, sku, name, fit_type, fabric_composition, measurements, category)
VALUES (
    '11111111-1111-1111-1111-111111111111',
    '00000000-0000-0000-0000-000000000001',
    'SHIRT-001',
    'Classic Oxford Shirt',
    'regular_fit',
    '{"cotton": 100}',
    '{
        "S": {"chest_width": 104, "length": 72, "shoulder_width": 44},
        "M": {"chest_width": 110, "length": 74, "shoulder_width": 46},
        "L": {"chest_width": 116, "length": 76, "shoulder_width": 48},
        "XL": {"chest_width": 122, "length": 78, "shoulder_width": 50}
    }',
    'shirts'
);

-- Insert sample size chart
INSERT INTO size_charts (tenant_id, name, category, size_code, measurements)
VALUES 
    ('00000000-0000-0000-0000-000000000001', 'Mens Shirts', 'shirts', 'S', 
     '{"chest_min": 86, "chest_max": 91, "waist_min": 71, "waist_max": 76}'),
    ('00000000-0000-0000-0000-000000000001', 'Mens Shirts', 'shirts', 'M', 
     '{"chest_min": 91, "chest_max": 96, "waist_min": 76, "waist_max": 81}'),
    ('00000000-0000-0000-0000-000000000001', 'Mens Shirts', 'shirts', 'L', 
     '{"chest_min": 96, "chest_max": 102, "waist_min": 81, "waist_max": 86}'),
    ('00000000-0000-0000-0000-000000000001', 'Mens Shirts', 'shirts', 'XL', 
     '{"chest_min": 102, "chest_max": 107, "waist_min": 86, "waist_max": 91}');

-- ============================================
-- USEFUL QUERIES FOR ANALYTICS
-- ============================================

-- View: Widget usage per product
CREATE OR REPLACE VIEW v_product_widget_stats AS
SELECT 
    p.id AS product_id,
    p.sku,
    p.name,
    COUNT(we.id) AS total_checks,
    MODE() WITHIN GROUP (ORDER BY we.recommended_size) AS most_common_size,
    AVG(we.confidence_score) AS avg_confidence
FROM products p
LEFT JOIN widget_events we ON p.id = we.product_id
GROUP BY p.id, p.sku, p.name;

-- View: Daily widget usage
CREATE OR REPLACE VIEW v_daily_widget_usage AS
SELECT 
    tenant_id,
    DATE(created_at) AS date,
    COUNT(*) AS total_checks,
    COUNT(DISTINCT session_id) AS unique_users,
    AVG(confidence_score) AS avg_confidence
FROM widget_events
GROUP BY tenant_id, DATE(created_at)
ORDER BY date DESC;
