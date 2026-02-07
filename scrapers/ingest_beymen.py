"""
Beymen Product Scraper using ScrapingBee and Regex.
Extracts product data from SSR JSON (BEYMEN.productListMain) and saves to database.
"""
import asyncio
import hashlib
import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import requests
from sqlalchemy import select

# Import database models
# Adjust the import path if your project structure requires it, e.g. from app.models.database
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import get_session_factory, Product

# Configuration
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

SCRAPINGBEE_API_KEY = os.getenv("SCRAPINGBEE_API_KEY")
TARGET_URL = "https://www.beymen.com/tr/erkek-giyim-pantolon-10119"
API_BASE_URL = "https://app.scrapingbee.com/api/v1/"
BASE_URL = "https://www.beymen.com"


def fetch_html(url: str, render_js: bool = False) -> Optional[str]:
    """
    Fetch HTML content using ScrapingBee API.
    """
    if not SCRAPINGBEE_API_KEY:
        logger.error("SCRAPINGBEE_API_KEY not found in environment variables.")
        return None

    params = {
        "api_key": SCRAPINGBEE_API_KEY,
        "url": url,
        # SSR data is usually in script tag. If not found, we'll retry with JS render.
        "render_js": "true" if render_js else "false",
        "premium_proxy": "true",
        "country_code": "tr",
    }
    if render_js:
        params["wait"] = "5000"
    
    try:
        logger.info(f"Fetching URL: {url} via ScrapingBee...")
        response = requests.get(API_BASE_URL, params=params, timeout=60)
        response.raise_for_status()
        return response.text
    except Exception as e:
        logger.error(f"Error fetching URL: {e}")
        return None


def save_debug_html(html: str, label: str) -> Optional[str]:
    """
    Save raw HTML to disk for debugging (e.g., captcha or structural changes).
    """
    if not html:
        return None
    safe_label = re.sub(r"[^a-z0-9]+", "_", (label or "error").lower()).strip("_") or "error"
    filename = f"debug_beymen_error_{safe_label}.html"
    path = os.path.join(os.getcwd(), filename)
    if os.path.exists(path):
        ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(os.getcwd(), f"debug_beymen_error_{safe_label}_{ts}.html")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        logger.warning(f"Saved debug HTML to {path}")
        return path
    except Exception as e:
        logger.error(f"Failed to save debug HTML: {e}")
        return None


def _extract_balanced(text: str, start_index: int, open_char: str, close_char: str) -> Optional[str]:
    """
    Extract a balanced JSON-like substring starting at start_index (which should be open_char).
    Handles strings and escapes to avoid premature closing.
    """
    if start_index < 0 or start_index >= len(text) or text[start_index] != open_char:
        return None

    depth = 0
    in_string = False
    string_char = ""
    escape = False
    start = None

    for i in range(start_index, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == string_char:
                in_string = False
            continue

        if ch in ("'", '"'):
            in_string = True
            string_char = ch
            continue

        if ch == open_char:
            if depth == 0:
                start = i
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0 and start is not None:
                return text[start:i + 1]

    return None


def _safe_json_loads(payload: str) -> Optional[object]:
    """
    Attempt to parse JSON with minor cleanup for trailing commas.
    """
    if not payload:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        cleaned = re.sub(r",\s*([}\]])", r"\1", payload)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            return None


def _ensure_abs_url(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    if url.startswith("//"):
        return f"https:{url}"
    return urljoin(BASE_URL, url)


def _derive_sku(url: Optional[str], name: Optional[str]) -> Optional[str]:
    if url:
        match = re.search(r"(\d{5,})", url)
        if match:
            return f"beymen-{match.group(1)}"
        parsed = urlparse(url)
        slug = parsed.path.strip("/").split("/")[-1]
        if slug:
            return f"beymen-{slug}"
    if name:
        slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
        if slug:
            return f"beymen-{slug}"
    seed = (url or "") + "|" + (name or "")
    if seed.strip("|"):
        digest = hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]
        return f"beymen-{digest}"
    return None


def _normalize_price_string(value: str) -> Optional[float]:
    if not value:
        return None
    cleaned = re.sub(r"[^\d,\\.]", "", value)
    if not cleaned:
        return None
    if cleaned.count(",") == 1 and cleaned.count(".") >= 1:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(",") == 1 and cleaned.count(".") == 0:
        cleaned = cleaned.replace(",", ".")
    else:
        cleaned = cleaned.replace(",", "")
    try:
        return float(cleaned)
    except ValueError:
        return None


def _parse_price(value: object) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value)
    matches = re.findall(r"\d[\d\.,]*", text)
    if not matches:
        return None
    return _normalize_price_string(matches[0])


