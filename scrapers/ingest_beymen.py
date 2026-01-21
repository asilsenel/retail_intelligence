"""
Beymen Product Scraper for FitEngine API

Scrapes product data from Beymen (Men's Shirts) and sends to FitEngine API.
Uses Playwright for dynamic content and BeautifulSoup for parsing.
"""
import asyncio
import re
import httpx
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout


# =============================================================================
# CONFIGURATION
# =============================================================================

API_BASE_URL = "http://localhost:8000"
API_KEY = "test-api-key"

# Sample Beymen product URLs - Replace with real URLs
PRODUCT_URLS = [
    # Men's Shirts - Replace these with actual Beymen product URLs
    "https://www.beymen.com/p/beymen-club-slim-fit-klasik-yaka-gomlek-123456",
    "https://www.beymen.com/p/beymen-club-regular-fit-gomlek-789012",
    "https://www.beymen.com/p/network-slim-fit-pamuklu-gomlek-345678",
]

# =============================================================================
# FALLBACK SIZE CHARTS (When website doesn't provide one)
# =============================================================================

FALLBACK_SIZE_CHARTS = {
    "beymen club": {
        "S": {"chest_width": 102, "length": 72, "shoulder_width": 44},
        "M": {"chest_width": 108, "length": 74, "shoulder_width": 46},
        "L": {"chest_width": 114, "length": 76, "shoulder_width": 48},
        "XL": {"chest_width": 120, "length": 78, "shoulder_width": 50},
        "XXL": {"chest_width": 126, "length": 80, "shoulder_width": 52},
    },
    "network": {
        "S": {"chest_width": 100, "length": 71, "shoulder_width": 43},
        "M": {"chest_width": 106, "length": 73, "shoulder_width": 45},
        "L": {"chest_width": 112, "length": 75, "shoulder_width": 47},
        "XL": {"chest_width": 118, "length": 77, "shoulder_width": 49},
    },
    "default": {
        "S": {"chest_width": 104, "length": 72, "shoulder_width": 44},
        "M": {"chest_width": 110, "length": 74, "shoulder_width": 46},
        "L": {"chest_width": 116, "length": 76, "shoulder_width": 48},
        "XL": {"chest_width": 122, "length": 78, "shoulder_width": 50},
    }
}


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ProductData:
    """Scraped product data"""
    url: str
    title: str
    brand: str
    price: Optional[str]
    image_url: Optional[str]
    fabric_composition: Dict[str, float]
    measurements: Dict[str, Dict[str, float]]
    fit_type: str
    sku: str


# =============================================================================
# FABRIC COMPOSITION PARSER
# =============================================================================

def parse_fabric_composition(text: str) -> Dict[str, float]:
    """
    Parse fabric composition from Turkish text.
    
    Examples:
        "%97 Pamuk, %3 Elastan" -> {"cotton": 97, "elastane": 3}
        "100% Cotton" -> {"cotton": 100}
    """
    fabric_mapping = {
        "pamuk": "cotton",
        "cotton": "cotton",
        "elastan": "elastane",
        "elastane": "elastane",
        "polyester": "polyester",
        "viskon": "viscose",
        "viscose": "viscose",
        "keten": "linen",
        "linen": "linen",
        "yün": "wool",
        "wool": "wool",
        "ipek": "silk",
        "silk": "silk",
        "naylon": "nylon",
        "nylon": "nylon",
        "likra": "lycra",
        "lycra": "lycra",
        "spandex": "spandex",
    }
    
    composition = {}
    
    # Pattern: %97 Pamuk or 97% Cotton
    pattern = r'[%]?\s*(\d+)\s*[%]?\s*([a-zA-ZığüşöçĞÜŞÖÇİ]+)'
    matches = re.findall(pattern, text, re.IGNORECASE)
    
    for percentage, fabric in matches:
        fabric_lower = fabric.lower()
        for tr_name, en_name in fabric_mapping.items():
            if tr_name in fabric_lower:
                composition[en_name] = float(percentage)
                break
    
    # If nothing found, assume 100% cotton
    if not composition:
        composition = {"cotton": 100}
    
    return composition


