import streamlit as st
from datetime import date, timedelta
import pandas as pd
import plotly.express as px
from get_data import get_historical_data_for_event, simulate_future_forecast, get_immediate_forecast, generate_pdf_report, find_best_dates
from geopy.geocoders import Nominatim
import random

# ==============================
# Main Analysis & Callback Logic
# ==============================
def run_analysis(location_name):
    """A centralized function to run the full analysis for a given location name."""
    with st.spinner(f"Analyzing {location_name}..."):
        geolocator = Nominatim(user_agent="weather_risk_app_pro")
        location = geolocator.geocode(location_name, timeout=10)
        
        if not location:
            st.error(f"Location not found: {location_name}. Please try again.")
            st.session_state.analysis_done = False
            return

        # Fetch all data
        hist_df = get_historical_data_for_event(location.latitude, location.longitude, st.session_state.event_start, st.session_state.event_end)
        sim_df = simulate_future_forecast(hist_df, st.session_state.event_start, st.session_state.event_end)
        imm_df = get_immediate_forecast(location.latitude, location.longitude)
        
        # Calculate risk probabilities
        hot_prob, rain_prob, total_days, advice_points = 0, 0, 0, []
        if not hist_df.empty:
            total_days = len(hist_df)
            hot_days = (hist_df["temperature_2m_max"] > st.session_state.hot_thresh).sum()
            rainy_days = (hist_df["precipitation_sum"] > st.session_state.rain_thresh).sum()
            hot_prob = (hot_days / total_days) * 100 if total_days > 0 else 0
            rain_prob = (rainy_days / total_days) * 100 if total_days > 0 else 0

        # Store results in a dictionary
        results = {
            "location_input": location_name,
            "location": location,
            "hist_df": hist_df, "sim_df": sim_df, "imm_df": imm_df,
            "hot_prob": hot_prob, "rain_prob": rain_prob, "total_days": total_days,
            "hot_thresh": st.session_state.hot_thresh, "rain_thresh": st.session_state.rain_thresh,
            "advice_points": advice_points # Initialize empty
        }
        return results

def analyze_new_location_callback(new_loc_name):
    """Callback for the suggestion button. Runs analysis and stores results in comparison slot."""
    results = run_analysis(new_loc_name)
    if results:
        st.session_state.comparison_results = results
        st.session_state.current_results = results
        st.session_state.location_input = new_loc_name

# ==============================
# Main App UI
# ==============================
st.set_page_config(page_title="Event Weather Forecaster", layout="wide")

# --- Initialize Session State ---
if "analysis_done" not in st.session_state: st.session_state.analysis_done = False
if "location_input" not in st.session_state: st.session_state.location_input = ""
if "original_results" not in st.session_state: st.session_state.original_results = None
if "comparison_results" not in st.session_state: st.session_state.comparison_results = None
if "current_results" not in st.session_state: st.session_state.current_results = None


# --- HEADER ---
st.title("🛰 Event Weather Risk Forecaster")
st.markdown("Analyze historical weather risk, get a simulated daily forecast for your future event, and see the immediate real-time forecast.")

# --- INPUT FORM ---
with st.container(border=True):
    st.header("1. Describe Your Future Event")
    col1, col2 = st.columns(2)
    with col1:
        location_input = st.text_input("Enter Event Location (e.g., Kothamangalam, Paris, Tokyo):", key="location_input")
        event_start = st.date_input("Event Start Date:", date.today() + timedelta(days=90))
    with col2:
        event_end = st.date_input("Event End Date:", date.today() + timedelta(days=92))

    if st.button("Analyze Event Weather", type="primary"):
        if not st.session_state.location_input:
            st.warning("Please enter a location.")
        elif event_start > event_end:
            st.error("Error: The event start date must be before the end date.")
        else:
            # Set fixed thresholds here
            st.session_state.hot_thresh = 32
            st.session_state.rain_thresh = 10
            
            st.session_state.event_start = event_start
            st.session_state.event_end = event_end

            results = run_analysis(st.session_state.location_input)
            if results:
                st.session_state.original_results = results
                st.session_state.current_results = results
                st.session_state.comparison_results = None
                st.session_state.analysis_done = True
                st.success("Analysis Complete!")

