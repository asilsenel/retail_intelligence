"""
FitEngine API - Main Application Entry Point

A B2B SaaS API for size recommendations, designed to help
e-commerce clothing brands reduce return rates.
"""
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from contextlib import asynccontextmanager
import time
import os
import json
import re
import base64
import httpx
from sqlalchemy import select, or_, func

from app.config import settings
from app.routers import products, recommendations
from app.models.database import get_session_factory, Product


# =============================================================================
# DATABASE HELPERS
# =============================================================================

def _extract_brand_from_url(url: str) -> Optional[str]:
    """Extract brand name from Beymen product URL slug."""
    if not url:
        return None
    # URL pattern: /tr/p_brand-name-product-desc_12345
    match = re.search(r"/p_([a-z0-9-]+)_\d+", url)
    if not match:
        return None
    slug = match.group(1)
    # First segment(s) before the product description is typically the brand
    # Heuristic: known multi-word brands
    known = [
        "beymen-club", "beymen-collection", "pal-zileri", "paul-smith",
        "corneliani", "canali", "boss", "tommy-hilfiger",
    ]
    for k in known:
        if slug.startswith(k):
            return k.replace("-", " ").title()
    # Fallback: first word
    first = slug.split("-")[0]
    return first.title() if first else None


def _product_to_dict(p: Product) -> dict:
    """Convert a Product ORM row to a serialisable dict for the widget."""
    brand = p.brand or _extract_brand_from_url(p.url)
    price_str = f"{p.price:,.0f} TL".replace(",", ".") if p.price else None
    category = p.category or _guess_category(p.name)
    measurements = p.measurements or _get_default_measurements(category)
    # Outerwear defaults to loose_fit (worn over other layers)
    cat_lower = category.lower() if category else ""
    if p.fit_type:
        fit_type = p.fit_type
    elif cat_lower in ("palto", "mont", "kaban", "parka", "pardösü"):
        fit_type = "loose_fit"
    else:
        fit_type = "regular_fit"
    fabric = p.fabric_composition or {"cotton": 100}

    # Sizes: DB may contain old format (list of strings) or new format (list of dicts)
    raw_sizes = p.sizes if p.sizes else []
    if raw_sizes and isinstance(raw_sizes[0], dict):
        # New format: [{"size": "50", "inStock": true}, ...]
        sizes_with_stock = raw_sizes
        available_sizes = [s["size"] for s in raw_sizes if s.get("inStock", True)]
    elif raw_sizes and isinstance(raw_sizes[0], str):
        # Old format: ["S", "M", "L"] — assume all in stock
        sizes_with_stock = [{"size": s, "inStock": True} for s in raw_sizes]
        available_sizes = raw_sizes
    else:
        # Fallback to measurement keys
        fallback = list(measurements.keys()) if measurements else []
        sizes_with_stock = [{"size": s, "inStock": True} for s in fallback]
        available_sizes = fallback

    # Fix CDN placeholder URLs: {width}/{height} → 500/500
    image_url = p.image_url
    if image_url and "{width}" in image_url:
        image_url = image_url.replace("{width}", "500").replace("{height}", "500")

    return {
        "id": str(p.id),
        "sku": p.sku,
        "name": p.name,
        "brand": brand or "Beymen",
        "price": price_str,
        "price_raw": p.price,
        "url": p.url,
        "image_url": image_url,
        "category": category,
        "sizes": sizes_with_stock,
        "available_sizes": available_sizes,
        "measurements": measurements,
        "fit_type": fit_type,
        "fabric_composition": fabric,
    }


# Category keywords found in DB product names
_CATEGORY_KEYWORDS = {
    "palto": "palto",
    "mont": "mont",
    "kaban": "kaban",
    "ceket": "ceket",
    "blazer": "ceket",
    "yelek": "yelek",
    "parka": "parka",
    "pardösü": "pardösü",
    "pantolon": "pantolon",
    "chino": "pantolon",
    "jean": "pantolon",
    "gömlek": "gömlek",
    "tişört": "tişört",
    "kazak": "kazak",
    "triko": "kazak",
    "ayakkabı": "ayakkabı",
    "oxford": "ayakkabı",
    "loafer": "ayakkabı",
    "derby": "ayakkabı",
    "brogue": "ayakkabı",
    "monk": "ayakkabı",
    "takım elbise": "takım elbise",
    "takım": "takım elbise",
    "suit": "takım elbise",
    "smokin": "takım elbise",
}


