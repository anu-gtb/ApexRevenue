from flask import Flask, jsonify, request
from flask_cors import CORS
import pandas as pd
from sqlalchemy import create_engine
import traceback
import os

app = Flask(__name__)
CORS(app)

# --- UPDATED DATABASE URI PATH LOGIC ---
if os.path.exists('/app/data'):
    # Path inside Kubernetes using your persistent volume mount folder
    DB_URI = 'sqlite:////app/data/data.sqlite'
elif os.path.exists('/app'):
    # Standard container path if volume is detached
    DB_URI = 'sqlite:////app/data.sqlite'
else:
    # Original fallback path for your local Windows laptop machine
    DB_URI = r'sqlite:///C:/Users/DELL/Documents/PBI_assignment2/data.sqlite'

engine = create_engine(DB_URI)

@app.route('/api/sales-data', methods=['GET'])
def get_sales_data():
    try:
        # Retrieve optional filter arguments from query parameters
        selected_year = request.args.get('year', 'all')
        selected_category = request.args.get('category', 'all')

        base_query = "SELECT CAST(s.Year_col AS TEXT) as calendar_year,s.OrderDate as order_date,CAST(s.OrderQuantity AS INTEGER) AS order_quantity, CAST(p.ProductPrice AS REAL) AS product_price,cat.SubcategoryName as category_name,p.ProductName FROM sales_data s JOIN adventureworksproductlookup p ON s.ProductKey = p.ProductKey JOIN adventureworksproductsubcategorieslookup cat ON p.ProductSubcategoryKey = cat.ProductSubcategoryKey"
        
        with engine.connect() as connection:
           df = pd.read_sql(base_query, con=connection)
           print(f"DataFrame Shape after read_sql: {df.shape}")
        
        if df.empty:
            return jsonify({"status": "success", "kpis": {"total_sales": 0, "total_orders": 0}, "annual_sales_summary": [], "category_distribution": [], "monthly_breakdown": [], "filter_options": {"years": [], "categories": []}, "drill_down_data": []}), 200
        
        df['order_quantity'] = pd.to_numeric(df['order_quantity'], errors='coerce').fillna(0)
        df['product_price'] = pd.to_numeric(df['product_price'], errors='coerce').fillna(0.0)

        # Data cleaning and calculations
        df['category_name'] = df['category_name'].fillna('Uncategorized').astype(str).str.strip()
        df['calendar_year'] = df['calendar_year'].astype(str).str.strip()
        df['total_sales'] = df['order_quantity'] * df['product_price']

        # Extract available filter options before applying filters
        available_years = sorted(df['calendar_year'].unique().tolist())
        available_categories = sorted(df['category_name'].unique().tolist())

        # Apply Slicer / Filter logic
        filtered_df = df.copy()
        if selected_year != 'all':
            filtered_df = filtered_df[filtered_df['calendar_year'] == str(selected_year)]
        if selected_category != 'all':
            filtered_df = filtered_df[filtered_df['category_name'] == str(selected_category)]

        # KPI calculations based on filtered dataset
        total_sales = float(filtered_df['total_sales'].sum()) if not filtered_df.empty else 0.0
        total_orders = int(filtered_df['order_quantity'].sum()) if not filtered_df.empty else 0

        # Aggregations for charts
        annual_df = filtered_df.groupby('calendar_year').agg(
            total_sales=('total_sales', 'sum'),
            total_orders=('order_quantity', 'sum')
        ).reset_index().to_dict(orient='records')

        cat_df = filtered_df.groupby('category_name').agg(
            sales_amount=('total_sales', 'sum')
        ).reset_index().to_dict(orient='records')

        filtered_df['order_date'] = pd.to_datetime(filtered_df['order_date'], errors='coerce')
        filtered_df['month'] = filtered_df['order_date'].dt.strftime('%b')
        monthly_df = filtered_df.dropna(subset=['month']).groupby('month').agg(
            total_sales=('total_sales', 'sum')
        ).reset_index().to_dict(orient='records')

        # Drill-down summary (e.g., sales grouped by product name for detailed inspection)
        drill_df = filtered_df.groupby('ProductName').agg(
            total_sales=('total_sales', 'sum'),
            total_orders=('order_quantity', 'sum')
        ).reset_index().sort_values(by='total_sales', ascending=False).head(15).to_dict(orient='records')

        payload = {
            "status": "success",
            "kpis": {
                "total_sales": total_sales,
                "total_orders": total_orders
            },
            "annual_sales_summary": annual_df,
            "category_distribution": cat_df,
            "monthly_breakdown": monthly_df,
            "filter_options": {
                "years": available_years,
                "categories": available_categories
            },
            "drill_down_data": drill_df
        }

        return jsonify(payload), 200

    except Exception as e:
        print("--- ERROR OCCURRED ---")
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)