def _looks_like_product_list(items: object) -> bool:
    if not isinstance(items, list) or not items:
        return False
    sample = items[0]
    if not isinstance(sample, dict):
        return False
    return "productId" in sample or "displayName" in sample


def _find_key_recursive(obj: object, key: str) -> Optional[object]:
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for value in obj.values():
            found = _find_key_recursive(value, key)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_key_recursive(item, key)
            if found is not None:
                return found
    return None


def _extract_array_from_text(text: str) -> Optional[List[Dict]]:
    """
    Try to extract productListMain array directly from a script/text block.
    """
    # Method 1: Regex capture with DOTALL and whitespace-insensitive tokens
    regex_patterns = [
        r"BEYMEN\s*\.\s*productListMain\s*=\s*(\[[\s\S]*?\])\s*;",
        r"window\s*\.\s*BEYMEN\s*\.\s*productListMain\s*=\s*(\[[\s\S]*?\])\s*;",
        r"productListMain\s*[:=]\s*(\[[\s\S]*?\])",
    ]
    for pattern in regex_patterns:
        match = re.search(pattern, text, flags=re.DOTALL)
        if not match:
            continue
        items = _safe_json_loads(match.group(1))
        if _looks_like_product_list(items):
            return items

    # Fallback: balanced bracket extraction (more robust for nested data)
    start_patterns = [
        r"BEYMEN\s*\.\s*productListMain\s*=\s*\[",
        r"window\s*\.\s*BEYMEN\s*\.\s*productListMain\s*=\s*\[",
        r"productListMain\s*[:=]\s*\[",
    ]
    for pattern in start_patterns:
        for match in re.finditer(pattern, text, flags=re.DOTALL):
            array_start = match.end() - 1
            array_str = _extract_balanced(text, array_start, "[", "]")
            items = _safe_json_loads(array_str)
            if _looks_like_product_list(items):
                return items
    return None


