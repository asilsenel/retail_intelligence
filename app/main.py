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
import base64
import httpx

from app.config import settings
from app.routers import products, recommendations


# =============================================================================
# DEMO INVENTORY - Expanded Product Catalog
# =============================================================================

DEMO_INVENTORY = [
    {
        "id": "2608e0bf-7f8c-47bb-b6c5-84200460638b",
        "name": "Slim Fit Klasik Yaka Gömlek",
        "brand": "Beymen Club",
        "category": "gömlek",
        "category_en": "shirt",
        "price": "2.499 TL",
        "fit_type": "Slim Fit",
        "color": "Beyaz",
        "fabric": "%100 Pamuk",
        "keywords": ["gömlek", "shirt", "beyaz", "white", "slim", "klasik"],
        "image_key": "shirt_white"
    },
    {
        "id": "c5118cf5-aa71-434e-8f2a-2b159c9d8bc7",
        "name": "Regular Fit Oxford Gömlek",
        "brand": "Beymen Club",
        "category": "gömlek",
        "category_en": "shirt",
        "price": "1.899 TL",
        "fit_type": "Regular Fit",
        "color": "Mavi",
        "fabric": "%100 Pamuk",
        "keywords": ["gömlek", "shirt", "mavi", "blue", "oxford", "regular"],
        "image_key": "shirt_blue"
    },
    {
        "id": "57337148-0b35-4141-84b3-bc9ea4f55aa0",
        "name": "Slim Fit Pamuklu Gömlek",
        "brand": "Network",
        "category": "gömlek",
        "category_en": "shirt",
        "price": "1.599 TL",
        "fit_type": "Slim Fit",
        "color": "Lacivert",
        "fabric": "%97 Pamuk, %3 Elastan",
        "keywords": ["gömlek", "shirt", "lacivert", "navy", "slim", "pamuk"],
        "image_key": "shirt_navy"
    },
    {
        "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "name": "Kruvaze Lacivert Blazer Ceket",
        "brand": "Beymen Club",
        "category": "ceket",
        "category_en": "jacket",
        "price": "8.999 TL",
        "fit_type": "Slim Fit",
        "color": "Lacivert",
        "fabric": "%55 Yün, %45 Polyester",
        "keywords": ["ceket", "jacket", "blazer", "lacivert", "navy", "kruvaze", "double-breasted"],
        "image_key": "blazer_navy"
    },
    {
        "id": "b2c3d4e5-f6a7-8901-bcde-f23456789012",
        "name": "Slim Fit Chino Pantolon",
        "brand": "Network",
        "category": "pantolon",
        "category_en": "pants",
        "price": "1.799 TL",
        "fit_type": "Slim Fit",
        "color": "Bej",
        "fabric": "%98 Pamuk, %2 Elastan",
        "keywords": ["pantolon", "pants", "chino", "bej", "beige", "slim"],
        "image_key": "chino_beige"
    },
    {
        "id": "c3d4e5f6-a7b8-9012-cdef-345678901234",
        "name": "Klasik Kesim Yün Pantolon",
        "brand": "Beymen Club",
        "category": "pantolon",
        "category_en": "pants",
        "price": "3.499 TL",
        "fit_type": "Regular Fit",
        "color": "Antrasit",
        "fabric": "%70 Yün, %30 Polyester",
        "keywords": ["pantolon", "pants", "klasik", "yün", "wool", "antrasit", "grey"],
        "image_key": "pants_grey"
    }
]

# Unsplash image mappings for high-quality demo visuals
IMAGE_URLS = {
    "shirt_white": "https://images.unsplash.com/photo-1602810318383-e386cc2a3ccf?w=400&q=80",
    "shirt_blue": "https://images.unsplash.com/photo-1620799140408-edc6dcb6d633?w=400&q=80",
    "shirt_navy": "https://images.unsplash.com/photo-1596755094514-f87e34085b2c?w=400&q=80",
    "blazer_navy": "https://images.unsplash.com/photo-1594938298603-c8148c4dae35?w=400&q=80",
    "chino_beige": "https://images.unsplash.com/photo-1473966968600-fa801b869a1a?w=400&q=80",
    "pants_grey": "https://images.unsplash.com/photo-1624378439575-d8705ad7ae80?w=400&q=80",
    "default": "https://images.unsplash.com/photo-1441986300917-64674bd600d8?w=400&q=80"
}


