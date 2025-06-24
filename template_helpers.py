"""
Template helper functions for safe calculations
"""
from decimal import Decimal


def safe_calculate_totals(items):
    """Calculate totals safely with proper decimal handling"""
    total_quantity = 0
    total_investment = 0.0
    total_revenue = 0.0
    total_net_profit = 0.0
    
    for item in items:
        quantity = item.quantity or 1
        total_quantity += quantity
        
        if item.purchase_cost:
            total_investment += float(item.purchase_cost) * quantity
            
        if item.selling_price:
            total_revenue += float(item.selling_price) * quantity
            
        if item.selling_price and item.purchase_cost:
            selling = float(item.selling_price)
            purchase = float(item.purchase_cost)
            gross = selling - purchase
            overhead = selling * 0.3
            net_per_item = gross - overhead
            total_net_profit += net_per_item * quantity
    
    return {
        'total_quantity': total_quantity,
        'total_investment': total_investment,
        'total_revenue': total_revenue,
        'total_net_profit': total_net_profit
    }


def safe_calculate_item_profit(item):
    """Calculate profit for individual item safely"""
    if not (item.selling_price and item.purchase_cost):
        return 0.0
    
    selling = float(item.selling_price)
    purchase = float(item.purchase_cost)
    gross = selling - purchase
    overhead = selling * 0.3
    return gross - overhead