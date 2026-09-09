import http.client
import urllib.parse
import json
import logging
from Database.config import get_db
from Database.data import insert_product

logger = logging.getLogger(__name__)

async def search_amazon_products(keyword):
    """Search Amazon products with error handling"""
    try:
        query = urllib.parse.quote(keyword)
        api_host = "real-time-amazon-data.p.rapidapi.com"
        api_key = "d5d656d29fmsheeede719dac5fc8p1c5c5ajsn7da55608f234"

        conn = http.client.HTTPSConnection(api_host)
        headers = {
            'x-rapidapi-key': api_key,
            'x-rapidapi-host': api_host
        }

        endpoint = f"/search?query={query}&country=US"

        conn.request("GET", endpoint, headers=headers)
        res = conn.getresponse()
        data = res.read().decode("utf-8")
        json_data = json.loads(data)

        products_found = json_data.get("data", {}).get("products", [])[:3]
        if not products_found:
            logger.warning("No Amazon products found")
            return []

        db = next(get_db())
        stored_products = []

        for item in products_found:
            # Format product data
            asin = item.get("asin", "N/A")
            product_data = {
                "title": item.get("product_title") or item.get("title", "No title"),
                "price": item.get("product_price", "0").replace("$", "").strip(),
                "product_star_rating": item.get("product_star_rating", "0"),
                "product_num_ratings": item.get("product_num_ratings", "0"),
                "product_url": f"https://www.amazon.com/dp/{asin}" if asin != "N/A" else "",
                "product_image_url": item.get("product_photo"),
                "sales_volume": item.get("sales_volume", "0")
            }

            # Store in database using unified inserter
            stored_product = insert_product(db, product_data, "Amazon")
            if stored_product:
                stored_products.append(stored_product)

        return stored_products

    except Exception as e:
        logger.error(f"Error in Amazon product search: {e}")
        return []

    finally:
        try:
            conn.close()
        except:
            pass