def get_product_image(product: dict) -> str:
    """Get Unsplash image URL for a product."""
    key = product.get("image_key", "default")
    return IMAGE_URLS.get(key, IMAGE_URLS["default"])


def get_inventory_for_prompt() -> str:
    """Format inventory as JSON for the AI prompt."""
    simplified = []
    for p in DEMO_INVENTORY:
        simplified.append({
            "id": p["id"],
            "name": p["name"],
            "brand": p["brand"],
            "category": p["category"],
            "price": p["price"],
            "fit_type": p["fit_type"],
            "color": p["color"]
        })
    return json.dumps(simplified, ensure_ascii=False, indent=2)


def find_product_by_id(product_id: str) -> Optional[dict]:
    """Find a product by its ID."""
    for p in DEMO_INVENTORY:
        if p["id"] == product_id:
            return p
    return None


def get_combo_suggestion(main_product: dict) -> Optional[dict]:
    """Get a complementary product for outfit recommendation."""
    category = main_product.get("category")
    
    # Combo logic
    if category == "ceket":
        # Jacket -> Suggest pants or shirt
        for p in DEMO_INVENTORY:
            if p["category"] == "pantolon":
                return p
    elif category == "gömlek":
        # Shirt -> Suggest jacket or pants
        for p in DEMO_INVENTORY:
            if p["category"] == "ceket":
                return p
    elif category == "pantolon":
        # Pants -> Suggest shirt or jacket
        for p in DEMO_INVENTORY:
            if p["category"] in ["gömlek", "ceket"]:
                return p
    
    return None


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
# OPENAI INTEGRATION
# =============================================================================

SYSTEM_PROMPT_TEMPLATE = """Sen Beymen'in Elit AI Stilistisin. Müşterilere lüks moda konusunda yardımcı oluyorsun.

**MEVCUT ENVANTER:**
{inventory}

**KURALLAR:**
1. **Sıkı Eşleştirme:** Müşteri "ceket" isterse, SADECE envanterdeki ceket kategorisinden öneri yap. Eğer istenen ürün yoksa, özür dile ve mevcut alternatifleri sun. Ceket istendiğinde gömlek önerme.

2. **Kombin Önerisi:** Bir ana ürün önerdiğinde, MUTLAKA envanterden uyumlu bir tamamlayıcı ürün öner. Örneğin: "Bu ceketin altına Bej Chino pantolonumuz harika olur" veya "Bu gömlekle Lacivert Blazer ceketimiz mükemmel bir kombin oluşturur."

3. **Beden Yardımı:** Müşteri beden sorduğunda, ürün ID'sini ver ve "Bedeninizi bulmam için boy ve kilonuzu yazabilir misiniz?" de.

4. **Dil ve Ton:** Her zaman Türkçe konuş. Kibar, profesyonel ve lüks bir ton kullan. "Efendim", "Memnuniyetle" gibi ifadeler kullan.

5. **JSON Çıktı Formatı:** Cevabını SADECE aşağıdaki JSON formatında ver, başka hiçbir şey yazma:
{{
    "message": "Müşteriye mesajın (kombin önerisi dahil)",
    "recommended_product_id": "ana ürünün id'si veya null",
    "related_product_id": "kombin ürününün id'si veya null"
}}

ÖNEMLİ: Sadece JSON döndür, başka açıklama yapma."""


async def call_openai(user_message: str) -> dict:
    """Call OpenAI API with the chat message."""
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        # Fallback to rule-based response if no API key
        return await fallback_response(user_message)
    
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(inventory=get_inventory_for_prompt())
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_message}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=30.0
            )
            
            if response.status_code != 200:
                print(f"OpenAI API error: {response.status_code} - {response.text}")
                return await fallback_response(user_message)
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON from response
            try:
                # Try to extract JSON from the response
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                result = json.loads(content.strip())
                return result
            except json.JSONDecodeError:
                # If JSON parsing fails, return the message as-is
                return {"message": content, "recommended_product_id": None, "related_product_id": None}
                
    except Exception as e:
        print(f"OpenAI API exception: {e}")
        return await fallback_response(user_message)


