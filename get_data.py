import requests
import pandas as pd
from datetime import date, timedelta
from dateutil.relativedelta import relativedelta
import numpy as np
import streamlit as st
from fpdf import FPDF
import time

# ==============================
# 1. Historical Data Engine (Cached)
# ==============================
@st.cache_data
def get_historical_data_for_event(lat, lon, start_date, end_date):
    """
    Fetches and combines historical data for a specific date range over the past 20 years.
    Uses the reliable Open-Meteo Historical Weather API.
    """
    all_years_df = []
    
    for i in range(20):
        past_start = start_date - relativedelta(years=i+1)
        past_end = end_date - relativedelta(years=i+1)
        
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": lat, "longitude": lon,
            "start_date": past_start.strftime("%Y-%m-%d"),
            "end_date": past_end.strftime("%Y-%m-%d"),
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max",
            "timezone": "auto"
        }
        
        try:
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if 'daily' in data:
                    all_years_df.append(pd.DataFrame(data['daily']))
            else:
                continue
        except Exception:
            continue

    if not all_years_df: return pd.DataFrame() 
    return pd.concat(all_years_df, ignore_index=True).dropna()

# ==============================
# 2. Simulated Forecast Engine
# ==============================
def simulate_future_forecast(historical_df, start_date, end_date):
    if historical_df.empty: return pd.DataFrame()
    df = historical_df.copy()
    df['date_obj'] = pd.to_datetime(df['time'])
    df['month_day'] = df['date_obj'].dt.strftime('%m-%d')
    daily_avg = df.groupby('month_day').agg(
        {'temperature_2m_max': 'mean', 'temperature_2m_min': 'mean',
         'precipitation_sum': 'mean', 'windspeed_10m_max': 'mean'}
    )
    simulated_dates = pd.date_range(start=start_date, end=end_date)
    forecast_list = []
    for dt in simulated_dates:
        month_day_key = dt.strftime('%m-%d')
        if month_day_key in daily_avg.index:
            avg_stats = daily_avg.loc[month_day_key]
            temp_max = avg_stats['temperature_2m_max'] + np.random.uniform(-2, 2)
            temp_min = avg_stats['temperature_2m_min'] + np.random.uniform(-1.5, 1.5)
            precip = max(0, avg_stats['precipitation_sum'] + np.random.uniform(-1, 5))
            wind = max(0, avg_stats['windspeed_10m_max'] + np.random.uniform(-3, 3))
            forecast_list.append([dt.strftime('%Y-%m-%d'), temp_max, temp_min, precip, wind])
    if not forecast_list: return pd.DataFrame()
    return pd.DataFrame(forecast_list, columns=['Date', 'Max Temp (°C)', 'Min Temp (°C)', 'Rainfall (mm)', 'Wind (km/h)'])

# ==============================
# 3. Immediate Forecast Engine (Cached)
# ==============================
@st.cache_data
def get_immediate_forecast(lat, lon):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {"latitude": lat, "longitude": lon, "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,windspeed_10m_max", "timezone": "auto"}
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            return pd.DataFrame(response.json().get('daily', {}))
    except Exception:
        pass
    return pd.DataFrame()

# ==============================
# 4. Date Advisor Engine
# ==============================
@st.cache_data
def find_best_dates(lat, lon, original_start, original_end, hot_thresh, rain_thresh):
    event_duration = (original_end - original_start).days + 1
    search_start, search_end = original_start - timedelta(days=30), original_start + timedelta(days=30)
    wide_range_df = get_historical_data_for_event(lat, lon, search_start, search_end)
    if wide_range_df.empty: return None, None
    wide_range_df['date_obj'] = pd.to_datetime(wide_range_df['time'])
    wide_range_df['month_day'] = wide_range_df['date_obj'].dt.strftime('%m-%d')
    daily_risks = wide_range_df.groupby('month_day').agg(
        hot_prob=('temperature_2m_max', lambda x: (x > hot_thresh).mean() * 100),
        rain_prob=('precipitation_sum', lambda x: (x > rain_thresh).mean() * 100)
    ).reset_index()
    daily_risks['total_risk'] = daily_risks['hot_prob'] + daily_risks['rain_prob']
    daily_risks['rolling_avg_risk'] = daily_risks['total_risk'].rolling(window=event_duration).mean()
    if not daily_risks['rolling_avg_risk'].dropna().empty:
        best_window_end_idx = daily_risks['rolling_avg_risk'].idxmin()
        best_period_df = daily_risks.iloc[best_window_end_idx - event_duration + 1 : best_window_end_idx + 1]
        start_month_day, end_month_day = best_period_df.iloc[0]['month_day'], best_period_df.iloc[-1]['month_day']
        start_month, start_day = map(int, start_month_day.split('-'))
        end_month, end_day = map(int, end_month_day.split('-'))
        year = original_start.year
        best_start_date = date(year, start_month, start_day)
        best_end_date = date(year, end_month, end_day) if start_month <= end_month else date(year + 1, end_month, end_day)
        return best_start_date, best_end_date
    return None, None

