import requests
import streamlit as st
import pandas as pd
from typing import Dict, List, Optional

# Access the API key from Streamlit secrets
try:
    API_KEY = st.secrets["datawrapper"]["api_key"]
    # Define the base URL and headers
    BASE_URL = "https://api.datawrapper.de/v3/"
    HEADERS = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }
except Exception as e:
    st.error("Could not find API key in secrets. Please make sure you have set up your .streamlit/secrets.toml file correctly.")
    st.stop()


def fetch_data(url: str) -> Optional[Dict]:
    """Base function for making GET requests to the Datawrapper API."""
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed for URL: {url}")
        st.error(f"Error: {str(e)}")
        if hasattr(e.response, 'text'):
            st.error(f"Response: {e.response.text}")
        return None

def clean_json_data(data: Dict) -> Dict:
    """Clean dictionary by removing NaN values and converting them to None."""
    if not isinstance(data, dict):
        return data
    
    cleaned = {}
    for key, value in data.items():
        if isinstance(value, dict):
            cleaned[key] = clean_json_data(value)
        elif isinstance(value, float) and pd.isna(value):
            cleaned[key] = None
        else:
            cleaned[key] = value
    return cleaned

def make_request(method: str, url: str, json: Optional[Dict] = None) -> Optional[Dict]:
    """Generic function for making requests to the Datawrapper API."""
    try:
        # Clean JSON data before sending
        if json:
            json = clean_json_data(json)
        
        response = requests.request(method, url, headers=HEADERS, json=json)
        response.raise_for_status()
        return response.json() if response.text else None
    except requests.exceptions.RequestException as e:
        st.error(f"{method} request failed for URL: {url}")
        st.error(f"Error: {str(e)}")
        if hasattr(e.response, 'text'):
            st.error(f"Response: {e.response.text}")
        return None

def fetch_chart_metadata_fields(chart_id):
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    if not chart_data:
        return [], {}, {}

    metadata = chart_data.get('metadata', {})
    high_level_properties = metadata.keys()
    
    fields_by_property = {}
    for prop in high_level_properties:
        if isinstance(metadata[prop], dict):
            fields = list(metadata[prop].keys())
            if prop == 'describe':
                fields = [field for field in fields if field != 'notes']  # Exclude 'notes'
                fields = ['print-title' if field == 'title' else field for field in fields]  # Rename 'title' to 'print-title'
            fields_by_property[prop] = fields
    
    grouped_high_level_properties = {
        "High-Level Properties": [
            'file-title', 'publicId', 'language', 'theme', 'authorId', 'createdAt', 
            'externalData', 'forkable', 'forkedFrom', 'id', 'isFork', 'lastEditStep', 
            'lastModifiedAt', 'organizationId', 'publicUrl', 'publicVersion', 
            'publishedAt', 'type', 'folderId', 'author', 'url'
        ]
    }
    
    return high_level_properties, fields_by_property, grouped_high_level_properties

def get_chart_ids_in_folder(folder_id):
    # Use the correct URL structure for fetching charts in a folder
    url = f"{BASE_URL}charts?folderId={folder_id}"
    folder_data = fetch_data(url)
    if folder_data:
        # Extract chart IDs from the response
        return [chart['id'] for chart in folder_data.get('list', [])]
    return []

def get_chart_name(chart_id):
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    return chart_data.get('title', 'Unknown Title') if chart_data else None

def get_folder_name(folder_id):
    folder_data = fetch_data(f"{BASE_URL}folders/{folder_id}")
    return folder_data.get('name', 'Unknown Folder') if folder_data else None

