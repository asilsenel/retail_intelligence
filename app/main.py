"""
FitEngine API - Main Application Entry Point

A B2B SaaS API for size recommendations, designed to help
e-commerce clothing brands reduce return rates.
"""
from fastapi import FastAPI, Request, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
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
    return {
        "id": str(p.id),
        "sku": p.sku,
        "name": p.name,
        "brand": brand or "Beymen",
        "price": price_str,
        "price_raw": p.price,
        "url": p.url,
        "image_url": p.image_url,
        "category": p.category or _guess_category(p.name),
        "sizes": p.sizes or [],
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


# Combo mapping: category -> list of complementary categories
_COMBO_MAP = {
    "palto": ["pantolon", "gömlek", "kazak"],
    "mont": ["pantolon", "gömlek", "kazak"],
    "kaban": ["pantolon", "gömlek", "kazak"],
    "ceket": ["pantolon", "gömlek"],
    "yelek": ["pantolon", "gömlek"],
    "parka": ["pantolon", "kazak"],
    "pardösü": ["pantolon", "gömlek"],
    "pantolon": ["ceket", "palto", "mont", "gömlek"],
    "gömlek": ["ceket", "pantolon", "palto"],
    "kazak": ["pantolon", "palto", "mont"],
    "tişört": ["pantolon", "ceket"],
}


async def search_products(keywords: List[str], limit: int = 3) -> List[dict]:
    """Search products table. All keywords must match (AND) for best relevance."""
    if not keywords:
        return []
    from sqlalchemy import and_
    session_factory = get_session_factory()
    async with session_factory() as session:
        conditions = [func.lower(Product.name).contains(kw.lower()) for kw in keywords]

        # AND: every keyword must appear in the name
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


async def get_combo_products(main_category: str, exclude_id: str, limit: int = 1) -> List[dict]:
    """Find complementary products for outfit combo."""
    target_cats = _COMBO_MAP.get(main_category, [])
    if not target_cats:
        return []

    session_factory = get_session_factory()
    async with session_factory() as session:
        # Build name-based category filter since 'category' column is often NULL
        cat_conditions = []
        for cat in target_cats:
            cat_conditions.append(func.lower(Product.name).contains(cat))

        stmt = (
            select(Product)
            .where(Product.is_active == True)
            .where(or_(*cat_conditions))
            .where(Product.id != exclude_id)
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
"Efendim", "Memnuniyetle" gibi ifadeler kullan. Kısa ve öz yanıt ver (2-3 cümle).

Müşteriye aşağıdaki ürünleri öneriyorsun:

**ANA ÜRÜN:**
{main_product}

**KOMBİN ÖNERİSİ:**
{combo_product}

Müşterinin orijinal mesajı: "{user_message}"

Yanıtında:
1. Ana ürünü tanıt (isim ve neden iyi bir seçim olduğunu belirt).
2. Kombin ürününü öner ("Bu ürünün altına/üstüne ... harika olur" gibi).
3. Beden yardımı teklif et.

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


async def generate_styled_response(user_message: str, main: dict, combo: Optional[dict]) -> str:
    """Ask OpenAI to write a luxurious Turkish response about these products."""
    api_key = os.getenv("OPENAI_API_KEY")

    main_desc = f"{main['brand']} - {main['name']}" + (f" ({main['price']})" if main.get("price") else "")
    combo_desc = "Yok" if not combo else f"{combo['brand']} - {combo['name']}" + (f" ({combo['price']})" if combo.get("price") else "")

    if api_key:
        try:
            prompt = STYLIST_PROMPT.format(
                main_product=main_desc,
                combo_product=combo_desc,
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
                        "max_tokens": 300,
                    },
                    timeout=15.0,
                )
                if resp.status_code == 200:
                    return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as e:
            print(f"Stylist response error: {e}")

    # Fallback
    msg = f"Memnuniyetle efendim! Size {main['brand']} {main['name']} önerebilirim."
    if main.get("price"):
        msg += f" Fiyatı {main['price']}."
    if combo:
        msg += f" Yanına {combo['brand']} {combo['name']} ile harika bir kombin oluşturabilirsiniz."
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
    return response


app.include_router(products.router)
app.include_router(recommendations.router)


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
    if not search_kws:
        # Generic — show popular items
        search_kws = ["palto", "ceket", "mont"]

    found = await search_products(search_kws, limit=3)

    if not found:
        return ChatResponse(
            message=f"Maalesef '{' '.join(keywords)}' aramanızla eşleşen bir ürün bulamadım efendim. Palto, mont, ceket, pantolon gibi kategorilerde arama yapabilirsiniz.",
            conversation_id=request.conversation_id,
        )

    main = found[0]
    main_cat = main.get("category") or _guess_category(main["name"])

    # Find combo
    combo = None
    if main_cat:
        combos = await get_combo_products(main_cat, main["id"], limit=1)
        combo = combos[0] if combos else None

    # Generate styled message
    styled_msg = await generate_styled_response(request.message, main, combo)

    return ChatResponse(
        message=styled_msg,
        main_product=main,
        combo_product=combo,
        conversation_id=request.conversation_id,
    )


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

        main_product = found[0] if found else None
        combo_product = None
        if main_product:
            cat = main_product.get("category") or _guess_category(main_product["name"])
            if cat:
                combos = await get_combo_products(cat, main_product["id"], limit=1)
                combo_product = combos[0] if combos else None

        msg = await generate_styled_response("gorsel arama", main_product, combo_product) if main_product else "Bu gorsele uygun urun bulamadim."
        return {"message": msg, "main_product": main_product, "combo_product": combo_product}

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