def _guess_category(name: str) -> Optional[str]:
    """Guess product category from its Turkish name."""
    if not name:
        return None
    lower = name.lower()
    for kw, cat in _CATEGORY_KEYWORDS.items():
        if kw in lower:
            return cat
    return None


# =============================================================================
# DEFAULT MEASUREMENTS — fallback when DB has no measurements for a product
# =============================================================================
# Standard Turkish men's garment measurements (chest_width, length, waist, shoulder_width) in cm

_DEFAULT_MEASUREMENTS = {
    # Dış giyim has ~8-12cm ease over body (worn over other layers)
    "dış_giyim": {  # palto, mont, kaban, parka, pardösü
        "S":   {"chest_width": 100, "length": 78, "shoulder_width": 43, "waist": 94},
        "M":   {"chest_width": 106, "length": 80, "shoulder_width": 45, "waist": 100},
        "L":   {"chest_width": 112, "length": 82, "shoulder_width": 47, "waist": 106},
        "XL":  {"chest_width": 118, "length": 84, "shoulder_width": 49, "waist": 112},
        "XXL": {"chest_width": 124, "length": 86, "shoulder_width": 51, "waist": 118},
        # Numeric EU sizes (same body measurements)
        "46": {"chest_width": 100, "length": 78, "shoulder_width": 43, "waist": 94},
        "48": {"chest_width": 104, "length": 79, "shoulder_width": 44, "waist": 98},
        "50": {"chest_width": 108, "length": 80, "shoulder_width": 45, "waist": 102},
        "52": {"chest_width": 112, "length": 82, "shoulder_width": 47, "waist": 106},
        "54": {"chest_width": 116, "length": 83, "shoulder_width": 48, "waist": 110},
        "56": {"chest_width": 120, "length": 84, "shoulder_width": 49, "waist": 114},
        "58": {"chest_width": 124, "length": 86, "shoulder_width": 51, "waist": 118},
        "60": {"chest_width": 128, "length": 88, "shoulder_width": 52, "waist": 122},
    },
    # Üst giyim has ~5-8cm ease (structured, single layer)
    "üst_giyim": {  # ceket, blazer, yelek
        "S":   {"chest_width": 96, "length": 70, "shoulder_width": 42, "waist": 90},
        "M":   {"chest_width": 102, "length": 72, "shoulder_width": 44, "waist": 96},
        "L":   {"chest_width": 108, "length": 74, "shoulder_width": 46, "waist": 102},
        "XL":  {"chest_width": 114, "length": 76, "shoulder_width": 48, "waist": 108},
        "XXL": {"chest_width": 120, "length": 78, "shoulder_width": 50, "waist": 114},
        # Numeric EU sizes
        "46": {"chest_width": 96, "length": 70, "shoulder_width": 42, "waist": 90},
        "48": {"chest_width": 100, "length": 72, "shoulder_width": 43, "waist": 94},
        "50": {"chest_width": 104, "length": 73, "shoulder_width": 44, "waist": 98},
        "52": {"chest_width": 108, "length": 74, "shoulder_width": 46, "waist": 102},
        "54": {"chest_width": 112, "length": 76, "shoulder_width": 47, "waist": 106},
        "56": {"chest_width": 116, "length": 77, "shoulder_width": 48, "waist": 110},
        "58": {"chest_width": 120, "length": 78, "shoulder_width": 50, "waist": 114},
        "60": {"chest_width": 124, "length": 80, "shoulder_width": 51, "waist": 118},
    },
    # Alt giyim: waist + hip are key measurements (no chest)
    "alt_giyim": {  # pantolon, chino, jean
        "S":   {"waist": 76, "hip": 94, "length": 102},
        "M":   {"waist": 82, "hip": 100, "length": 104},
        "L":   {"waist": 88, "hip": 106, "length": 106},
        "XL":  {"waist": 94, "hip": 112, "length": 108},
        "XXL": {"waist": 100, "hip": 118, "length": 110},
        # Numeric EU sizes
        "44": {"waist": 74, "hip": 92, "length": 101},
        "46": {"waist": 78, "hip": 96, "length": 102},
        "48": {"waist": 82, "hip": 100, "length": 103},
        "50": {"waist": 86, "hip": 104, "length": 104},
        "52": {"waist": 90, "hip": 108, "length": 106},
        "54": {"waist": 94, "hip": 112, "length": 107},
        "56": {"waist": 98, "hip": 116, "length": 108},
    },
    # Üst iç giyim: ~3-5cm ease (body-hugging)
    "üst_iç_giyim": {  # gömlek, tişört, kazak, triko
        "S":   {"chest_width": 94, "length": 72, "shoulder_width": 42, "waist": 88},
        "M":   {"chest_width": 100, "length": 74, "shoulder_width": 44, "waist": 94},
        "L":   {"chest_width": 106, "length": 76, "shoulder_width": 46, "waist": 100},
        "XL":  {"chest_width": 112, "length": 78, "shoulder_width": 48, "waist": 106},
        "XXL": {"chest_width": 118, "length": 80, "shoulder_width": 50, "waist": 112},
    },
    # Takım elbise (suit): ~4-6cm ease, similar to üst_giyim but slightly more fitted
    "takım_elbise": {
        "46": {"chest_width": 96, "length": 70, "shoulder_width": 42, "waist": 84},
        "48": {"chest_width": 100, "length": 72, "shoulder_width": 43, "waist": 88},
        "50": {"chest_width": 104, "length": 74, "shoulder_width": 45, "waist": 92},
        "52": {"chest_width": 108, "length": 75, "shoulder_width": 46, "waist": 96},
        "54": {"chest_width": 112, "length": 76, "shoulder_width": 48, "waist": 100},
        "56": {"chest_width": 116, "length": 78, "shoulder_width": 50, "waist": 104},
    },
    # Ayakkabı: foot length based sizing
    "ayakkabı": {
        "39": {"foot_length": 25.0},
        "40": {"foot_length": 25.7},
        "41": {"foot_length": 26.3},
        "42": {"foot_length": 27.0},
        "43": {"foot_length": 27.7},
        "44": {"foot_length": 28.3},
        "45": {"foot_length": 29.0},
    },
}

