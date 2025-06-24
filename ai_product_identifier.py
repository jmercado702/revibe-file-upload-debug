import os
import base64
import json
from openai import OpenAI

# the newest OpenAI model is "gpt-4o" which was released May 13, 2024.
# do not change this unless explicitly requested by the user
client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

def identify_product_from_image(image_data):
    """
    Use OpenAI Vision to identify a product from an image and extract relevant details
    """
    try:
        # Convert image data to base64 if it's not already
        if isinstance(image_data, bytes):
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        else:
            image_base64 = image_data

        prompt = """
        You are an expert product identifier for a recycling business. Analyze this image and provide detailed information about the product shown. Focus on identifying:

        1. Product name/title
        2. Brand name
        3. Category (electronics, furniture, appliance, etc.)
        4. Condition assessment (excellent, good, fair, poor)
        5. Material type (plastic, metal, wood, etc.)
        6. Estimated retail price range
        7. Suggested selling price for recycled/used item
        8. Key features and description
        9. Potential issues or damage visible
        10. Marketability assessment

        Please respond in JSON format with the following structure:
        {
            "product_name": "specific product name",
            "brand": "brand name if visible",
            "category": "product category",
            "condition": "condition assessment",
            "material": "primary material",
            "estimated_retail_price": "price range as string",
            "suggested_selling_price": "recommended price for used item",
            "description": "detailed description",
            "features": ["list", "of", "key", "features"],
            "issues": ["list", "of", "visible", "issues"],
            "marketability": "high/medium/low with reasoning",
            "confidence": "high/medium/low"
        }

        If you cannot clearly identify the product, set confidence to "low" and provide your best guess with available information.
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user", 
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=800
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "success": True,
            "product": result,
            "source": "AI Vision Analysis"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"AI analysis failed: {str(e)}",
            "source": "AI Vision Analysis"
        }

def analyze_product_for_recycling(image_data, additional_context=""):
    """
    Specialized analysis for recycling business focusing on material value and resale potential
    """
    try:
        if isinstance(image_data, bytes):
            image_base64 = base64.b64encode(image_data).decode('utf-8')
        else:
            image_base64 = image_data

        prompt = f"""
        As a recycling business expert, analyze this item for its recycling and resale value. {additional_context}

        Provide assessment in JSON format:
        {{
            "item_type": "clear item identification",
            "recycling_value": "high/medium/low with explanation",
            "resale_potential": "excellent/good/fair/poor with reasoning",
            "material_breakdown": ["primary", "secondary", "materials"],
            "estimated_weight": "approximate weight if determinable",
            "space_requirements": "storage space needed",
            "quick_sale_price": "price for quick turnover",
            "optimal_sale_price": "price for maximum profit",
            "target_market": "who would buy this",
            "refurbishment_needed": ["list", "of", "improvements"],
            "selling_points": ["key", "attractive", "features"],
            "challenges": ["potential", "selling", "obstacles"],
            "recommendation": "overall business recommendation"
        }}
        """

        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url", 
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                        }
                    ]
                }
            ],
            response_format={"type": "json_object"},
            max_tokens=600
        )

        result = json.loads(response.choices[0].message.content)
        return {
            "success": True,
            "analysis": result,
            "source": "AI Recycling Analysis"
        }

    except Exception as e:
        return {
            "success": False,
            "message": f"Recycling analysis failed: {str(e)}",
            "source": "AI Recycling Analysis"
        }