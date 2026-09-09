import http.client
import json
import sys
import asyncio
import logging
from Database.config import get_db
from Database.data import insert_product

# Configure logging
logger = logging.getLogger(__name__)

# AliExpress API setup
API_KEY = "d5d656d29fmsheeede719dac5fc8p1c5c5ajsn7da55608f234"
API_HOST = "aliexpress-true-api.p.rapidapi.com"

async def get_products(search_term):
    """Search AliExpress products with error handling"""
    try:
        encoded_search_term = search_term.replace(" ", "+")
        endpoint = (
            f"/api/v3/products?page_no=1&ship_to_country=US&keywords={encoded_search_term}"
            f"&target_currency=USD&target_language=EN&page_size=50&sort=SALE_PRICE_ASC"
        )

        conn = http.client.HTTPSConnection(API_HOST)
        headers = {
            'x-rapidapi-key': API_KEY,
            'x-rapidapi-host': API_HOST
        }
        
        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")

        try:
            products_json = json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return []

        items = products_json.get("products", [])
        if not items:
            logger.warning("No products found in AliExpress response")
            return []

        # Filter relevant products
        filtered_products = []
        search_term_lower = search_term.lower()
        
        db = next(get_db())
        stored_products = []

        for item in items:
            if not isinstance(item, dict):
                continue
                
            title = item.get("title") or item.get("product_title", "")
            if search_term_lower in title.lower():
                # Store in database using unified inserter
                stored_product = insert_product(db, item, "AliExpress")
                if stored_product:
                    stored_products.append(stored_product)
                filtered_products.append(item)

        return stored_products or []

    except Exception as e:
        logger.error(f"Error in AliExpress product search: {e}")
        return []

    finally:
        try:
            conn.close()
        except:
            pass

if __name__ == "__main__":
    # MySQL connection
    db = mysql.connector.connect(
        host="productsdb.cvce864kqv1q.us-east-2.rds.amazonaws.com",
        user="admin",
        password="malaysiaboleh",
        database="productsdb"
    )

    # Get the query (default or CLI)
    if len(sys.argv) > 1:
        query = sys.argv[1]
    else:
        query = "coffee cups"

    print(f"🔧 Running SEO pipeline for: '{query}'")
    search_keyword = asyncio.run(run_pipeline(query))
    print(f"🎯 Using keyword: '{search_keyword}'")

    # Get matching products from AliExpress
    matching_products = asyncio.run(get_products(search_keyword))

    if not matching_products:
        print("⚠️ No matching products found.")
    else:
        print(f"🔄 Found {len(matching_products)} products. Inserting into database...")
        for product in matching_products:
            try:
                insert_product(db, product)
            except Exception as e:
                print(f"🔥 Unexpected error during insert: {e}")

        # Print one example
        top_product = matching_products[0]
        print("\n🛍️ Example Product:")
        print("Title:", top_product.get("title") or top_product.get("product_title"))
        print("Price:", top_product.get("original_price"))
        print("Rating:", top_product.get("rating"))
        print("Image:", top_product.get("product_main_image_url"))

    db.close()

