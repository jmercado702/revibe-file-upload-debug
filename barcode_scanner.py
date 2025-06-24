import requests
import os
from urllib.parse import urlparse
from werkzeug.utils import secure_filename
import uuid

class ProductLookupService:
    """Service to lookup product information from barcodes"""
    
    def __init__(self):
        # UPC Database API - requires API key
        self.upc_api_key = os.environ.get('UPC_DATABASE_API_KEY')
        self.upc_api_url = "https://api.upcitemdb.com/prod/trial/lookup"
        
        # Open Food Facts API (free, no key required)
        self.openfoodfacts_url = "https://world.openfoodfacts.org/api/v0/product"
        
    def lookup_product(self, barcode):
        """Lookup product information by barcode"""
        product_info = None
        
        # Try UPC Database first if API key is available
        if self.upc_api_key:
            product_info = self._lookup_upc_database(barcode)
        
        # Fallback to Open Food Facts
        if not product_info:
            product_info = self._lookup_openfoodfacts(barcode)
            
        return product_info
    
    def _lookup_upc_database(self, barcode):
        """Lookup using UPC Database API"""
        try:
            headers = {
                'Authorization': f'Bearer {self.upc_api_key}',
                'Content-Type': 'application/json'
            }
            
            response = requests.get(
                f"{self.upc_api_url}?upc={barcode}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('items'):
                    item = data['items'][0]
                    return {
                        'title': item.get('title', ''),
                        'description': item.get('description', ''),
                        'brand': item.get('brand', ''),
                        'category': item.get('category', ''),
                        'images': item.get('images', []),
                        'source': 'UPC Database'
                    }
        except Exception as e:
            print(f"UPC Database lookup failed: {e}")
        
        return None
    
    def _lookup_openfoodfacts(self, barcode):
        """Lookup using Open Food Facts API"""
        try:
            response = requests.get(
                f"{self.openfoodfacts_url}/{barcode}.json",
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 1 and data.get('product'):
                    product = data['product']
                    return {
                        'title': product.get('product_name', ''),
                        'description': product.get('generic_name', ''),
                        'brand': product.get('brands', ''),
                        'category': product.get('categories', ''),
                        'images': [product.get('image_url')] if product.get('image_url') else [],
                        'source': 'Open Food Facts'
                    }
        except Exception as e:
            print(f"Open Food Facts lookup failed: {e}")
        
        return None
    
    def download_product_images(self, image_urls, upload_folder):
        """Download product images and return file paths"""
        downloaded_files = []
        
        for i, url in enumerate(image_urls[:3]):  # Limit to 3 images
            if not url:
                continue
                
            try:
                response = requests.get(url, timeout=15)
                if response.status_code == 200:
                    # Get file extension from URL or default to jpg
                    parsed_url = urlparse(url)
                    filename = os.path.basename(parsed_url.path)
                    if not filename or '.' not in filename:
                        filename = f"product_image_{i}.jpg"
                    
                    # Create unique filename
                    unique_filename = f"{uuid.uuid4()}_{secure_filename(filename)}"
                    filepath = os.path.join(upload_folder, unique_filename)
                    
                    # Save the image
                    with open(filepath, 'wb') as f:
                        f.write(response.content)
                    
                    downloaded_files.append({
                        'filename': unique_filename,
                        'original_filename': filename,
                        'file_type': 'photo',
                        'file_path': filepath
                    })
                        
            except Exception as e:
                print(f"Failed to download image {url}: {e}")
                continue
        
        return downloaded_files