async def fallback_response(user_message: str) -> dict:
    """Rule-based fallback when OpenAI is not available."""
    lower = user_message.lower()
    
    # Detect category intent
    if "ceket" in lower or "blazer" in lower or "jacket" in lower:
        product = next((p for p in DEMO_INVENTORY if p["category"] == "ceket"), None)
        combo = get_combo_suggestion(product) if product else None
        
        if product:
            msg = f"Memnuniyetle efendim. Size {product['brand']} {product['name']} önerebilirim. {product['price']} fiyatıyla mükemmel bir seçim."
            if combo:
                msg += f" Bu ceketin altına {combo['brand']} {combo['name']} ({combo['color']}) harika bir kombin oluşturur."
            return {
                "message": msg,
                "recommended_product_id": product["id"],
                "related_product_id": combo["id"] if combo else None
            }
    
    elif "pantolon" in lower or "chino" in lower or "pants" in lower:
        product = next((p for p in DEMO_INVENTORY if p["category"] == "pantolon"), None)
        combo = get_combo_suggestion(product) if product else None
        
        if product:
            msg = f"Tabii efendim. {product['brand']} {product['name']} tam size göre. {product['fit_type']} kesimi ve {product['color']} rengi çok şık."
            if combo:
                msg += f" Üstüne {combo['brand']} {combo['name']} ile harika görünürsünüz."
            return {
                "message": msg,
                "recommended_product_id": product["id"],
                "related_product_id": combo["id"] if combo else None
            }
    
    elif "gömlek" in lower or "shirt" in lower:
        # Check for color preference
        if "mavi" in lower or "blue" in lower:
            product = next((p for p in DEMO_INVENTORY if p["category"] == "gömlek" and "mavi" in p.get("color", "").lower()), None)
        elif "beyaz" in lower or "white" in lower:
            product = next((p for p in DEMO_INVENTORY if p["category"] == "gömlek" and "beyaz" in p.get("color", "").lower()), None)
        else:
            product = next((p for p in DEMO_INVENTORY if p["category"] == "gömlek"), None)
        
        combo = get_combo_suggestion(product) if product else None
        
        if product:
            msg = f"Elbette efendim. {product['brand']} {product['name']} ({product['color']}) harika bir seçim. {product['fit_type']} kalıbı ve {product['fabric']} kumaşıyla çok konforlu."
            if combo:
                msg += f" Bu gömlekle {combo['brand']} {combo['name']} kombinleyebilirsiniz."
            return {
                "message": msg,
                "recommended_product_id": product["id"],
                "related_product_id": combo["id"] if combo else None
            }
    
    elif "beden" in lower or "ölçü" in lower or "size" in lower:
        return {
            "message": "Beden önerisi için size yardımcı olabilirim. Hangi ürün için beden arıyorsunuz? Ürünü seçtikten sonra boy ve kilonuzu yazarsanız size en uygun bedeni bulabilirim.",
            "recommended_product_id": None,
            "related_product_id": None
        }
    
    elif "kombin" in lower or "outfit" in lower:
        jacket = next((p for p in DEMO_INVENTORY if p["category"] == "ceket"), None)
        pants = next((p for p in DEMO_INVENTORY if p["category"] == "pantolon"), None)
        shirt = next((p for p in DEMO_INVENTORY if p["category"] == "gömlek"), None)
        
        msg = "Mükemmel bir kombin için şunları önerebilirim:\n"
        if jacket:
            msg += f"• {jacket['brand']} {jacket['name']} ({jacket['price']})\n"
        if shirt:
            msg += f"• {shirt['brand']} {shirt['name']} ({shirt['price']})\n"
        if pants:
            msg += f"• {pants['brand']} {pants['name']} ({pants['price']})\n"
        msg += "\nBu üçlü birlikte çok şık görünecektir."
        
        return {
            "message": msg,
            "recommended_product_id": jacket["id"] if jacket else None,
            "related_product_id": pants["id"] if pants else None
        }
    
    # Default response
    return {
        "message": "Beymen'e hoş geldiniz efendim. Size nasıl yardımcı olabilirim? Gömlek, ceket veya pantolon mu arıyorsunuz? Beden önerisi de verebilirim.",
        "recommended_product_id": None,
        "related_product_id": None
    }


# =============================================================================
# APPLICATION SETUP
# =============================================================================

