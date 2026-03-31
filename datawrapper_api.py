import requests
import streamlit as st
import pandas as pd
import time
from typing import Dict, List, Optional

# Rate limiting and retry configuration
REQUEST_DELAY = 0.3    # seconds between individual requests
BATCH_SIZE = 10        # charts per batch before a longer pause
BATCH_DELAY = 2        # seconds between batches
MAX_RETRIES = 3        # retry attempts per request
REQUEST_TIMEOUT = 30   # seconds before a single request times out

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
        response = requests.get(url, headers=HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Request failed for URL: {url}")
        st.error(f"Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
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

        response = requests.request(method, url, headers=HEADERS, json=json, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return response.json() if response.text else None
    except requests.exceptions.RequestException as e:
        st.error(f"{method} request failed for URL: {url}")
        st.error(f"Error: {str(e)}")
        if hasattr(e, 'response') and e.response is not None:
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

def get_chart_ids_in_folder(folder_id: str) -> List[str]:
    """Get all chart IDs directly inside a folder (non-recursive)."""
    url = f"{BASE_URL}charts?folderId={folder_id}"
    folder_data = fetch_data(url)
    if folder_data:
        return [chart['id'] for chart in folder_data.get('list', [])]
    return []

def get_all_subfolders(folder_id: str) -> List[str]:
    """Recursively get all subfolder IDs under a given folder.

    Tries two strategies:
    1. GET /folders/{id} — if the response includes a nested `folders` list.
    2. GET /folders       — flat list filtered by `parentId` (fallback).
    """
    folder_data = fetch_data(f"{BASE_URL}folders/{folder_id}")
    if folder_data:
        nested = folder_data.get('folders', [])
        if nested:
            result = []
            for subfolder in nested:
                sub_id = str(subfolder.get('id', ''))
                if sub_id:
                    result.append(sub_id)
                    result.extend(get_all_subfolders(sub_id))
            return result

    # Fallback: fetch all folders and filter by parentId
    all_folders_data = fetch_data(f"{BASE_URL}folders")
    if not all_folders_data:
        return []

    folder_list = all_folders_data.get('list', [])

    def collect_children(parent_id: str) -> List[str]:
        children = []
        for folder in folder_list:
            if str(folder.get('parentId', '')) == str(parent_id):
                child_id = str(folder['id'])
                children.append(child_id)
                children.extend(collect_children(child_id))
        return children

    return collect_children(str(folder_id))

def get_chart_ids_in_folder_recursive(folder_id: str) -> List[str]:
    """Get all chart IDs from a folder and all its subfolders."""
    all_chart_ids = get_chart_ids_in_folder(folder_id)
    for subfolder_id in get_all_subfolders(folder_id):
        all_chart_ids.extend(get_chart_ids_in_folder(subfolder_id))
    return all_chart_ids

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
    failed_count = 0
    updated_chart_titles = []
    progress_text = st.empty()
    status_text = st.empty()

    for index, chart_id in enumerate(chart_ids):
        # Delay between requests to avoid rate limiting
        if index > 0:
            time.sleep(REQUEST_DELAY)

        # Extra pause between batches
        if index > 0 and index % BATCH_SIZE == 0:
            status_text.text(f"Pausing between batches ({index}/{total_charts} done)...")
            time.sleep(BATCH_DELAY)

        progress_text.text(f"Updating chart {index + 1} of {total_charts} (ID: {chart_id})")

        response = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.patch(
                    f"{BASE_URL}charts/{chart_id}",
                    headers=HEADERS,
                    json=clean_json_data({"metadata": metadata}),
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 429:
                    wait_time = 5 * (2 ** attempt)
                    status_text.text(f"Rate limited. Waiting {wait_time}s before retrying...")
                    time.sleep(wait_time)
                    continue
                response = resp
                break
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                status_text.text(f"Chart {chart_id} timed out, moving on.")
                break
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                st.error(f"Request error for chart {chart_id}: {str(e)}")
                break

        if response is not None and response.status_code == 200:
            success_count += 1
            updated_chart_titles.append(response.json().get('title', 'Unknown Title'))
        else:
            failed_count += 1
            if response is not None:
                st.error(f"Failed to update chart {chart_id}. Status: {response.status_code}")
            else:
                st.warning(f"Skipped chart {chart_id} after {MAX_RETRIES} failed attempts.")

        progress_bar.progress((index + 1) / total_charts)

    status_text.empty()
    st.success(f"Update completed: {success_count}/{total_charts} charts updated successfully.")
    if failed_count > 0:
        st.warning(f"{failed_count} charts failed to update.")
    if updated_chart_titles:
        st.write("Updated Charts:")
        for title in updated_chart_titles:
            st.write(f"- {title}")

def republish_charts(chart_ids, chart_titles):
    total_charts = len(chart_ids)
    progress_bar = st.progress(0)
    success_count = 0
    failed_count = 0
    republished_chart_titles = []
    progress_text = st.empty()
    status_text = st.empty()

    for index, chart_id in enumerate(chart_ids):
        if index > 0:
            time.sleep(REQUEST_DELAY)

        if index > 0 and index % BATCH_SIZE == 0:
            status_text.text(f"Pausing between batches ({index}/{total_charts} done)...")
            time.sleep(BATCH_DELAY)

        progress_text.text(f"Republishing chart {index + 1} of {total_charts} (ID: {chart_id})")

        response = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.post(
                    f"{BASE_URL}charts/{chart_id}/publish",
                    headers=HEADERS,
                    timeout=REQUEST_TIMEOUT,
                )
                if resp.status_code == 429:
                    wait_time = 5 * (2 ** attempt)
                    status_text.text(f"Rate limited. Waiting {wait_time}s before retrying...")
                    time.sleep(wait_time)
                    continue
                response = resp
                break
            except requests.exceptions.Timeout:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                status_text.text(f"Chart {chart_id} timed out, moving on.")
                break
            except requests.exceptions.RequestException as e:
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt)
                    continue
                st.error(f"Request error for chart {chart_id}: {str(e)}")
                break

        if response is not None and response.status_code == 200:
            success_count += 1
            republished_chart_titles.append(chart_titles.get(chart_id, 'Unknown Title'))
        else:
            failed_count += 1
            if response is not None:
                st.error(f"Failed to republish chart {chart_id}. Status: {response.status_code}")
            else:
                st.warning(f"Skipped chart {chart_id} after {MAX_RETRIES} failed attempts.")

        progress_bar.progress((index + 1) / total_charts)

    status_text.empty()
    st.success(f"Republish completed: {success_count}/{total_charts} charts republished successfully.")
    if failed_count > 0:
        st.warning(f"{failed_count} charts failed to republish.")
    if republished_chart_titles:
        st.write("Republished Chart Titles:")
        for title in republished_chart_titles:
            st.write(f"- {title}")

def get_chart_type(chart_id):
    """Get the visualization type of a chart."""
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    return chart_data.get('type') if chart_data else None

def get_line_customization_strings(chart_id):
    """Fetch a chart's line colors and widths formatted as UI input strings.

    Returns (colors_str, widths_str) where:
      colors_str: "Series A:#ff0000, Series B:#0000ff"
      widths_str: "Series A:style1, Series B:style2"
    """
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    if not chart_data:
        return None, None

    visualize = chart_data.get('metadata', {}).get('visualize', {})

    color_map = visualize.get('color-category', {}).get('map', {})
    colors_str = ', '.join(f"{s}:{c}" for s, c in color_map.items()) if color_map else ''

    lines = visualize.get('lines', {})
    widths_str = ', '.join(
        f"{s}:{props['width']}"
        for s, props in lines.items()
        if isinstance(props, dict) and 'width' in props
    ) if lines else ''

    return colors_str, widths_str

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

    if chart_type == 'd3-lines':
        fields['Customize Lines'] = {
            'visualize.color-category.map': 'Line Colors (e.g., "Series A:#ff0000, Series B:#0000ff")',
            'visualize.lines': 'Line Widths (e.g., "Series A:style1, Series B:style2" — style1=thin, style2=thick)',
        }
    
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