def update_chart_metadata(chart_ids, metadata):
    total_charts = len(chart_ids)
    progress_bar = st.progress(0)
    success_count = 0
    updated_chart_titles = []

    # Initialize a placeholder for the progress text
    progress_text = st.empty()

    for index, chart_id in enumerate(chart_ids):
        st.write(f"Updating chart ID {chart_id} with metadata: {metadata}")
        response = requests.patch(f"{BASE_URL}charts/{chart_id}", headers=HEADERS, json={"metadata": metadata})


        if response.status_code == 200:
            success_count += 1
            chart_data = response.json()
            updated_chart_titles.append(chart_data.get('title', 'Unknown Title'))
            st.write(f"Successfully updated chart {chart_id}")
        else:
            st.error(f"Failed to update chart {chart_id}. Status code: {response.status_code}")
            st.error(response.text)
        
        # Update the progress bar and text
        progress_bar.progress((index + 1) / total_charts)
        progress_text.text(f"Processing chart {index + 1} of {total_charts}")

    st.success(f"Update completed: {success_count}/{total_charts} charts updated successfully.")
    if updated_chart_titles:
        st.write("Updated Charts:")
        for title in updated_chart_titles:
            st.write(f"- {title}")

def republish_charts(chart_ids, chart_titles):
    total_charts = len(chart_ids)
    progress_bar = st.progress(0)
    success_count = 0
    republished_chart_titles = []

    # Initialize a placeholder for the progress text
    progress_text = st.empty()

    for index, chart_id in enumerate(chart_ids):
        response = requests.post(f"{BASE_URL}charts/{chart_id}/publish", headers=HEADERS)
        
        if response.status_code == 200:
            success_count += 1
            republished_chart_titles.append(chart_titles.get(chart_id, 'Unknown Title'))
        else:
            st.error(f"Failed to republish chart {chart_id}. Status code: {response.status_code}")
            st.error(response.text)
        
        # Update the progress bar and text
        progress_bar.progress((index + 1) / total_charts)
        progress_text.text(f"Processing chart {index + 1} of {total_charts}")

    st.success(f"Republish completed: {success_count}/{total_charts} charts republished successfully.")
    if republished_chart_titles:
        st.write("Republished Chart Titles:")
        for title in republished_chart_titles:
            st.write(f"- {title}")

def get_chart_type(chart_id):
    """Get the visualization type of a chart."""
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    return chart_data.get('type') if chart_data else None

def get_relevant_fields(chart_type):
    """Get relevant fields based on chart type."""
    # Common fields for all visualizations
    fields = {
        'Source': {
            'describe.source-name': 'Source Name',
            'describe.source-url': 'Source Link'
        },
        'Publishing': {
            'publish.blocks.share': 'Show Social Media Buttons (true/false)',
            'publish.blocks.download-image': 'Show Download Image Button (true/false)'
        },
        'Text': {
            'describe.intro': 'Chart Description',
            'annotate.notes': 'Footer Notes',
        }
    }
    
    # Add visualization-specific fields
    if chart_type in ['d3-lines', 'd3-bars', 'd3-dot-plot', 'column-chart', 'grouped-column-chart', 'stacked-column-chart', 'd3-area', 'd3-scatter-plot']:
        fields['Chart Range'] = {
            'visualize.custom-range-y': 'Y-Axis Min and Max (e.g., "0,100")',
            'visualize.custom-ticks-y': 'Y-Axis Custom Ticks (e.g., "0,25,50,75,100")',
            'visualize.custom-range-x': 'X-Axis Start and End (e.g., "2010,2020")',
            'visualize.custom-ticks-x': 'X-Axis Custom Ticks (e.g., "2010,2015,2020")'
        }
        # Add number format only for charts
        fields['Text']['describe.number-format'] = 'Number Format Style'
    
    # Add table-specific fields
    elif chart_type == 'tables':  # Changed from 'd3-tables' to 'tables'
        fields['Table'] = {
            'visualize.columns': 'Column Headers (Format: old_name:new_name, e.g., "VC Investment:2024 Value")'
        }
    
    return fields