# =============================================================================
# FIT TYPE DETECTOR
# =============================================================================

def detect_fit_type(title: str, description: str = "") -> str:
    """Detect fit type from product title and description."""
    text = (title + " " + description).lower()
    
    if "slim fit" in text or "slim-fit" in text or "dar kalıp" in text:
        return "slim_fit"
    elif "regular fit" in text or "regular-fit" in text or "normal kalıp" in text:
        return "regular_fit"
    elif "loose" in text or "oversize" in text or "bol kalıp" in text:
        return "loose_fit"
    elif "relaxed" in text:
        return "loose_fit"
    else:
        return "regular_fit"  # Default


# =============================================================================
# SIZE CHART PARSER
# =============================================================================

def parse_size_chart_table(html: str) -> Dict[str, Dict[str, float]]:
    """
    Parse size chart HTML table into structured measurements.
    
    Returns:
        {"S": {"chest_width": 104, "length": 72}, "M": {...}}
    """
    soup = BeautifulSoup(html, 'html.parser')
    measurements = {}
    
    # Find table
    table = soup.find('table')
    if not table:
        return {}
    
    # Get headers
    headers = []
    header_row = table.find('tr')
    if header_row:
        for th in header_row.find_all(['th', 'td']):
            headers.append(th.get_text(strip=True).lower())
    
    # Map Turkish headers to English keys
    header_mapping = {
        "beden": "size",
        "size": "size",
        "göğüs": "chest_width",
        "chest": "chest_width",
        "göğüs genişliği": "chest_width",
        "boy": "length",
        "length": "length",
        "uzunluk": "length",
        "omuz": "shoulder_width",
        "shoulder": "shoulder_width",
        "omuz genişliği": "shoulder_width",
        "kol": "sleeve_length",
        "sleeve": "sleeve_length",
        "bel": "waist",
        "waist": "waist",
    }
    
    # Parse rows
    rows = table.find_all('tr')[1:]  # Skip header
    for row in rows:
        cells = row.find_all(['td', 'th'])
        if len(cells) < 2:
            continue
        
        size_code = None
        size_measurements = {}
        
        for i, cell in enumerate(cells):
            if i >= len(headers):
                break
            
            header = headers[i]
            value = cell.get_text(strip=True)
            
            # Map header to key
            key = header_mapping.get(header, header)
            
            if key == "size":
                size_code = value.upper()
            else:
                # Try to parse as number
                try:
                    # Handle "104-106" ranges by taking first value
                    if "-" in value:
                        value = value.split("-")[0]
                    size_measurements[key] = float(re.sub(r'[^\d.]', '', value))
                except ValueError:
                    pass
        
        if size_code and size_measurements:
            measurements[size_code] = size_measurements
    
    return measurements


# =============================================================================
# PRODUCT SCRAPER
# =============================================================================