APP_METADATA = {
    "title": "FitEngine API",
    "description": """
## 🎯 Reduce Returns with AI-Powered Size Recommendations

FitEngine provides an embeddable size recommendation widget for e-commerce 
clothing brands. Our statistical heuristic model considers:

- **Body Measurements**: Estimated from height, weight, and body shape
- **Ease Calculation (Bolluk Payı)**: Proper garment-to-body fit allowance
- **Fabric Properties**: Stretch fabrics require less ease
- **Fit Preferences**: Tight, true-to-size, or loose

### Quick Start

1. **Ingest Products**: Push your product catalog with measurements
2. **Embed Widget**: Add our JavaScript snippet to your product pages
3. **Get Recommendations**: Users receive personalized size suggestions

### Authentication

Use the `X-API-Key` header with your tenant API key.
For testing, use: `test-api-key`
    """,
    "version": "2.0.0",
    "contact": {
        "name": "FitEngine Support",
        "email": "support@fitengine.io"
    },
    "license_info": {
        "name": "Proprietary",
    }
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    print("🚀 FitEngine API starting...")
    print(f"📦 Loaded {len(DEMO_INVENTORY)} products in inventory")
    yield
    print("👋 FitEngine API shutting down...")


# Create FastAPI application
app = FastAPI(
    **APP_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS middleware for widget embedding
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list if settings.is_production else ["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"]
)


@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    """Add request timing and ID headers."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = f"{process_time:.4f}"
    return response


# Include routers
app.include_router(products.router)
app.include_router(recommendations.router)


# =============================================================================
# CHAT ENDPOINT
# =============================================================================

@app.post("/api/v1/chat", response_model=ChatResponse, tags=["AI Chat"])
async def chat_with_ai(request: ChatRequest):
    """
    Chat with the Beymen AI Stylist.
    
    The AI can:
    - Recommend products from inventory
    - Suggest outfit combinations (kombin)
    - Help with size recommendations
    - Speak Turkish with a luxury tone
    
    **Example messages:**
    - "Mavi gömlek arıyorum"
    - "Ceket var mı?"
    - "Kombin önerir misin?"
    - "Beden bilgisi almak istiyorum"
    """
    # Get AI response
    ai_response = await call_openai(request.message)
    
    # Build response with product details
    main_product = None
    combo_product = None
    
    # Get main product details
    if ai_response.get("recommended_product_id"):
        product = find_product_by_id(ai_response["recommended_product_id"])
        if product:
            main_product = {
                "id": product["id"],
                "name": product["name"],
                "brand": product["brand"],
                "price": product["price"],
                "fit_type": product["fit_type"],
                "color": product["color"],
                "category": product.get("category", ""),
                "image_url": get_product_image(product)
            }
    
    # Get combo product details (full object, not just ID)
    if ai_response.get("related_product_id"):
        related = find_product_by_id(ai_response["related_product_id"])
        if related:
            combo_product = {
                "id": related["id"],
                "name": related["name"],
                "brand": related["brand"],
                "price": related["price"],
                "fit_type": related["fit_type"],
                "color": related["color"],
                "category": related.get("category", ""),
                "image_url": get_product_image(related)
            }
    
    return ChatResponse(
        message=ai_response.get("message", "Özür dilerim, bir sorun oluştu."),
        main_product=main_product,
        combo_product=combo_product,
        conversation_id=request.conversation_id
    )


@app.get("/api/v1/inventory", tags=["Inventory"])
async def get_inventory():
    """Get the full product inventory with images."""
    result = []
    for p in DEMO_INVENTORY:
        result.append({
            **p,
            "image_url": get_product_image(p)
        })
    return {"products": result, "total": len(result)}


# =============================================================================
# IMAGE ANALYSIS ENDPOINT (GPT-4o Vision)
# =============================================================================

VISION_SYSTEM_PROMPT = """Sen bir Moda Eşleştirme Uzmanısın. Kullanıcının yüklediği fotoğrafı analiz et.

**MEVCUT ENVANTER:**
{inventory}

**GÖREV:**
1. Fotoğraftaki kıyafeti analiz et (renk, stil, tür).
2. Envanterden en çok benzeyen ürünü bul.
3. Eğer uygun ürün varsa, onun ID'sini döndür.
4. Eğer hiçbir ürün uymuyorsa, bunu belirt.

**JSON ÇIKTI FORMATI:**
{{
    "message": "Fotoğraftaki ürünle ilgili yorumun ve önerdiğin ürün hakkında açıklama",
    "matched_product_id": "eşleşen ürünün id'si veya null",
    "confidence": "high/medium/low/none"
}}

Sadece JSON döndür, başka bir şey yazma."""


@app.post("/api/v1/analyze-image", tags=["AI Vision"])
async def analyze_image(file: UploadFile = File(...)):
    """
    Analyze an uploaded image and find matching products.
    
    Uses GPT-4o Vision to identify clothing items and match
    them against our inventory.
    
    **Supported formats:** JPEG, PNG, WebP
    """
    api_key = os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        return {
            "message": "Görsel analizi şu anda kullanılamıyor. Lütfen metin ile arama yapın.",
            "main_product": None,
            "combo_product": None
        }
    
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/webp", "image/jpg"]
    if file.content_type not in allowed_types:
        return {
            "message": "Desteklenmeyen dosya formatı. Lütfen JPEG, PNG veya WebP yükleyin.",
            "main_product": None,
            "combo_product": None
        }
    
    try:
        # Read and encode image
        image_data = await file.read()
        base64_image = base64.b64encode(image_data).decode("utf-8")
        
        # Determine media type
        media_type = file.content_type
        
        # Build system prompt with inventory
        system_prompt = VISION_SYSTEM_PROMPT.format(inventory=get_inventory_for_prompt())
        
        # Call GPT-4o Vision
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4o",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "Bu fotoğraftaki kıyafeti analiz et ve envanterden en uygun ürünü öner."
                                },
                                {
                                    "type": "image_url",
                                    "image_url": {
                                        "url": f"data:{media_type};base64,{base64_image}",
                                        "detail": "low"
                                    }
                                }
                            ]
                        }
                    ],
                    "max_tokens": 500,
                    "temperature": 0.5
                },
                timeout=60.0
            )
            
            if response.status_code != 200:
                print(f"Vision API error: {response.status_code} - {response.text}")
                return {
                    "message": "Görsel analizi sırasında bir hata oluştu. Lütfen tekrar deneyin.",
                    "main_product": None,
                    "combo_product": None
                }
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            # Parse JSON response
            try:
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0]
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0]
                
                result = json.loads(content.strip())
            except json.JSONDecodeError:
                result = {"message": content, "matched_product_id": None, "confidence": "none"}
        
        # Build response with product details
        main_product = None
        combo_product = None
        
        if result.get("matched_product_id"):
            product = find_product_by_id(result["matched_product_id"])
            if product:
                main_product = {
                    "id": product["id"],
                    "name": product["name"],
                    "brand": product["brand"],
                    "price": product["price"],
                    "fit_type": product["fit_type"],
                    "color": product["color"],
                    "category": product.get("category", ""),
                    "image_url": get_product_image(product)
                }
                
                # Get combo suggestion
                combo = get_combo_suggestion(product)
                if combo:
                    combo_product = {
                        "id": combo["id"],
                        "name": combo["name"],
                        "brand": combo["brand"],
                        "price": combo["price"],
                        "fit_type": combo["fit_type"],
                        "color": combo["color"],
                        "category": combo.get("category", ""),
                        "image_url": get_product_image(combo)
                    }
        
        return {
            "message": result.get("message", "Görsel analizi tamamlandı."),
            "main_product": main_product,
            "combo_product": combo_product,
            "confidence": result.get("confidence", "medium")
        }
        
    except Exception as e:
        print(f"Vision API exception: {e}")
        return {
            "message": "Görsel işlenirken bir hata oluştu. Lütfen tekrar deneyin.",
            "main_product": None,
            "combo_product": None
        }


# =============================================================================
# HEALTH & ROOT ENDPOINTS
# =============================================================================

@app.get("/", tags=["Health"])
async def root():
    """API root - returns basic info and health status."""
    return {
        "name": "FitEngine API",
        "version": "3.0.0",
        "status": "healthy",
        "docs": "/docs",
        "endpoints": {
            "ingest_product": "POST /api/v1/ingest-product",
            "recommend": "POST /api/v1/recommend",
            "products": "GET /api/v1/products",
            "chat": "POST /api/v1/chat",
            "inventory": "GET /api/v1/inventory",
            "analyze_image": "POST /api/v1/analyze-image"
        }
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """Health check endpoint for load balancers."""
    return {
        "status": "healthy",
        "environment": settings.environment,
        "inventory_count": len(DEMO_INVENTORY)
    }


# Error handlers
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions gracefully."""
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "message": "An unexpected error occurred" if settings.is_production else str(exc)
        }
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=not settings.is_production
    )