def validate_chart_data(title: str, description: str, data_source: str) -> tuple[bool, str]:
    """Validate chart data before creation."""
    if not title:
        return False, "Title is required"
    if not description:
        return False, "Description is required"
    if not data_source:
        return False, "Data source is required"
    return True, ""

def create_chart_from_template(template_id: str, title: str, description: str, 
                             data_source: str, folder_id: Optional[str] = None) -> Dict:
    """Creates a new chart using an existing chart as template."""
    result = {
        'success': False,
        'chart_id': None,
        'error': None,
        'details': {}
    }
    
    try:
        # Validate input data
        is_valid, error_message = validate_chart_data(title, description, data_source)
        if not is_valid:
            raise ValueError(error_message)
            
        # Get template chart metadata
        template_data = make_request('GET', f"{BASE_URL}charts/{template_id}")
        if not template_data:
            raise Exception("Failed to fetch template chart data")
        result['details']['template_fetch'] = 'success'
        
        # Prepare new chart data with correct Google Sheet metadata
        new_chart_data = {
            "title": title,
            "type": template_data["type"],
            "folderId": folder_id,
            "metadata": template_data["metadata"]
        }
        
        # Update metadata description and data source configuration
        new_chart_data["metadata"]["describe"]["intro"] = description
        new_chart_data["metadata"]["data"] = {
            "upload-method": "google-spreadsheet",
            "google-spreadsheet": data_source,
            "google-spreadsheet-src": convert_to_csv_url(data_source)
        }
        
        # Create new chart
        create_response = make_request('POST', f"{BASE_URL}charts", json=new_chart_data)
        if not create_response:
            raise Exception("Failed to create new chart")
        
        new_chart_id = create_response["id"]
        result['success'] = True
        result['chart_id'] = new_chart_id
        result['details']['creation'] = 'success'
        result['details']['data_source'] = 'success'
        
    except Exception as e:
        result['error'] = str(e)
    
    return result

def convert_to_csv_url(google_sheet_url: str) -> str:
    """Convert Google Sheet URL to CSV export URL."""
    try:
        # Extract document ID and sheet ID from URL
        if 'spreadsheets/d/' not in google_sheet_url:
            return google_sheet_url
        
        doc_id = google_sheet_url.split('spreadsheets/d/')[1].split('/')[0]
        gid = '0'  # default to first sheet
        
        if 'gid=' in google_sheet_url:
            gid = google_sheet_url.split('gid=')[1].split('&')[0]
        
        # Construct CSV export URL
        return f"https://docs.google.com/spreadsheets/d/{doc_id}/export?format=csv&id={doc_id}&gid={gid}"
    except Exception:
        return google_sheet_url  # Return original URL if conversion fails

def bulk_create_charts(template_id: str, charts_data: pd.DataFrame, 
                      folder_id: Optional[str] = None, 
                      progress_callback=None) -> List[Dict]:
    """Creates multiple charts from a template using data from a DataFrame."""
    results = []
    total = len(charts_data)
    
    # Validate template ID first using global HEADERS
    template_check = requests.get(
        f"{BASE_URL}charts/{template_id}",
        headers=HEADERS  # Use the global HEADERS instead
    )
    
    if template_check.status_code != 200:
        return [{
            'title': row['title'],
            'success': False,
            'error': f"Template chart {template_id} not found or not accessible",
            'chart_id': None
        } for _, row in charts_data.iterrows()]
    
    # Rest of the function remains the same
    for idx, row in charts_data.iterrows():
        if progress_callback:
            progress_callback(idx / total)
            
        result = create_chart_from_template(
            template_id=template_id,
            title=row['title'],
            description=row['description'],
            data_source=row['data_source'],
            folder_id=folder_id
        )
        
        results.append({
            'title': row['title'],
            'success': result['success'],
            'error': result['error'],
            'chart_id': result['chart_id'],
            'details': result.get('details', {})
        })
    
    if progress_callback:
        progress_callback(1.0)
    
    return results
