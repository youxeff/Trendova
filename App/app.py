from flask import Flask, jsonify, request
from flask_cors import CORS
from Database.config import get_db
from Database.models import TiktokProduct
from Database.data import get_all_products, get_trending_products, search_products
from sqlalchemy import desc
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import asyncio
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={
    r"/api/*": {
        "origins": ["http://localhost:5173"],
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

@app.route("/")
def home():
    return jsonify({
        'status': 'healthy',
        'version': '1.0.0',
        'timestamp': datetime.now().isoformat()
    })

@app.route("/api/products")
def get_products():
    db = next(get_db())
    try:
        products = get_all_products(db)
        return jsonify([p.to_dict() for p in products])
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_products: {str(e)}")
        return jsonify({'error': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Error in get_products: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        db.close()

@app.route("/api/products/category/<category_id>")
def get_products_by_category(category_id):
    if not category_id:
        return jsonify({'error': 'Category ID is required'}), 400
        
    db = next(get_db())
    try:
        products = db.query(TiktokProduct).filter(
            TiktokProduct.supplier == category_id
        ).order_by(desc(TiktokProduct.rating)).all()
        
        return jsonify([p.to_dict() for p in products])
    except SQLAlchemyError as e:
        logger.error(f"Database error in get_products_by_category: {str(e)}")
        return jsonify({'error': 'Database error'}), 500
    except Exception as e:
        logger.error(f"Error in get_products_by_category: {str(e)}")
        return jsonify({'error': 'Internal server error'}), 500
    finally:
        db.close()

@app.route("/api/products/trending")
def get_trending():
    db = next(get_db())
    try:
        products = get_all_products(db)
        trending = sorted(products, key=lambda p: p.list_velocity or 0, reverse=True)[:10]
        return jsonify([p.to_dict() for p in trending])
    except Exception as e:
        logger.error(f"Error in get_trending: {str(e)}")
        return jsonify({'error': str(e)}), 500
    finally:
        db.close()

@app.route("/api/search", methods=["POST"])
async def unified_search():
    # Imported here so sentence-transformers and torch are not loaded at startup.
    # They are only needed for this route, which is not deployed.
    from Model.new_trend import run_pipeline
    from Model.cj_product_matcher import get_cj_products_and_store
    from Model.aliexpress import get_products as ali_search
    from Model.amazon_search import search_amazon_products
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Query is required"}), 400

    try:
        # Run the AI trend analysis pipeline to get optimized search keyword
        result = await run_pipeline(query)
        if not result:
            return jsonify({"error": "No results found"}), 404

        # Extract the best keyword from trend analysis
        keyword = result.get("theme", query)
        keywords = result.get("keywords", [])
        top_kw = keywords[0] if keywords else keyword

        logger.info(f"🔍 Optimized search keyword: {top_kw}")

        # Run concurrent product searches across marketplaces
        tasks = [
            asyncio.create_task(get_cj_products_and_store(top_kw)),
            asyncio.create_task(ali_search(top_kw)),
            asyncio.create_task(search_amazon_products(top_kw))
        ]

        # Gather results with error handling
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process marketplace results
        cj_products = results[0] if not isinstance(results[0], Exception) else []
        ali_products = results[1] if not isinstance(results[1], Exception) else []
        amazon_products = results[2] if not isinstance(results[2], Exception) else []

        # Prepare response
        response = {
            "keyword": top_kw,
            "analysis": result,
            "products": {
                "cj": [p.to_dict() if hasattr(p, 'to_dict') else p for p in cj_products],
                "aliexpress": [p.to_dict() if hasattr(p, 'to_dict') else p for p in ali_products],
                "amazon": [p.to_dict() if hasattr(p, 'to_dict') else p for p in amazon_products]
            }
        }

        return jsonify(response)

    except Exception as e:
        logger.error(f"Unified search error: {str(e)}")
        return jsonify({"error": "Search failed", "details": str(e)}), 500

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5001)
