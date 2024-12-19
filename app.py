# File: app.py
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2

# Load dataset
@st.cache_data
def load_data():
    file_path = "/Users/GeoTarget/streamlit_app/TerritoryList.xlsx"  # Update with your file path
    spreadsheet = pd.ExcelFile(file_path)
    data = spreadsheet.parse(sheet_name=spreadsheet.sheet_names[0])
    
    if 'Date Assigned to Rep' in data.columns:
        data['Date Assigned to Rep'] = pd.to_datetime(data['Date Assigned to Rep'], errors='coerce')
    if 'Sale Entry Date' in data.columns:
        data['Sale Entry Date'] = pd.to_datetime(data['Sale Entry Date'], errors='coerce')
    
    return data

# Assign flags based on conditions
def assign_flags(data):
    today = datetime.today()
    flags = []
    for _, row in data.iterrows():
        assigned_date = row.get("Date Assigned to Rep")
        deal_date = row.get("Sale Entry Date")
        deals = row.get("Deals", 0)
        rep_assigned = row.get("Rep Assigned")

        if pd.notna(assigned_date):
            days_since_assigned = (today - assigned_date).days
            if days_since_assigned <= 210:
                flags.append("Blue")  # Assigned within 7 months
            elif 210 < days_since_assigned <= 270:
                flags.append("Orange")  # Assigned 7-9 months ago
            elif days_since_assigned > 270 and deals == 0:
                flags.append("Red")  # Assigned 9+ months ago with no deals
            else:
                flags.append("Black")  # Assigned Other
        elif pd.notna(rep_assigned):
            flags.append("Black")  # Assigned Other
        else:
            flags.append("Purple")  # Available unassigned cities
    data["Flag"] = flags
    return data

# Haversine formula to calculate distance
def haversine(lat1, lon1, lat2, lon2):
    R = 3958.8  # Radius of the Earth in miles
    dlat = radians(lat2 - lat1)
    dlon = radians(lat2 - lon1)
    a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# Identify available cities (unassigned and > 7 miles away from any assigned city)
def find_available_cities(data):
    assigned = data[data["Rep Assigned"].notna()]
    unassigned = data[data["Rep Assigned"].isna()]
    available_cities = []

    for _, unassigned_row in unassigned.iterrows():
        too_close = False
        for _, assigned_row in assigned.iterrows():
            distance = haversine(
                unassigned_row["Latitude"], unassigned_row["Longitude"],
                assigned_row["Latitude"], assigned_row["Longitude"]
            )
            if distance <= 7:  # Distance threshold set to 7 miles
                too_close = True
                break
        if not too_close:
            available_cities.append(unassigned_row)
    
    return pd.DataFrame(available_cities)

# Summarize data by representative
def summarize_by_rep(data):
    summary = data.groupby('Rep Assigned')['Flag'].value_counts().unstack(fill_value=0)
    summary = summary.reindex(columns=["Blue", "Orange", "Red", "Black"], fill_value=0)
    summary['Total'] = summary.sum(axis=1)
    return summary

# Filter data based on state, search, rep, flag, and minimum population
def filter_data(data, states, search_query, selected_rep, selected_flag, min_population):
    filtered_data = data[data["State"].isin(states) & (data["Population"] >= min_population)]
    if search_query:
        filtered_data = filtered_data[
            filtered_data["City"].str.contains(search_query, case=False, na=False) |
            filtered_data["State"].str.contains(search_query, case=False, na=False) |
            filtered_data["Rep Assigned"].astype(str).str.contains(search_query, case=False, na=False)
        ]
    if selected_rep:
        filtered_data = filtered_data[filtered_data["Rep Assigned"] == selected_rep]
    if selected_flag:
        filtered_data = filtered_data[filtered_data["Flag"] == selected_flag]
    return filtered_data