# --- RESULTS DASHBOARD (RESTRUCTURED FOR BULLETPROOF LOGIC) ---
if st.session_state.analysis_done and st.session_state.current_results:
    res = st.session_state.current_results
    
    country = res['location'].address.split(',')[-1].strip()
    display_name = res['location_input'].title()
    clean_header = f"Weather Insights for: {display_name} ({country})"
    st.header(clean_header)
    
    # --- 2. HISTORICAL RISK ANALYSIS ---
    st.subheader("2. Historical Risk Analysis")
    if not res['hist_df'].empty:
        col1_res, col2_res = st.columns(2)
        with col1_res:
            st.metric("Chance of a 'Hot' Day", f"{res['hot_prob']:.1f}%", help=f"Based on a threshold of >{res['hot_thresh']}°C")
        with col2_res:
            st.metric("Chance of a 'Rainy' Day", f"{res['rain_prob']:.1f}%", help=f"Based on a threshold of >{res['rain_thresh']} mm/day")
        st.caption(f"Analysis based on {res['total_days']} total days of data from the past 20 years.")

        # --- 3. FUTURE WEATHER OUTLOOK ---
        st.subheader("3. Future Weather Outlook")
        tab1, tab2 = st.tabs(["Simulated Forecast for Your Event", "Immediate Forecast (Real-time)"])
        with tab1:
            st.markdown(f"##### Simulated Daily Forecast for Your Event ({st.session_state.event_start.strftime('%B %Y')})")
            if not res['sim_df'].empty:
                st.dataframe(res['sim_df'])
            else:
                st.warning("Could not generate a simulated forecast.")
        with tab2:
            st.markdown("##### Immediate 16-Day Forecast")
            if not res['imm_df'].empty:
                st.dataframe(res['imm_df'])
            else:
                st.warning("Could not retrieve the immediate forecast.")
        
        # --- 4. SMART REGIONAL SUGGESTIONS ---
        st.subheader("4. Smart Regional Suggestions")
        advice_points = []
        rain_prob = res.get('rain_prob', 0)
        hot_prob = res.get('hot_prob', 0)

        if rain_prob > 50 or hot_prob > 50:
            is_high_risk = True
        elif rain_prob > 20 or hot_prob > 20:
            is_high_risk = False
            message = "⚠ *Moderate Risk:* Be aware of potential adverse weather. It is advisable to have a backup plan."
            advice_points.append(message)
            st.info(message)
        else:
            is_high_risk = False
            message = "✅ *Good Conditions Expected:* Your selected location and dates have a low historical risk of adverse weather."
            advice_points.append(message)
            st.success(message)

        if is_high_risk:
            # Date suggestion logic
            with st.spinner("Searching for better dates..."):
                 best_start, best_end = find_best_dates(res['location'].latitude, res['location'].longitude, st.session_state.event_start, st.session_state.event_end, res['hot_thresh'], res['rain_thresh'])
            if best_start and best_start.strftime('%Y-%m-%d') != st.session_state.event_start.strftime('%Y-%m-%d'):
                advice = f"Date Suggestion: If you wish to stay in {display_name}, the period from {best_start.strftime('%B %d')} to {best_end.strftime('%B %d')} has a historically lower weather risk."
                advice_points.append(advice)
                st.info(f"💡 {advice}")

            # Location suggestion logic
            suggested_locations = []
            address = res['location'].address
            country = address.split(',')[-1].strip()
            cooler_south_india = ["Munnar, Kerala", "Ooty, Tamil Nadu", "Kodaikanal, Tamil Nadu"]
            cooler_north_india = ["Shimla, Himachal Pradesh", "Manali, Himachal Pradesh", "Nainital, Uttarakhand"]
            drier_india = ["Jaisalmer, Rajasthan", "Leh, Ladakh", "Pune, Maharashtra"]
            cooler_international = ["Zurich, Switzerland", "Vancouver, Canada", "Oslo, Norway"]
            drier_international = ["Dubai, UAE", "Cairo, Egypt", "Lima, Peru"]

            if res['rain_prob'] > 50:
                source_list = drier_india if country == "India" else drier_international
                num_suggestions = min(3, len(source_list))
                suggested_locations = random.sample(source_list, num_suggestions)
                st.warning(f"🌧 *High Rain Risk:* With a {res['rain_prob']:.0f}% chance of rainy conditions, you might want to consider some drier destinations.")
            elif res['hot_prob'] > 50:
                if country == "India":
                    if any(state in address for state in ["Kerala", "Tamil Nadu", "Karnataka", "Andhra Pradesh", "Telangana"]):
                        source_list = cooler_south_india
                    else:
                        source_list = cooler_north_india
                else:
                    source_list = cooler_international
                num_suggestions = min(3, len(source_list))
                suggested_locations = random.sample(source_list, num_suggestions)
                st.warning(f"🔥 *High Heat Risk:* There's a {res['hot_prob']:.0f}% chance of hot weather. You could explore some cooler, nearby alternatives.")
            
            if suggested_locations:
                st.markdown("##### Click a location to analyze it instead:")
                for i, loc in enumerate(suggested_locations):
                    st.button(loc, on_click=analyze_new_location_callback, args=[loc], key=f"suggestion_btn_{i}")


        res['advice_points'] = advice_points # Save advice for PDF

        # --- 5. DOWNLOAD YOUR REPORT ---
        st.subheader("5. Download Your Report")
        original_results = st.session_state.original_results
        comparison_results = st.session_state.comparison_results
        
        # Add generated advice points to the results dictionaries for the PDF
        original_results['advice_points'] = advice_points
        if comparison_results:
            # We don't generate new advice for comparison, so just pass an empty list
            comparison_results['advice_points'] = []

        pdf_data = generate_pdf_report(original_results, comparison_results)
        
        # Prepare CSV data
        orig_df = original_results['hist_df'].copy()
        orig_df['Location'] = original_results['location_input'].title()
        csv_parts = [orig_df]
        if comparison_results:
            comp_df = comparison_results['hist_df'].copy()
            comp_df['Location'] = comparison_results['location_input'].title()
            csv_parts.append(comp_df)
        
        # Append advice and simulated forecast to CSV string
        csv_string = pd.concat(csv_parts).to_csv(index=False)
        if not original_results['sim_df'].empty:
            csv_string += "\n\n--- Simulated Forecast for Your Event ---\n"
            csv_string += original_results['sim_df'].to_csv(index=False)
        if advice_points:
            csv_string += "\n\n--- Smart Suggestions & Travel Advice ---\n"
            for point in advice_points:
                csv_string += f"- {point.replace('', '')}\n"

        csv_data = csv_string.encode('utf-8')
        
        st.download_button("📄 Download Data (CSV)", csv_data, f"weather_comparison_data.csv", "text/csv")
        st.download_button("📑 Download Report (PDF)", pdf_data, f"weather_comparison_report.pdf", "application/pdf")

    else:
        st.error("Could not retrieve any historical data for this location and date range. The analysis cannot be completed.")