async def scrape_product(page: Page, url: str) -> Optional[ProductData]:
    """
    Scrape a single product from Beymen.
    
    Returns ProductData or None if scraping fails.
    """
    print(f"  📦 Scraping: {url}")
    
    try:
        # Navigate to product page
        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(2000)  # Wait for JS to load
        
        # Extract basic info
        title = ""
        brand = ""
        price = ""
        image_url = ""
        fabric_text = ""
        
        # Title
        title_el = await page.query_selector('h1.o-productDetail__title, h1[data-testid="product-name"]')
        if title_el:
            title = await title_el.inner_text()
        
        # Brand
        brand_el = await page.query_selector('.o-productDetail__brand, [data-testid="product-brand"]')
        if brand_el:
            brand = await brand_el.inner_text()
        
        # Price
        price_el = await page.query_selector('.m-price__current, [data-testid="product-price"]')
        if price_el:
            price = await price_el.inner_text()
        
        # Image
        img_el = await page.query_selector('.o-productDetail__image img, [data-testid="product-image"]')
        if img_el:
            image_url = await img_el.get_attribute('src') or ""
        
        # Fabric composition from description
        desc_el = await page.query_selector('.o-productDetail__description, [data-testid="product-description"]')
        if desc_el:
            desc_text = await desc_el.inner_text()
            fabric_text = desc_text
        
        # Also check product details section
        details_el = await page.query_selector('.o-productDetail__details, [data-testid="product-details"]')
        if details_el:
            details_text = await details_el.inner_text()
            if "%" in details_text:
                fabric_text = details_text
        
        # Parse fabric
        fabric_composition = parse_fabric_composition(fabric_text)
        
        # Detect fit type
        fit_type = detect_fit_type(title, fabric_text)
        
        # Try to get size chart
        measurements = {}
        
        try:
            # Look for size chart button
            size_btn = await page.query_selector(
                'button:has-text("Beden Tablosu"), '
                'a:has-text("Beden Tablosu"), '
                '[data-testid="size-chart-button"]'
            )
            
            if size_btn:
                await size_btn.click()
                await page.wait_for_timeout(1500)
                
                # Wait for modal
                modal = await page.query_selector('.size-chart-modal, .o-modal, [data-testid="size-chart-modal"]')
                if modal:
                    modal_html = await modal.inner_html()
                    measurements = parse_size_chart_table(modal_html)
                    
                    # Close modal
                    close_btn = await page.query_selector('.o-modal__close, [data-testid="close-modal"]')
                    if close_btn:
                        await close_btn.click()
                
        except PlaywrightTimeout:
            print(f"    ⚠️  Size chart modal not found, using fallback")
        except Exception as e:
            print(f"    ⚠️  Error getting size chart: {e}")
        
        # Use fallback if no measurements found
        if not measurements:
            brand_lower = brand.lower() if brand else "default"
            for key in FALLBACK_SIZE_CHARTS:
                if key in brand_lower:
                    measurements = FALLBACK_SIZE_CHARTS[key]
                    print(f"    ℹ️  Using fallback size chart for '{key}'")
                    break
            else:
                measurements = FALLBACK_SIZE_CHARTS["default"]
                print(f"    ℹ️  Using default fallback size chart")
        
        # Generate SKU from URL
        sku = url.split("/")[-1][:50] or f"beymen-{hash(url) % 10000}"
        
        # Use placeholder data if title is empty (demo mode)
        if not title:
            title = f"Demo Shirt {sku[:10]}"
            brand = "Beymen Club"
            print(f"    ⚠️  Using demo data (page structure may have changed)")
        
        return ProductData(
            url=url,
            title=title.strip(),
            brand=brand.strip() if brand else "Beymen Club",
            price=price.strip() if price else None,
            image_url=image_url,
            fabric_composition=fabric_composition,
            measurements=measurements,
            fit_type=fit_type,
            sku=sku
        )
        
    except Exception as e:
        print(f"    ❌ Error scraping {url}: {e}")
        return None


# =============================================================================
# API CLIENT
# =============================================================================

async def ingest_to_api(product: ProductData) -> bool:
    """
    Send product data to FitEngine API.
    
    Returns True if successful.
    """
    payload = {
        "sku": product.sku,
        "name": product.title,
        "fit_type": product.fit_type,
        "fabric_composition": product.fabric_composition,
        "measurements": product.measurements
    }
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{API_BASE_URL}/api/v1/ingest-product",
                json=payload,
                headers={
                    "Content-Type": "application/json",
                    "X-API-Key": API_KEY
                },
                timeout=10.0
            )
            
            if response.status_code == 201:
                data = response.json()
                print(f"    ✅ Ingested: {product.title[:40]}... → ID: {data['product_id']}")
                return True
            else:
                print(f"    ❌ API Error {response.status_code}: {response.text}")
                return False
                
    except httpx.RequestError as e:
        print(f"    ❌ Connection error: {e}")
        return False


# =============================================================================
# MAIN PIPELINE
# =============================================================================