def _extract_object_assignment(text: str, var_name: str) -> Optional[object]:
    """
    Extract JSON object assigned to a variable (e.g., window.BEYMEN = {...};).
    """
    patterns = [
        rf"{re.escape(var_name)}\s*=\s*\{{",
        rf"window\.{re.escape(var_name)}\s*=\s*\{{",
        rf"var\s+{re.escape(var_name)}\s*=\s*\{{",
        rf"let\s+{re.escape(var_name)}\s*=\s*\{{",
        rf"const\s+{re.escape(var_name)}\s*=\s*\{{",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if not match:
            continue
        obj_start = text.find("{", match.end() - 1)
        obj_str = _extract_balanced(text, obj_start, "{", "}")
        obj = _safe_json_loads(obj_str)
        if obj is not None:
            return obj
    return None


def _find_item_lists(obj: object, results: List[Dict]) -> None:
    if isinstance(obj, dict):
        obj_type = str(obj.get("@type", "")).lower()
        if obj_type == "itemlist":
            results.append(obj)
        for value in obj.values():
            _find_item_lists(value, results)
    elif isinstance(obj, list):
        for item in obj:
            _find_item_lists(item, results)


def _extract_ld_json_products(soup: BeautifulSoup) -> List[Dict]:
    products: List[Dict] = []
    scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
    for script in scripts:
        payload = script.get_text()
        data = _safe_json_loads(payload)
        if data is None:
            continue
        itemlists: List[Dict] = []
        _find_item_lists(data, itemlists)
        for itemlist in itemlists:
            elements = itemlist.get("itemListElement") or []
            if isinstance(elements, (dict, str)):
                elements = [elements]
            if not isinstance(elements, list):
                continue
            for el in elements:
                item = None
                if isinstance(el, dict):
                    item = el.get("item") or el
                elif isinstance(el, str):
                    item = {"url": el}
                if not isinstance(item, dict):
                    continue
                product = _normalize_ld_json_item(item)
                if product:
                    products.append(product)
    return products


def _normalize_ld_json_item(item: Dict) -> Optional[Dict]:
    name = item.get("name") or item.get("title")
    url = item.get("url") or item.get("@id")
    image = item.get("image")
    if isinstance(image, dict):
        image = image.get("url")
    elif isinstance(image, list) and image:
        image = image[0].get("url") if isinstance(image[0], dict) else image[0]

    brand = item.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")

    offers = item.get("offers") or {}
    if isinstance(offers, list) and offers:
        offers = offers[0]
    if isinstance(offers, str):
        offers = {}

    price = offers.get("price") or offers.get("lowPrice") or offers.get("highPrice")
    currency = offers.get("priceCurrency") or "TRY"

    sku = item.get("sku") or item.get("mpn") or item.get("productId")
    sku = sku or _derive_sku(url, name)

    if not sku or not (name or url):
        return None

    return {
        "sku": sku,
        "name": name,
        "brand": brand,
        "price": _parse_price(price),
        "original_price": None,
        "url": _ensure_abs_url(url),
        "image_url": _ensure_abs_url(image),
        "sizes": [],
        "category": None,
        "gender": None,
        "currency": currency or "TRY",
    }


def _text_content(el) -> Optional[str]:
    if not el:
        return None
    text = " ".join(el.stripped_strings)
    return text or None


def _extract_text_from_selectors(root, selectors: List[str]) -> Optional[str]:
    for sel in selectors:
        el = root.select_one(sel)
        text = _text_content(el)
        if text:
            return text
    return None


def _extract_attr_from_selectors(root, selectors: List[str], attr: str) -> Optional[str]:
    for sel in selectors:
        el = root.select_one(sel)
        if el and el.get(attr):
            return el.get(attr)
    return None


def _normalize_srcset(srcset: Optional[str]) -> Optional[str]:
    if not srcset:
        return None
    # Take the first URL in srcset
    first = srcset.split(",")[0].strip()
    return first.split(" ")[0].strip() if first else None


def _extract_html_products(soup: BeautifulSoup) -> List[Dict]:
    products: List[Dict] = []
    selectors = [
        ".m-productCard",
        ".o-productList__item",
        ".o-productList__itemWrapper",
    ]
    cards = []
    for sel in selectors:
        cards.extend(soup.select(sel))

    seen_keys = set()
    name_selectors = [
        ".m-productCard__name",
        ".m-productCard__title",
        ".m-productCard__productName",
        ".o-productList__itemName",
        ".product-card-title",
        ".product-name",
    ]
    brand_selectors = [
        ".m-productCard__brand",
        ".o-productList__itemBrand",
        ".product-card-brand",
    ]
    price_selectors = [
        ".m-price__new",
        ".m-price__current",
        ".m-productCard__price",
        ".o-productList__itemPrice",
        ".m-productCard__price--sale",
    ]
    old_price_selectors = [
        ".m-price__old",
        ".m-price__original",
        ".m-productCard__price--old",
        ".o-productList__itemPrice--old",
    ]
    for card in cards:
        link_el = card.select_one("a[href]")
        url = link_el.get("href") if link_el else None
        url = _ensure_abs_url(url)

        name = card.get("data-product-name") or _extract_text_from_selectors(card, name_selectors)
        if not name and link_el:
            name = link_el.get("title")

        brand = card.get("data-brand") or _extract_text_from_selectors(card, brand_selectors)

        price_text = (
            card.get("data-price")
            or card.get("data-product-price")
            or _extract_text_from_selectors(card, price_selectors)
        )
        old_price_text = (
            card.get("data-old-price")
            or card.get("data-product-old-price")
            or _extract_text_from_selectors(card, old_price_selectors)
        )

        price = _parse_price(price_text)
        original_price = _parse_price(old_price_text)

        image_url = None
        img = card.select_one("img")
        if img:
            image_url = (
                img.get("data-src")
                or img.get("data-original")
                or img.get("data-lazy")
                or img.get("src")
            )
            if not image_url and img.get("srcset"):
                image_url = _normalize_srcset(img.get("srcset"))
        if not image_url:
            source = card.select_one("source")
            if source:
                image_url = (
                    source.get("data-srcset")
                    or source.get("srcset")
                    or source.get("data-src")
                )
                image_url = _normalize_srcset(image_url)

        image_url = _ensure_abs_url(image_url)
        sku = _derive_sku(url, name)

        if not sku or not (name or url):
            continue
        key = sku or url
        if key in seen_keys:
            continue
        seen_keys.add(key)

        products.append(
            {
                "sku": sku,
                "name": name,
                "brand": brand,
                "price": price,
                "original_price": original_price,
                "url": url,
                "image_url": image_url,
                "sizes": [],
                "category": None,
                "gender": None,
                "currency": "TRY",
            }
        )
    return products


def extract_json_data(html: str) -> List[Dict]:
    """
    Extract products using multiple strategies (productListMain, LD-JSON, HTML fallback).
    """
    # Strategy 1: Direct extraction from raw HTML
    direct_items = _extract_array_from_text(html)
    if direct_items:
        logger.info("Found product list via direct BEYMEN/productListMain assignment.")
        return direct_items

    logger.warning("Regex match failed for BEYMEN.productListMain. Trying alternative extraction...")

    # Strategy 2: Parse script tags with BeautifulSoup
    soup = BeautifulSoup(html, "lxml")

    # Next.js style data
    next_data = soup.find("script", id="__NEXT_DATA__")
    if next_data:
        payload = next_data.get_text()
        data = _safe_json_loads(payload)
        found = _find_key_recursive(data, "productListMain")
        if _looks_like_product_list(found):
            logger.info("Found product list via __NEXT_DATA__.")
            return found

    # Any application/json script tags
    for script in soup.find_all("script", attrs={"type": "application/json"}):
        payload = script.get_text()
        data = _safe_json_loads(payload)
        found = _find_key_recursive(data, "productListMain")
        if _looks_like_product_list(found):
            logger.info("Found product list via application/json script.")
            return found

    # Scan inline scripts for productListMain
    for script in soup.find_all("script"):
        payload = script.get_text()
        if not payload or "productListMain" not in payload:
            continue
        items = _extract_array_from_text(payload)
        if items:
            logger.info("Found product list via inline script scan.")
            return items
        # Try common state containers
        for var_name in ("__INITIAL_STATE__", "__PRELOADED_STATE__", "BEYMEN"):
            state = _extract_object_assignment(payload, var_name)
            found = _find_key_recursive(state, "productListMain")
            if _looks_like_product_list(found):
                logger.info(f"Found product list via {var_name} state.")
                return found

    # Method 2: LD-JSON ItemList extraction
    ld_products = _extract_ld_json_products(soup)
    if ld_products:
        logger.info("Found product list via LD-JSON ItemList.")
        return ld_products

    # Method 3: HTML parsing fallback
    html_products = _extract_html_products(soup)
    if html_products:
        logger.info("Found product list via HTML product cards.")
        return html_products

    if "productListMain" not in html:
        logger.warning("productListMain not found in HTML. Site structure may have changed.")
    return []


def process_product(item: Dict) -> Optional[Dict]:
    """
    Map raw JSON item to database schema dict.
    """
    try:
        if not isinstance(item, dict):
            return None

        # Branch 1: Beymen productListMain schema
        if "productId" in item or "displayName" in item:
            url_suffix = item.get("url", "")
            full_url = _ensure_abs_url(url_suffix)

            images = item.get("images", [])
            image_url = None
            if images and isinstance(images, list):
                first = images[0] if images else None
                if isinstance(first, dict):
                    image_url = first.get("url") or first.get("imageUrl")
                elif isinstance(first, str):
                    image_url = first
            image_url = _ensure_abs_url(image_url)

            # Sizes
            size_list = []
            raw_sizes = item.get("sizes", [])
            if isinstance(raw_sizes, list):
                for s in raw_sizes:
                    if isinstance(s, dict) and s.get("inStock"):
                        size_list.append(s.get("sizeName"))

            price = _parse_price(item.get("actualPrice"))
            original_price = _parse_price(item.get("originalPrice"))

            sku = item.get("productId") or _derive_sku(full_url, item.get("displayName"))

            product_data = {
                "sku": sku,
                "name": item.get("displayName"),
                "brand": item.get("brandName"),
                "price": price,
                "original_price": original_price,
                "url": full_url,
                "image_url": image_url,
                "sizes": size_list,
                "category": item.get("categoryName") or item.get("category"),
                "gender": item.get("gender"),
                "currency": "TRY",
                "stock_code": item.get("productId"),
            }
            return product_data

        # Branch 2: Normalized fallback schema (LD-JSON / HTML)
        name = item.get("name") or item.get("displayName")
        url = _ensure_abs_url(item.get("url"))
        image_url = _ensure_abs_url(item.get("image_url") or item.get("image"))
        brand = item.get("brand") or item.get("brandName")
        price = _parse_price(item.get("price") or item.get("actualPrice"))
        original_price = _parse_price(item.get("original_price") or item.get("originalPrice"))
        sku = item.get("sku") or item.get("productId") or _derive_sku(url, name)
        sizes = item.get("sizes") if isinstance(item.get("sizes"), list) else []
        category = item.get("category") or item.get("categoryName")
        gender = item.get("gender")
        currency = item.get("currency") or "TRY"

        if not sku or not name:
            return None

        return {
            "sku": sku,
            "name": name,
            "brand": brand,
            "price": price,
            "original_price": original_price,
            "url": url,
            "image_url": image_url,
            "sizes": sizes,
            "category": category,
            "gender": gender,
            "currency": currency,
            "stock_code": item.get("productId") or sku,
        }
    except Exception as e:
        fallback_id = item.get("productId") if isinstance(item, dict) else None
        logger.error(f"Error processing item {fallback_id}: {e}")
        return None


async def save_product(session, data: Dict) -> bool:
    """
    Upsert product into database.
    """
    sku = data.get("sku")
    if not sku:
        return False

    # Check if exists
    stmt = select(Product).where(Product.sku == sku)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        # Update
        existing.name = data["name"]
        existing.brand = data["brand"]
        existing.price = data["price"]
        existing.original_price = data["original_price"]
        existing.url = data["url"]
        existing.image_url = data["image_url"]
        existing.sizes = data["sizes"]
        existing.category = data["category"]
        existing.gender = data["gender"]
        existing.currency = data["currency"]
        logger.info(f"Updated product: {sku}")
    else:
        # Insert
        new_product = Product(
            sku=sku,
            name=data["name"],
            brand=data["brand"],
            price=data["price"],
            original_price=data["original_price"],
            url=data["url"],
            image_url=data["image_url"],
            sizes=data["sizes"],
            category=data["category"],
            gender=data["gender"],
            currency=data["currency"],
            # Nullable fields
            fit_type=None,
            fabric_composition=None,
            measurements=None,
            tenant_id=None
        )
        session.add(new_product)
        logger.info(f"Created product: {sku}")

    return True


async def run_pipeline():
    """
    Main entry point.
    """
    logger.info("Starting Beymen Scraper Pipeline...")
    
    html = fetch_html(TARGET_URL, render_js=False)
    if not html:
        logger.error("Failed to retrieve HTML.")
        return

    try:
        products_data = extract_json_data(html)
    except Exception as e:
        logger.error(f"Extraction error (SSR): {e}")
        save_debug_html(html, "ssr_parse_error")
        products_data = []
    logger.info(f"Extracted {len(products_data)} products from extraction.")

    if not products_data:
        save_debug_html(html, "ssr_no_products")
        logger.warning("No products found in SSR HTML. Retrying with JS rendering...")
        html = fetch_html(TARGET_URL, render_js=True)
        if html:
            try:
                products_data = extract_json_data(html)
            except Exception as e:
                logger.error(f"Extraction error (JS): {e}")
                save_debug_html(html, "js_parse_error")
                products_data = []
            logger.info(f"Extracted {len(products_data)} products from JS-rendered HTML.")

    if not products_data:
        if html:
            save_debug_html(html, "js_no_products")
        return

    # Database Session — use a fresh session per product to avoid
    # asyncpg prepared-statement pollution after rollback.
    session_factory = get_session_factory()
    success_count = 0
    failed_count = 0
    skipped_count = 0
    first_db_error_logged = False
    for item in products_data:
        clean_data = process_product(item)
        if not clean_data:
            skipped_count += 1
            continue

        sku = clean_data.get("sku")
        try:
            async with session_factory() as session:
                async with session.begin():
                    saved = await save_product(session, clean_data)
                if saved:
                    success_count += 1
                else:
                    skipped_count += 1
        except Exception as e:
            failed_count += 1
            if not first_db_error_logged:
                first_db_error_logged = True
                logger.exception(f"First DB error on SKU {sku}: {e}")
            else:
                logger.error(f"Database error for {sku}: {e}")

    logger.info(
        f"DB summary: success={success_count}, failed={failed_count}, skipped={skipped_count}"
    )

if __name__ == "__main__":
    asyncio.run(run_pipeline())
