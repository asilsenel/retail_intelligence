# 🎯 FitEngine API

> **B2B SaaS Size Recommendation Service**  
> Reduce return rates with AI-powered size recommendations for e-commerce clothing brands.

## 🚀 Quick Start

### Prerequisites
- Python 3.10+
- PostgreSQL (or Supabase account)

### Installation

```bash
# Clone and navigate to project
cd /Users/asil/PycharmProjects/PersonalStylist

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env with your database credentials
```

### Run the Server

```bash
uvicorn app.main:app --reload --port 8000
```

Open **http://localhost:8000/docs** for interactive API documentation.

---

## 📡 API Endpoints

### Authentication
Include `X-API-Key` header with your tenant API key.  
For testing, use: `test-api-key`

### Core Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/ingest-product` | POST | Push product measurement data |
| `/api/v1/recommend` | POST | Get size recommendation |
| `/api/v1/products` | GET | List all products |
| `/api/v1/products/{id}` | GET | Get product details |
| `/api/v1/quick-recommend` | POST | Quick recommendation (no prior ingestion) |

---

## 🧮 Recommendation Algorithm

### Ease (Bolluk Payı) Calculation

The core concept: **Garment must be larger than body** for comfortable fit.

| Fit Type | Chest Ease | Waist Ease |
|----------|-----------|------------|
| Slim Fit | +2-3cm | +2cm |
| Regular Fit | +4-6cm | +5cm |
| Loose Fit | +8-12cm | +10cm |
| Oversized | +15cm+ | +15cm+ |

**Stretch fabrics** (elastane, spandex) reduce required ease by up to 2.5cm.

### Body Estimation

From height + weight + body shape, we estimate:
- Chest circumference
- Waist circumference  
- Hip circumference
- Shoulder width

---

## 🔧 Widget Integration

Add to your product pages:

```html
<!-- Include the widget script -->
<script src="https://your-cdn.com/fit-engine-widget.js"></script>

<!-- Add a trigger button -->
<button id="find-my-size">Find My Size</button>

<!-- Initialize -->
<script>
  FitEngine.init({
    apiUrl: 'https://api.fitengine.io',
    productId: 'YOUR_PRODUCT_UUID',
    language: 'en' // or 'tr' for Turkish
  });
</script>
```

---

## 🗄️ Database Setup

### Supabase

1. Go to SQL Editor in Supabase Dashboard
2. Run `sql/schema.sql`
3. Update `.env` with your connection string

### Local PostgreSQL

```bash
psql -d your_database -f sql/schema.sql
```

---

## 📊 Analytics

Track widget usage via the `widget_events` table:
- Total size checks per product
- Most recommended sizes
- Confidence scores over time
- Unique users & sessions

---

## 🧪 Testing

### Test the API

```bash
# 1. Ingest a product
curl -X POST http://localhost:8000/api/v1/ingest-product \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key" \
  -d '{
    "sku": "TEST-001",
    "name": "Test Shirt",
    "fit_type": "regular_fit",
    "fabric_composition": {"cotton": 100},
    "measurements": {
      "S": {"chest_width": 104, "length": 72},
      "M": {"chest_width": 110, "length": 74},
      "L": {"chest_width": 116, "length": 76}
    }
  }'

# 2. Get recommendation
curl -X POST http://localhost:8000/api/v1/recommend \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": "PRODUCT_UUID_FROM_STEP_1",
    "user_height": 180,
    "user_weight": 85,
    "body_shape": "average"
  }'
```

### Test the Widget

Open `widget/test.html` in a browser (server must be running).

---

## 📁 Project Structure

```
PersonalStylist/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Environment config
│   ├── models/
│   │   ├── schemas.py       # Pydantic models
│   │   └── database.py      # SQLAlchemy models
│   ├── routers/
│   │   ├── products.py      # Product endpoints
│   │   └── recommendations.py
│   ├── services/
│   │   ├── body_estimator.py
│   │   └── recommendation_engine.py
│   └── middleware/
│       └── auth.py          # API key auth
├── sql/
│   └── schema.sql           # Database schema
├── widget/
│   ├── fit-engine-widget.js # Embeddable widget
│   └── test.html            # Widget demo page
├── requirements.txt
├── .env.example
└── README.md
```

---

## 📄 License

Proprietary - FitEngine © 2026