# Create map function
def create_map(data, available_cities, filters):
    clean_data = data.dropna(subset=["Latitude", "Longitude"])
    map_center = [clean_data["Latitude"].mean(), clean_data["Longitude"].mean()]
    m = folium.Map(location=map_center, zoom_start=6)

    # Map custom colors to valid Folium icon colors
    color_mapping = {
        "Blue": "blue",
        "Orange": "orange",
        "Red": "red",
        "Black": "black",
        "Purple": "purple",
    }

    for _, row in clean_data.iterrows():
        flag = row.get("Flag", "Purple")
        if flag in filters:
            popup_info = f"""
            <b>City:</b> {row['City']}<br>
            <b>State:</b> {row['State']}<br>
            <b>Population:</b> {row.get('Population', 'N/A')}<br>
            <b>Rep Assigned:</b> {row.get('Rep Assigned', 'Unassigned')}<br>
            <b>Flag:</b> {row.get('Flag', 'Unknown')}
            """
            marker_color = color_mapping.get(flag, "gray")
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=popup_info,
                icon=folium.Icon(color=marker_color)
            ).add_to(m)

    # Add markers for available cities in purple
    if "Purple" in filters:
        for _, row in available_cities.iterrows():
            popup_info = f"""
            <b>Available City:</b> {row['City']}<br>
            <b>State:</b> {row['State']}<br>
            <b>Population:</b> {row.get('Population', 'N/A')}
            """
            folium.Marker(
                location=[row["Latitude"], row["Longitude"]],
                popup=popup_info,
                icon=folium.Icon(color="purple")
            ).add_to(m)

    return m

# Main app
def main():
    st.title("City Flag Dashboard")
    data = load_data()
    data = assign_flags(data)

    st.sidebar.header("Filters")
    selected_states = st.sidebar.multiselect(
        "Filter by State", 
        options=sorted(data["State"].dropna().unique()),  # Alphabetical order
        default=[]
    )

    search_query = st.sidebar.text_input("Search (City, State, Rep Assigned)", value="")
    min_population = st.sidebar.number_input("Minimum Population", min_value=0, value=10000)

    st.sidebar.subheader("Flag Filters")
    show_blue = st.sidebar.checkbox("Blue (Assigned within 7 months)", value=True)
    show_orange = st.sidebar.checkbox("Orange (Assigned 7-9 months ago)", value=True)
    show_red = st.sidebar.checkbox("Red (Assigned 9+ months ago, 0 deals)", value=True)
    show_black = st.sidebar.checkbox("Black (Assigned Other)", value=True)
    show_purple = st.sidebar.checkbox("Purple (Available unassigned cities > 7 miles from any assigned)", value=True)

    filters = []
    if show_blue: filters.append("Blue")
    if show_orange: filters.append("Orange")
    if show_red: filters.append("Red")
    if show_black: filters.append("Black")
    if show_purple: filters.append("Purple")

    if not selected_states:
        st.warning("Please select at least one state to begin.")
        return

    # Placeholder for selected rep and flag
    if "selected_rep" not in st.session_state:
        st.session_state["selected_rep"] = None
    if "selected_flag" not in st.session_state:
        st.session_state["selected_flag"] = None

    # Interactive summary by representative
    st.header("Summary by Representative")
    summary = summarize_by_rep(data[data["State"].isin(selected_states)])

    def on_cell_click(rep, flag):
        if st.session_state["selected_rep"] == rep and st.session_state["selected_flag"] == flag:
            st.session_state["selected_rep"] = None
            st.session_state["selected_flag"] = None
        else:
            st.session_state["selected_rep"] = rep
            st.session_state["selected_flag"] = flag

    # Render summary as interactive table
    st.dataframe(summary)

    # Filter data based on selections
    filtered_data = filter_data(
        data, selected_states, search_query,
        st.session_state["selected_rep"], st.session_state["selected_flag"], min_population
    )

    # Map View
    st.header("Map View")
    with st.expander("Expand to View Map", expanded=True):
        st_folium(create_map(filtered_data, find_available_cities(filtered_data), filters), width=1400, height=800)

    # Dataset Preview
    st.header("Dataset Preview")
    st.dataframe(filtered_data)

if __name__ == "__main__":
    main()