# ==============================
# 5. PDF Report Generator (Complete & Bulletproof)
# ==============================
class PDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, 'Event Weather Risk Comparison Report', 0, 1, 'C')
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

def add_section_to_pdf(pdf, results):
    """Helper function to add a full analysis section for one location to the PDF."""
    country = results['location'].address.split(',')[-1].strip()
    display_name = results['location_input'].title()
    clean_header = f"Analysis for: {display_name} ({country})".encode('latin-1', 'replace').decode('latin-1')
    
    pdf.set_font('Arial', 'B', 16)
    pdf.cell(0, 10, clean_header, ln=True)
    pdf.ln(5)

    # --- Risk Analysis ---
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 8, '1. Historical Risk Analysis', ln=True)
    pdf.set_font('Arial', '', 12)
    risk_text = f"- Chance of a 'Hot' Day (> {results['hot_thresh']} C): {results['hot_prob']:.1f}%\n- Chance of a 'Rainy' Day (> {results['rain_thresh']} mm): {results['rain_prob']:.1f}%"
    pdf.multi_cell(0, 8, risk_text.encode('latin-1', 'replace').decode('latin-1'))
    pdf.set_font('Arial', 'I', 10)
    pdf.cell(0, 8, f"(Analysis based on {results['total_days']} total days from the past 20 years)", ln=True)
    pdf.ln(5)

    # --- Smart Suggestions ---
    if results.get('advice_points'):
        pdf.set_font('Arial', 'B', 14)
        pdf.cell(0, 8, '2. Smart Suggestions', ln=True)
        pdf.set_font('Arial', '', 11)
        for point in results['advice_points']:
            point_cleaned = point.replace("", "").replace("🌧 ", "(Rain) ").replace("🔥 ", "(Heat) ").replace("✅ ", "(OK) ").replace("💡 ", "(Idea) ").replace("⚠", "(Warn)")
            pdf.multi_cell(0, 6, f"- {point_cleaned.encode('latin-1', 'replace').decode('latin-1')}")
        pdf.ln(5)

    # --- Simulated Forecast Table ---
    pdf.set_font('Arial', 'B', 14)
    pdf.cell(0, 8, '3. Simulated Daily Forecast for Your Event', ln=True)
    sim_df = results.get('sim_df')
    if sim_df is not None and not sim_df.empty:
        pdf.set_font('Arial', 'B', 9)
        col_widths = [28, 32, 32, 32, 32]
        for i, col in enumerate(sim_df.columns):
            pdf.cell(col_widths[i], 8, col, 1, 0, 'C')
        pdf.ln()
        pdf.set_font('Arial', '', 8)
        for _, row in sim_df.iterrows():
            pdf.cell(col_widths[0], 8, str(row.iloc[0]), 1)
            pdf.cell(col_widths[1], 8, f"{row.iloc[1]:.1f}", 1, 0, 'C')
            pdf.cell(col_widths[2], 8, f"{row.iloc[2]:.1f}", 1, 0, 'C')
            pdf.cell(col_widths[3], 8, f"{row.iloc[3]:.1f}", 1, 0, 'C')
            pdf.cell(col_widths[4], 8, f"{row.iloc[4]:.1f}", 1, 0, 'C')
            pdf.ln()
    else:
        pdf.set_font('Arial', '', 12)
        pdf.cell(0, 10, "No simulated forecast data available.", ln=True)
    pdf.ln(10)

def generate_pdf_report(original_results, comparison_results=None):
    pdf = PDF()
    pdf.add_page()
    if original_results: add_section_to_pdf(pdf, original_results)
    if comparison_results:
        pdf.add_page()
        add_section_to_pdf(pdf, comparison_results)
    
    pdf_content = pdf.output(dest='S')
    return pdf_content.encode('latin-1') if isinstance(pdf_content, str) else bytes(pdf_content)