_CATEGORY_TO_MEASUREMENT_GROUP = {
    "palto": "dış_giyim", "mont": "dış_giyim", "kaban": "dış_giyim",
    "parka": "dış_giyim", "pardösü": "dış_giyim",
    "ceket": "üst_giyim", "yelek": "üst_giyim", "blazer": "üst_giyim",
    "pantolon": "alt_giyim", "spor pantolon": "alt_giyim",
    "gömlek": "üst_iç_giyim", "tişört": "üst_iç_giyim",
    "kazak": "üst_iç_giyim",
    "takım elbise": "takım_elbise", "takım": "takım_elbise", "takim": "takım_elbise",
    "ayakkabı": "ayakkabı", "ayakkabi": "ayakkabı", "loafer": "ayakkabı",
}


def _get_default_measurements(category: Optional[str]) -> Optional[dict]:
    """Return default measurements for a category, or None."""
    if not category:
        return None
    cat_lower = category.lower()
    group = _CATEGORY_TO_MEASUREMENT_GROUP.get(cat_lower)
    if not group:
        return None
    return _DEFAULT_MEASUREMENTS.get(group)


# Combo mapping: category -> list of complementary categories
_COMBO_MAP = {
    "palto": ["pantolon", "gömlek", "kazak", "ayakkabı"],
    "mont": ["pantolon", "gömlek", "kazak"],
    "kaban": ["pantolon", "gömlek", "kazak"],
    "ceket": ["pantolon", "gömlek", "ayakkabı"],
    "blazer": ["pantolon", "gömlek", "ayakkabı"],
    "yelek": ["pantolon", "gömlek"],
    "parka": ["pantolon", "kazak"],
    "pardösü": ["pantolon", "gömlek"],
    "pantolon": ["ceket", "blazer", "palto", "mont", "gömlek", "ayakkabı"],
    "spor pantolon": ["ceket", "mont", "ayakkabı"],
    "gömlek": ["ceket", "blazer", "pantolon", "palto"],
    "kazak": ["pantolon", "palto", "mont"],
    "tişört": ["pantolon", "ceket"],
    "ayakkabı": ["pantolon", "ceket", "blazer", "takım"],
    "ayakkabi": ["pantolon", "ceket", "blazer", "takım"],
    "loafer": ["pantolon", "blazer", "takım"],
    "takım elbise": ["gömlek", "ayakkabı", "palto"],
    "takım": ["gömlek", "ayakkabı", "palto"],
    "takim": ["gömlek", "ayakkabı", "palto"],
}


