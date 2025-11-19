import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Product, Order, OrderItem

app = FastAPI(title="EV Parts Store API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "EV Parts Store Backend Running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os
    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return response

# Helper to convert ObjectId to string

def serialize(doc):
    if not doc:
        return doc
    doc = dict(doc)
    if "_id" in doc:
        doc["id"] = str(doc.pop("_id"))
    return doc

# Seed sample products if collection empty
@app.post("/seed")
def seed_products():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    count = db["product"].count_documents({})
    if count > 0:
        return {"seeded": False, "message": "Products already exist"}
    samples = [
        {
            "title": "Level 2 Home Charger",
            "description": "Fast 32A wall-mounted EVSE with WiFi smart scheduling.",
            "price": 499.0,
            "category": "charging",
            "in_stock": True,
            "image": "https://images.unsplash.com/photo-1593941707882-a5bba14938c1?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "Type 2 Charging Cable 7m",
            "description": "Durable T2 to T2 cable, 32A, weatherproof.",
            "price": 129.0,
            "category": "cables",
            "in_stock": True,
            "image": "https://images.unsplash.com/photo-1607860108855-0a3d85e9e599?q=80&w=1200&auto=format&fit=crop"
        },
        {
            "title": "Portable Tire Inflator",
            "description": "Digital compressor with auto-stop and LED light.",
            "price": 59.0,
            "category": "accessories",
            "in_stock": True,
            "image": "https://images.unsplash.com/photo-1627228616588-46e0cd85f618?q=80&w=1200&auto=format&fit=crop"
        }
    ]
    for p in samples:
        db["product"].insert_one(p)
    return {"seeded": True, "count": len(samples)}

@app.get("/products")
def list_products():
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")
    items = [serialize(p) for p in db["product"].find({}).limit(50)]
    return {"items": items}

class CartItem(BaseModel):
    product_id: str
    quantity: int

class CheckoutRequest(BaseModel):
    items: List[CartItem]
    customer_name: str
    email: str
    address: str

@app.post("/checkout")
def checkout(payload: CheckoutRequest):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not configured")

    # Fetch products and compute total
    product_map = {}
    ids = []
    for item in payload.items:
        try:
            ids.append(ObjectId(item.product_id))
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid product id")
    for p in db["product"].find({"_id": {"$in": ids}}):
        product_map[str(p["_id"])] = p

    order_items: List[OrderItem] = []
    total = 0.0
    for ci in payload.items:
        prod = product_map.get(ci.product_id)
        if not prod:
            raise HTTPException(status_code=400, detail=f"Product not found: {ci.product_id}")
        qty = max(1, ci.quantity)
        price = float(prod.get("price", 0))
        total += price * qty
        order_items.append(OrderItem(
            product_id=ci.product_id,
            title=prod.get("title", ""),
            quantity=qty,
            price=price
        ))

    order = Order(
        items=order_items,
        total=round(total, 2),
        customer_name=payload.customer_name,
        email=payload.email,
        address=payload.address
    )

    order_id = create_document("order", order)
    return {"order_id": order_id, "total": order.total}

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