async def run_pipeline(urls: List[str]) -> Dict[str, Any]:
    """
    Run the complete scraping and ingestion pipeline.
    
    Returns summary statistics.
    """
    print("\n" + "="*60)
    print("🚀 FitEngine - Beymen Product Ingestion Pipeline")
    print("="*60 + "\n")
    
    stats = {
        "total": len(urls),
        "scraped": 0,
        "ingested": 0,
        "failed": 0
    }
    
    async with async_playwright() as p:
        # Launch browser
        print("🌐 Launching browser...")
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
        page = await context.new_page()
        
        print(f"\n📋 Processing {len(urls)} products...\n")
        
        for i, url in enumerate(urls, 1):
            print(f"[{i}/{len(urls)}] Processing...")
            
            # Scrape product
            product = await scrape_product(page, url)
            
            if product:
                stats["scraped"] += 1
                
                # Ingest to API
                success = await ingest_to_api(product)
                if success:
                    stats["ingested"] += 1
                else:
                    stats["failed"] += 1
            else:
                stats["failed"] += 1
            
            print()
        
        await browser.close()
    
    # Print summary
    print("\n" + "="*60)
    print("📊 PIPELINE SUMMARY")
    print("="*60)
    print(f"  Total URLs:     {stats['total']}")
    print(f"  Scraped:        {stats['scraped']}")
    print(f"  Ingested:       {stats['ingested']} ✅")
    print(f"  Failed:         {stats['failed']} ❌")
    print("="*60 + "\n")
    
    if stats["ingested"] > 0:
        print(f"🎉 Successfully ingested {stats['ingested']} products into FitEngine!\n")
    
    return stats


# =============================================================================
# DEMO MODE (without real URLs)
# =============================================================================

async def run_demo():
    """
    Run demo ingestion with sample data (no actual scraping).
    Use this when real URLs are not available.
    """
    print("\n" + "="*60)
    print("🎭 FitEngine - DEMO MODE (No actual scraping)")
    print("="*60 + "\n")
    
    demo_products = [
        ProductData(
            url="https://beymen.com/demo-1",
            title="Beymen Club Slim Fit Klasik Yaka Gömlek",
            brand="Beymen Club",
            price="799 TL",
            image_url="https://example.com/shirt1.jpg",
            fabric_composition={"cotton": 97, "elastane": 3},
            measurements=FALLBACK_SIZE_CHARTS["beymen club"],
            fit_type="slim_fit",
            sku="BC-SLIM-001"
        ),
        ProductData(
            url="https://beymen.com/demo-2",
            title="Beymen Club Regular Fit Oxford Gömlek",
            brand="Beymen Club",
            price="899 TL",
            image_url="https://example.com/shirt2.jpg",
            fabric_composition={"cotton": 100},
            measurements=FALLBACK_SIZE_CHARTS["beymen club"],
            fit_type="regular_fit",
            sku="BC-REG-002"
        ),
        ProductData(
            url="https://beymen.com/demo-3",
            title="Network Slim Fit Pamuklu Gömlek",
            brand="Network",
            price="649 TL",
            image_url="https://example.com/shirt3.jpg",
            fabric_composition={"cotton": 95, "elastane": 5},
            measurements=FALLBACK_SIZE_CHARTS["network"],
            fit_type="slim_fit",
            sku="NW-SLIM-003"
        ),
    ]
    
    stats = {"total": len(demo_products), "ingested": 0, "failed": 0}
    
    for product in demo_products:
        print(f"📦 Demo product: {product.title}")
        success = await ingest_to_api(product)
        if success:
            stats["ingested"] += 1
        else:
            stats["failed"] += 1
    
    print("\n" + "="*60)
    print(f"🎉 Successfully ingested {stats['ingested']} demo products into FitEngine!")
    print("="*60 + "\n")
    
    return stats


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    import sys
    
    if "--demo" in sys.argv:
        # Run demo mode without actual scraping
        asyncio.run(run_demo())
    else:
        # Run actual scraping pipeline
        # Note: Replace PRODUCT_URLS with real Beymen URLs
        print("\n⚠️  Note: Using placeholder URLs. Replace PRODUCT_URLS with real Beymen product URLs.")
        print("   Or run with --demo flag for demo mode without scraping.\n")
        
        # For now, run demo mode since we have placeholder URLs
        asyncio.run(run_demo())