async def search_products(keywords: List[str], limit: int = 3) -> List[dict]:
    """Search products table. Keywords match against name OR category column."""
    if not keywords:
        return []
    from sqlalchemy import and_
    session_factory = get_session_factory()
    async with session_factory() as session:
        # Each keyword can match in name OR category
        conditions = [
            or_(
                func.lower(Product.name).contains(kw.lower()),
                func.lower(Product.category).contains(kw.lower()),
            )
            for kw in keywords
        ]

        # AND: every keyword must appear in name or category
        stmt = (
            select(Product)
            .where(Product.is_active == True)
            .where(and_(*conditions))
            .order_by(Product.created_at.desc())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        # If AND is too strict (0 results), fall back to OR
        if not rows and len(keywords) > 1:
            stmt_or = (
                select(Product)
                .where(Product.is_active == True)
                .where(or_(*conditions))
                .order_by(Product.created_at.desc())
                .limit(limit)
            )
            result = await session.execute(stmt_or)
            rows = result.scalars().all()

        return [_product_to_dict(r) for r in rows]


async def get_combo_products(
    main_category: str,
    exclude_id: str,
    limit: int = 2,
    exclude_ids: set = None,
    target_category: str = None,
) -> List[dict]:
    """Find complementary products for outfit combo.

    Args:
        main_category: Category of the main product (e.g. "palto").
        exclude_id: Single product ID to exclude (backward compat).
        limit: Max combo products to return.
        exclude_ids: Set of product IDs to exclude (e.g. all main search results).
        target_category: If provided, only search for this specific category
                         (e.g. "pantolon") instead of all complementary categories.
    """
    cat_lower = main_category.lower() if main_category else ""

    if target_category:
        # Filter to just one specific complementary category
        target_cats = [target_category.lower()]
    else:
        target_cats = _COMBO_MAP.get(cat_lower, [])
    if not target_cats:
        return []

    ids_to_exclude = list(exclude_ids) if exclude_ids else [exclude_id]

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Build category filter — match by name OR by category column
        cat_conditions = []
        for cat in target_cats:
            cat_conditions.append(func.lower(Product.name).contains(cat))
            cat_conditions.append(func.lower(Product.category).contains(cat))

        stmt = (
            select(Product)
            .where(Product.is_active == True)
            .where(or_(*cat_conditions))
            .where(Product.id.notin_(ids_to_exclude))
            .order_by(func.random())
            .limit(limit)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()
        return [_product_to_dict(r) for r in rows]


async def get_product_count() -> int:
    """Get total active product count."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(func.count(Product.id)).where(Product.is_active == True)
        result = await session.execute(stmt)
        return result.scalar_one()


# =============================================================================
# CHAT ENDPOINT MODELS
# =============================================================================

class ChatRequest(BaseModel):
    """Request body for chat endpoint."""
    message: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response from chat endpoint."""
    message: str
    products: List[Dict[str, Any]] = []
    combos: List[Dict[str, Any]] = []
    # Backward compat
    main_product: Optional[Dict[str, Any]] = None
    combo_product: Optional[Dict[str, Any]] = None
    conversation_id: Optional[str] = None


# =============================================================================
# OPENAI INTEGRATION — 2-STAGE: INTENT PARSE → DB SEARCH → STYLED REPLY
# =============================================================================

INTENT_PROMPT = """Sen bir intent-parse botusun. Kullanıcının mesajından arama anahtar kelimelerini çıkar.

Cevabını SADECE JSON olarak ver:
{
    "intent": "product_search" | "outfit_combo" | "size_help" | "greeting" | "other",
    "keywords": ["anahtar", "kelimeler"],
    "category": "palto|mont|ceket|pantolon|gömlek|yelek|kaban|parka|kazak|null",
    "color": "renk veya null"
}

Örnekler:
- "siyah palto öner" → {"intent":"product_search","keywords":["siyah","palto"],"category":"palto","color":"siyah"}
- "bana bir kombin yap" → {"intent":"outfit_combo","keywords":[],"category":null,"color":null}
- "boyum 180 kilom 80" → {"intent":"size_help","keywords":[],"category":null,"color":null}
- "merhaba" → {"intent":"greeting","keywords":[],"category":null,"color":null}

Sadece JSON döndür."""

STYLIST_PROMPT = """Sen Beymen'in Elit AI Stilistisin. Lüks, kibar ve profesyonel bir Türkçe ile konuş.
"Efendim", "Memnuniyetle" gibi ifadeler kullan. Kısa ve öz yanıt ver (3-4 cümle).

Müşteriye aşağıdaki ürünleri öneriyorsun:

**ANA ÜRÜNLER:**
{main_products}

**KOMBİN ÖNERİLERİ:**
{combo_products}

Müşterinin orijinal mesajı: "{user_message}"

Yanıtında:
1. Ana ürünleri kısaca tanıt (birden fazlaysa her birini bir cümleyle belirt).
2. Kombin önerilerini sun ("Yanına ... harika olur" gibi).
3. Beden yardımı teklif et ("Bedeninizi bulmam için boy ve kilonuzu yazabilirsiniz").

Düz metin olarak yanıtla, JSON değil. Lüks, elit ve samimi bir ton kullan."""

GREETING_RESPONSES = [
    "Beymen'e hoş geldiniz efendim! Size nasıl yardımcı olabilirim? Palto, mont, ceket, pantolon gibi pek çok seçeneğimiz mevcut. Aradığınız ürünü veya tarzı söylemeniz yeterli.",
]


async def parse_intent(user_message: str) -> dict:
    """Use OpenAI to parse user intent, or fall back to keyword matching."""
    api_key = os.getenv("OPENAI_API_KEY")

    if api_key:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": INTENT_PROMPT},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.0,
                        "max_tokens": 200,
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    raw = resp.json()["choices"][0]["message"]["content"]
                    if "```json" in raw:
                        raw = raw.split("```json")[1].split("```")[0]
                    elif "```" in raw:
                        raw = raw.split("```")[1].split("```")[0]
                    return json.loads(raw.strip())
        except Exception as e:
            print(f"Intent parse error: {e}")

    # Fallback: simple keyword extraction
    return _fallback_intent(user_message)


def _fallback_intent(text: str) -> dict:
    """Simple rule-based intent extraction."""
    lower = text.lower()

    # Check for greetings
    greetings = ["merhaba", "selam", "hey", "naber", "hoş geldin"]
    if any(g in lower for g in greetings):
        return {"intent": "greeting", "keywords": [], "category": None, "color": None}

    # Size help
    if re.search(r"\d{2,3}\s*(cm|kg|boy|kilo)", lower):
        return {"intent": "size_help", "keywords": [], "category": None, "color": None}
    if any(w in lower for w in ["beden", "ölçü", "size"]):
        return {"intent": "size_help", "keywords": [], "category": None, "color": None}

    # Combo
    if any(w in lower for w in ["kombin", "outfit", "set"]):
        return {"intent": "outfit_combo", "keywords": [], "category": None, "color": None}

    # Product search — extract keywords
    keywords = []
    category = None
    color = None

    colors = ["siyah", "beyaz", "lacivert", "mavi", "gri", "kahverengi", "bej",
              "haki", "bordo", "kırmızı", "yeşil", "mor", "turuncu", "krem", "antrasit"]
    for c in colors:
        if c in lower:
            color = c
            keywords.append(c)
            break

    for kw, cat in _CATEGORY_KEYWORDS.items():
        if kw in lower:
            category = cat
            keywords.append(kw)
            break

    if not keywords:
        # Just send all meaningful words
        stopwords = {"bir", "bana", "benim", "için", "var", "mı", "mi", "mu", "öner",
                     "önerir", "misin", "musun", "istiyorum", "arıyorum", "lazım",
                     "lütfen", "bakar", "bakabilir"}
        keywords = [w for w in lower.split() if w not in stopwords and len(w) > 2]

    return {
        "intent": "product_search",
        "keywords": keywords,
        "category": category,
        "color": color,
    }


async def generate_styled_response(user_message: str, products: List[dict], combos: List[dict]) -> str:
    """Ask OpenAI to write a luxurious Turkish response about these products."""
    api_key = os.getenv("OPENAI_API_KEY")

    def _desc(p: dict) -> str:
        s = f"{p['brand']} - {p['name']}"
        if p.get("price"):
            s += f" ({p['price']})"
        return s

    main_desc = "\n".join(f"- {_desc(p)}" for p in products) if products else "Yok"
    combo_desc = "\n".join(f"- {_desc(c)}" for c in combos) if combos else "Yok"

    if api_key:
        try:
            prompt = STYLIST_PROMPT.format(
                main_products=main_desc,
                combo_products=combo_desc,
                user_message=user_message,
            )
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": user_message},
                        ],
                        "temperature": 0.7,
                        "max_tokens": 400,
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Stylist response error: {e}")

    # Fallback
    main = products[0] if products else None
    if not main:
        return "Maalesef uygun ürün bulamadım efendim."
    msg = f"Memnuniyetle efendim! Size {main['brand']} {main['name']} önerebilirim."
    if main.get("price"):
        msg += f" Fiyatı {main['price']}."
    if len(products) > 1:
        msg += f" Ayrıca {products[1]['brand']} {products[1]['name']} da ilginizi çekebilir."
    if combos:
        msg += f" Yanına {combos[0]['brand']} {combos[0]['name']} ile harika bir kombin oluşturabilirsiniz."
    msg += " Bedeninizi bulmam için boy ve kilonuzu yazabilirsiniz."
    return msg


# =============================================================================
# APPLICATION SETUP
# =============================================================================

APP_METADATA = {
    "title": "FitEngine API",
    "description": "AI-Powered Size Recommendations & Personal Styling",
    "version": "3.0.0",
    "contact": {"name": "FitEngine Support", "email": "support@fitengine.io"},
    "license_info": {"name": "Proprietary"},
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    count = await get_product_count()
    print(f"FitEngine API starting... {count} products in DB")
    yield
    print("FitEngine API shutting down...")


app = FastAPI(
    **APP_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list if settings.is_production else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    response.headers["X-Process-Time"] = f"{time.time() - start_time:.4f}"
    # Prevent caching for widget files during development
    if request.url.path.startswith("/widget/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


app.include_router(products.router)
app.include_router(recommendations.router)

# Serve widget files at /widget/ so test.html works via http://localhost:8000/widget/test.html
import pathlib
_widget_dir = pathlib.Path(__file__).resolve().parent.parent / "widget"
if _widget_dir.is_dir():
    app.mount("/widget", StaticFiles(directory=str(_widget_dir), html=True), name="widget")


# =============================================================================
# CHAT ENDPOINT
# =============================================================================

@app.post("/api/v1/chat", response_model=ChatResponse, tags=["AI Chat"])
async def chat_with_ai(request: ChatRequest):
    """
    Chat with the Beymen AI Stylist.

    2-stage pipeline:
    1. Parse intent (category, color, keywords) via OpenAI or fallback.
    2. Search real DB, find combo, generate styled response.
    """
    intent = await parse_intent(request.message)
    intent_type = intent.get("intent", "other")

    # --- Greeting ---
    if intent_type == "greeting":
        return ChatResponse(
            message=GREETING_RESPONSES[0],
            conversation_id=request.conversation_id,
        )

    # --- Size help ---
    if intent_type == "size_help":
        return ChatResponse(
            message="Beden önerisi için size yardımcı olabilirim efendim. Lütfen önce bir ürün seçin, ardından boy ve kilonuzu yazın; size en uygun bedeni hemen bulayım.",
            conversation_id=request.conversation_id,
        )

    # --- Product search / Outfit combo ---
    keywords = intent.get("keywords", [])
    category = intent.get("category")
    color = intent.get("color")

    # Build search keywords
    search_kws = list(keywords)
    if not search_kws and category:
        search_kws.append(category)

    # If no keywords at all, show a welcome message instead of random products
    if not search_kws:
        return ChatResponse(
            message="Beymen'e hoş geldiniz efendim! Size nasıl yardımcı olabilirim? Palto, mont, ceket, pantolon, takım elbise, ayakkabı gibi kategorilerde arama yapabilirsiniz.",
            conversation_id=request.conversation_id,
        )

    found = await search_products(search_kws, limit=3)

    if not found:
        # Smart suggestion: offer related categories instead of empty response
        cat_lower = category.lower() if category else ""
        suggestion_cats = _COMBO_MAP.get(cat_lower, ["palto", "ceket", "pantolon"])
        suggestions = []
        for scat in suggestion_cats[:3]:
            suggestions = await search_products([scat], limit=3)
            if suggestions:
                break

        if suggestions:
            search_term = " ".join(keywords) if keywords else (category or "")
            styled_msg = await generate_styled_response(
                request.message, suggestions, []
            )
            return ChatResponse(
                message=f"Maalesef '{search_term}' kategorisinde ürün bulamadım efendim, ancak bunları beğenebileceğinizi düşünüyorum:\n\n{styled_msg}",
                products=suggestions,
                combos=[],
                conversation_id=request.conversation_id,
            )
        else:
            return ChatResponse(
                message=f"Maalesef '{' '.join(keywords)}' aramanızla eşleşen bir ürün bulamadım efendim. Palto, mont, ceket, pantolon gibi kategorilerde arama yapabilirsiniz.",
                conversation_id=request.conversation_id,
            )

    # No combo generation at search time — combos are fetched on-demand
    # via /api/v1/products/{product_id}/combos after user selects a product

    # Generate styled message
    styled_msg = await generate_styled_response(request.message, found, [])

    return ChatResponse(
        message=styled_msg,
        products=found,
        combos=[],
        main_product=found[0] if found else None,
        conversation_id=request.conversation_id,
    )


# =============================================================================
# ON-DEMAND COMBO ENDPOINT — lazy fetch for post-selection combo suggestions
# =============================================================================

@app.get("/api/v1/products/{product_id}/combos", tags=["Products"])
async def get_product_combos_endpoint(
    product_id: str,
    limit: int = 2,
    target_category: Optional[str] = None,
):
    """
    Fetch combo/complementary products for a specific product.

    Args:
        product_id: The product to find combos for.
        limit: Max combo products to return.
        target_category: Optional specific category to filter combos
                         (e.g. "pantolon"). If omitted, returns from all
                         complementary categories.

    Returns combo_categories: list of all possible complementary categories
    so the widget can show category picker buttons.
    """
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(Product).where(Product.id == product_id, Product.is_active == True)
        result = await session.execute(stmt)
        product = result.scalars().first()

    if not product:
        return {"combos": [], "product_id": product_id, "category": None, "combo_categories": []}

    p_dict = _product_to_dict(product)
    category = p_dict.get("category") or _guess_category(p_dict["name"])
    if not category:
        return {"combos": [], "product_id": product_id, "category": None, "combo_categories": []}

    # All possible complementary categories for this product
    combo_categories = _COMBO_MAP.get(category.lower(), [])

    combos = await get_combo_products(
        category, product_id, limit=limit, target_category=target_category
    )
    return {
        "combos": combos,
        "product_id": product_id,
        "category": category,
        "combo_categories": combo_categories,
    }


# =============================================================================
# CART ENDPOINT — placeholder for future cart integration
# =============================================================================

class CartItem(BaseModel):
    product_id: str
    size: Optional[str] = None
    quantity: int = 1


class CartRequest(BaseModel):
    items: List[CartItem]


@app.post("/api/v1/cart", tags=["Cart"])
async def add_to_cart(request: CartRequest):
    """
    Placeholder cart endpoint.

    Accepts selected products with optional size and quantity.
    Currently logs the request and returns success.
    Future: integrate with e-commerce cart system.
    """
    print(f"[Cart] {len(request.items)} items added:")
    for item in request.items:
        print(f"  - product={item.product_id}, size={item.size}, qty={item.quantity}")

    return {
        "status": "ok",
        "added_count": len(request.items),
        "items": [item.model_dump() for item in request.items],
    }


# =============================================================================
# INVENTORY ENDPOINT (now from DB)
# =============================================================================

@app.get("/api/v1/inventory", tags=["Inventory"])
async def get_inventory():
    """Get the full product inventory from the database."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(Product).where(Product.is_active == True).order_by(Product.created_at.desc()).limit(100)
        result = await session.execute(stmt)
        rows = result.scalars().all()
        items = [_product_to_dict(r) for r in rows]
    return {"products": items, "total": len(items)}


# =============================================================================
# IMAGE ANALYSIS ENDPOINT (GPT-4o Vision) — kept simple, uses DB now
# =============================================================================

@app.post("/api/v1/analyze-image", tags=["AI Vision"])
async def analyze_image(file: UploadFile = File(...)):
    """Analyze an uploaded image and find matching products using GPT-4o Vision."""
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return {"message": "Gorsel analizi su anda kullanilamiyor.", "main_product": None, "combo_product": None}

    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        return {"message": "Desteklenmeyen format. JPEG, PNG veya WebP yukleyin.", "main_product": None, "combo_product": None}

    try:
        image_data = await file.read()
        base64_image = base64.b64encode(image_data).decode("utf-8")

        vision_prompt = """Fotoğraftaki kıyafeti analiz et. Türkçe arama anahtar kelimeleri çıkar.
JSON döndür: {"keywords": ["siyah", "palto"], "category": "palto|mont|ceket|pantolon|...", "color": "siyah"}
Sadece JSON."""

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": vision_prompt},
                        {"role": "user", "content": [
                            {"type": "text", "text": "Bu kiyafeti analiz et."},
                            {"type": "image_url", "image_url": {"url": f"data:{file.content_type};base64,{base64_image}", "detail": "low"}},
                        ]},
                    ],
                    "max_tokens": 200,
                    "temperature": 0.3,
                },
                timeout=60.0,
            )

            if resp.status_code != 200:
                return {"message": "Gorsel analizi hatasi.", "main_product": None, "combo_product": None}

            raw = resp.json()["choices"][0]["message"]["content"]
            if "```json" in raw:
                raw = raw.split("```json")[1].split("```")[0]
            elif "```" in raw:
                raw = raw.split("```")[1].split("```")[0]
            parsed = json.loads(raw.strip())

        kws = parsed.get("keywords", [])
        found = await search_products(kws, limit=3) if kws else []

        # Per-product combo generation (same pattern as chat endpoint)
        all_found_ids = {p["id"] for p in found}
        all_combos_flat = []

        for product in found:
            cat = product.get("category") or _guess_category(product["name"])
            if cat:
                product_combos = await get_combo_products(
                    cat, exclude_id=product["id"], limit=2, exclude_ids=all_found_ids,
                )
                product["combos"] = product_combos
                all_combos_flat.extend(product_combos)
            else:
                product["combos"] = []

        seen_ids = set()
        unique_combos = []
        for c in all_combos_flat:
            if c["id"] not in seen_ids:
                seen_ids.add(c["id"])
                unique_combos.append(c)

        msg = await generate_styled_response("gorsel arama", found, unique_combos) if found else "Bu gorsele uygun urun bulamadim."
        return {
            "message": msg,
            "products": found,
            "combos": unique_combos,
            "main_product": found[0] if found else None,
            "combo_product": unique_combos[0] if unique_combos else None,
        }

    except Exception as e:
        print(f"Vision error: {e}")
        return {"message": "Gorsel islenirken hata olustu.", "main_product": None, "combo_product": None}


# =============================================================================
# HEALTH & ROOT
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    return {
        "name": "FitEngine API",
        "version": "3.0.0",
        "status": "healthy",
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health_check():
    count = await get_product_count()
    return {"status": "healthy", "environment": settings.environment, "product_count": count}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": "An unexpected error occurred" if settings.is_production else str(exc)},
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=not settings.is_production)
