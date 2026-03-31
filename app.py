import streamlit as st
from datawrapper_api import (
    update_chart_metadata,
    get_chart_ids_in_folder_recursive,
    republish_charts,
    fetch_chart_metadata_fields,
    get_chart_name,
    get_folder_name,
    get_chart_type,
    get_relevant_fields,
    get_line_customization_strings,
    bulk_create_charts,
    fetch_data,
    BASE_URL,
)
from io import StringIO
import pandas as pd

def display_chart_and_folder_names(chart_ids, folder_ids):
    if chart_ids:
        chart_names = [get_chart_name(chart_id) for chart_id in chart_ids]
        st.write("Selected Charts:")
        for name in chart_names:
            st.write(f"- {name}")

    if folder_ids:
        folder_names = [get_folder_name(folder_id) for folder_id in folder_ids]
        st.write("Selected All Charts in Folder(s):")
        for name in folder_names:
            st.write(f"- {name}")

def get_all_chart_ids(chart_ids_input, folder_ids_input):
    chart_ids = [chart_id.strip() for chart_id in chart_ids_input.split(',') if chart_id.strip()]
    folder_ids = [folder_id.strip() for folder_id in folder_ids_input.split(',') if folder_id.strip()]
    all_chart_ids = list(chart_ids)
    for folder_id in folder_ids:
        folder_chart_ids = get_chart_ids_in_folder_recursive(folder_id)
        all_chart_ids.extend(folder_chart_ids)
    return all_chart_ids

def prepare_metadata_update(metadata_inputs):
    metadata_update = {}
    for key, value in metadata_inputs.items():
        # Split the key into parts
        parts = key.split('.')
        
        # Start with the top level of the metadata dictionary
        current_dict = metadata_update
        
        # Navigate through all parts except the last one
        for part in parts[:-1]:
            if part not in current_dict:
                current_dict[part] = {}
            current_dict = current_dict[part]
        
        # Handle special cases
        if parts[-1] in ['custom-range-x', 'custom-range-y']:
            if value:  # only if value is not empty
                start, end = value.split(',')
                value = [start.strip(), end.strip()]
        elif parts[-1] == 'custom-ticks-x' or parts[-1] == 'custom-ticks-y':
            if value:
                value = ','.join(x.strip() for x in value.split(','))
        elif parts[-1] in ['share', 'download-image']:
            value = value.lower() == 'true'
        elif parts[-1] == 'columns':
            try:
                if value:
                    columns = {}
                    for pair in value.split(','):
                        old_name, new_name = pair.strip().split(':')
                        columns[old_name.strip()] = {
                            "title": new_name.strip()
                        }
                    value = columns
            except Exception as e:
                st.error(f"Error parsing column headers: {e}")
                st.error("Format should be: old_column_name:new_name, e.g., 'VC Investment:2024 Value'")
                return None
        elif key == 'visualize.color-category.map':
            try:
                if value:
                    color_map = {}
                    for pair in value.split(','):
                        series, color = pair.strip().rsplit(':', 1)
                        color_map[series.strip()] = color.strip()
                    value = color_map
            except Exception as e:
                st.error(f"Error parsing line colors: {e}")
                st.error("Format should be: Series A:#ff0000, Series B:#0000ff")
                return None
        elif key == 'visualize.lines':
            try:
                if value:
                    lines = {}
                    for pair in value.split(','):
                        series, width = pair.strip().rsplit(':', 1)
                        lines[series.strip()] = {"width": width.strip()}
                    value = lines
            except Exception as e:
                st.error(f"Error parsing line widths: {e}")
                st.error("Format should be: Series A:style1, Series B:style2")
                return None
            
        # Set the value at the final level
        current_dict[parts[-1]] = value
    
    return metadata_update

def validate_and_display_chart(chart_id: str) -> dict:
    """Validates a chart ID and displays its details in the UI."""
    chart_data = fetch_data(f"{BASE_URL}charts/{chart_id}")
    if chart_data:
        st.success(f"✅ Chart found: {chart_data.get('title')}")
        
        # Show chart details in expander
        with st.expander("Chart Details"):
            st.write("**Chart Type:** ", chart_data.get('type'))
            st.write("**Created:** ", chart_data.get('createdAt'))
            st.write("**Last Modified:** ", chart_data.get('lastModifiedAt'))
            
            # Show metadata
            if 'metadata' in chart_data:
                st.write("**Current Metadata:**")
                st.json(chart_data['metadata'].get('describe', {}))
        return chart_data
    else:
        st.error("❌ Chart not found or not accessible")
        return None

def validate_and_display_folder(folder_id: str) -> dict:
    """Validates a folder ID and displays its details in the UI."""
    folder_data = fetch_data(f"{BASE_URL}folders/{folder_id}")
    if folder_data:
        st.success(f"✅ Folder found: {folder_data.get('name')}")
        return folder_data
    else:
        st.error("❌ Folder not found or not accessible")
        return None

def validate_csv_data(df: pd.DataFrame) -> tuple[bool, str]:
    """Validate CSV data before processing."""
    required_columns = ['title', 'description', 'data_source']
    
    # Check for required columns
    if not all(col in df.columns for col in required_columns):
        return False, f"CSV must contain columns: {', '.join(required_columns)}"
    
    # Check for empty values
    for col in required_columns:
        if df[col].isna().any():
            return False, f"Column '{col}' contains empty values"
    
    return True, ""

def main():
    st.title("Datawrapper Chart Manager")

    # Create tabs with the new Link Remover tab
    tab1, tab2, tab3 = st.tabs(["Update Charts", "Create Charts", "Link Remover"])
    
    with tab1:
        st.header("Update Existing Charts")
        
        # Instructions in expander
        with st.expander("How to Update Charts"):
            st.markdown("""
            **Step-by-Step Guide:**
            
            1. **Enter Chart and Folder IDs:**
               - Input chart IDs separated by commas in the "Enter Chart ID(s)" field.
               - Input folder IDs separated by commas in the "Enter Folder ID(s)" field.
            
            2. **Select Properties to Edit:**
               - Choose the properties you want to edit from the multiselect dropdown.
               - Select specific fields within those properties to edit.
            
            3. **Provide Values:**
               - Enter new values for the selected fields.
               - Leave a field empty to delete its current value.
            
            4. **Update or Republish:**
               - Click "Update Charts" to apply changes.
               - Click "Republish Charts" to republish with the current settings.
            
            **Note:** Ensure you have the correct permissions to update or republish charts.
            
            **Useful Links:**
            - [Datawrapper Chart Properties Documentation](https://developer.datawrapper.de/docs/chart-properties)
            """)
        
        chart_ids_input = st.text_input("Enter Chart ID(s) (comma-separated)")
        folder_ids_input = st.text_input("Enter Folder ID(s) (comma-separated)")

        chart_ids = [chart_id.strip() for chart_id in chart_ids_input.split(',') if chart_id.strip()]
        folder_ids = [folder_id.strip() for folder_id in folder_ids_input.split(',') if folder_id.strip()]

        # Validate and display each chart and folder
        valid_charts = []
        valid_folders = []
        
        for chart_id in chart_ids:
            chart_data = validate_and_display_chart(chart_id)
            if chart_data:
                valid_charts.append(chart_id)
                
        for folder_id in folder_ids:
            folder_data = validate_and_display_folder(folder_id)
            if folder_data:
                valid_folders.append(folder_id)

        if valid_charts or valid_folders:
            display_chart_and_folder_names(valid_charts, valid_folders)

            if valid_charts or valid_folders:  # Only show this section if there are inputs
                # Get the first available chart ID from either direct input or folders
                sample_chart_id = None
                if valid_charts:
                    sample_chart_id = valid_charts[0]
                elif valid_folders:
                    for folder_id in valid_folders:
                        folder_chart_ids = get_chart_ids_in_folder_recursive(folder_id)
                        if folder_chart_ids:
                            sample_chart_id = folder_chart_ids[0]
                            break
                
                if not sample_chart_id:
                    st.warning("Please provide at least one chart ID or folder containing charts to see available fields.")
                else:
                    # Get chart type and relevant fields
                    chart_type = get_chart_type(sample_chart_id)
                    if not chart_type:
                        st.error("Could not determine chart type.")
                        return

                    # Get relevant fields based on chart type
                    available_fields = get_relevant_fields(chart_type)
                    
                    # Create a flat list of all field options with their display names
                    field_options = {}
                    for category, fields in available_fields.items():
                        for field_key, display_name in fields.items():
                            # Use the display name as the key and the field_key as the value
                            display_key = f"{display_name} ({category})"
                            field_options[display_key] = field_key

                    # Initialize session state for selected fields and confirm_deletion if not already set
                    if 'selected_fields' not in st.session_state:
                        st.session_state.selected_fields = []
                    if 'confirm_deletion' not in st.session_state:
                        st.session_state.confirm_deletion = False

                    # Show visualization type
                    st.write(f"Visualization Type: {chart_type}")

                    # Copy from chart (line charts only)
                    if chart_type == 'd3-lines':
                        with st.expander("Copy line settings from another chart"):
                            copy_source_id = st.text_input("Source Chart ID", key="copy_source_chart_id")
                            if st.button("Copy Settings") and copy_source_id:
                                colors_str, widths_str = get_line_customization_strings(copy_source_id)
                                if colors_str is not None:
                                    st.session_state['prefill_visualize.color-category.map'] = colors_str
                                    st.session_state['prefill_visualize.lines'] = widths_str
                                    st.success("Settings copied! Select the Customize Lines fields to see them pre-filled.")
                                    st.rerun()

                    # Single multiselect for all available fields
                    selected_field_displays = st.multiselect(
                        "Select fields to edit",
                        options=list(field_options.keys()),
                        default=st.session_state.selected_fields
                    )

                    # Update session state with the selected fields
                    st.session_state.selected_fields = selected_field_displays

                    # Create input fields for selected options
                    metadata_inputs = {}
                    for display_key in st.session_state.selected_fields:
                        field_key = field_options[display_key]
                        # Remove the category from the display name for the input field label
                        display_name = display_key.split(" (")[0]
                        prefill = st.session_state.get(f'prefill_{field_key}', '')
                        metadata_inputs[field_key] = st.text_input(
                            f"Enter value for {display_name}",
                            value=prefill,
                            key=f"input_{field_key}"
                        )

                    # Identify which fields are empty (i.e. slated for deletion)
                    empty_fields = [key for key, value in metadata_inputs.items() if value == ""]

                    # --- Update Charts Logic ---
                    if st.button("Update Charts"):
                        st.write("Update Charts button clicked")
                        st.write(f"Metadata inputs: {metadata_inputs}")
                        st.write(f"Empty fields: {empty_fields}")
                        
                        if empty_fields:
                            # If there are empty fields, warn and ask for confirmation.
                            st.warning("You have selected fields without providing values. This will delete existing values in those fields. Please confirm deletion.")
                            st.session_state.confirm_deletion = True
                        else:
                            # No empty fields: run update immediately.
                            all_chart_ids = get_all_chart_ids(chart_ids_input, folder_ids_input)
                            st.write(f"All chart IDs: {all_chart_ids}")
                            if all_chart_ids:
                                metadata_update = prepare_metadata_update(metadata_inputs)
                                st.write(f"Metadata update: {metadata_update}")
                                update_chart_metadata(all_chart_ids, metadata_update)
                                st.success("Charts updated successfully.")
                            else:
                                st.warning("No valid chart IDs found.")

                    # --- Confirm Deletion Logic ---
                    if st.session_state.confirm_deletion:
                        if st.button("Confirm Deletion"):
                            st.write("Confirm Deletion button clicked")
                            all_chart_ids = get_all_chart_ids(chart_ids_input, folder_ids_input)
                            st.write(f"All chart IDs: {all_chart_ids}")
                            if all_chart_ids:
                                metadata_update = prepare_metadata_update(metadata_inputs)
                                st.write(f"Metadata update: {metadata_update}")
                                update_chart_metadata(all_chart_ids, metadata_update)
                                st.success("Charts updated successfully.")
                            else:
                                st.warning("No valid chart IDs found.")
                            # Reset confirmation state after processing
                            st.session_state.confirm_deletion = False

                    # --- Republish Charts Logic ---
                    if st.button("Republish Charts", key="republish_charts"):
                        all_chart_ids = get_all_chart_ids(chart_ids_input, folder_ids_input)
                        st.write(f"Republish Charts button clicked with IDs: {all_chart_ids}")
                        if all_chart_ids:
                            chart_titles = {chart_id: get_chart_name(chart_id) for chart_id in all_chart_ids}
                            st.write(f"Chart titles: {chart_titles}")
                            republish_charts(all_chart_ids, chart_titles)
                        else:
                            st.warning("No valid chart IDs found.")
        else:
            st.info("Enter valid chart or folder IDs above to start updating charts.")

    with tab2:
        st.header("Create Charts from Template")
        
        # Instructions in expander
        with st.expander("How to Create Charts"):
            st.markdown("""
            **Step-by-Step Guide:**
            
            1. **Select Template Chart:**
               - Enter the ID of an existing chart to use as template.
               - The new charts will inherit all settings from this template.
            
            2. **Choose Target Folder (Optional):**
               - Enter a folder ID where the new charts should be created.
               - Leave empty to create charts in the root folder.
            
            3. **Prepare and Upload CSV:**
               - Create a CSV file with details for each new chart.
               - Required columns: title, description, data_source (use these exact column names in your csv)
               - Make sure all cells contain valid data.
               - URLs should be complete (including https://)
            
            4. **Create Charts:**
               - Review the preview of charts to be created.
               - Click "Create Charts" to generate all charts.
            
            **Note:** The template chart should be properly configured with the desired visualization settings.
            """)
        
        template_id = st.text_input(
            "Template Chart ID",
            help="Enter the ID of the chart you want to use as a template"
        )
        
        # Validate template chart
        template_data = None
        if template_id:
            template_data = validate_and_display_chart(template_id)
            if not template_data:
                st.stop()
        
        target_folder = st.text_input(
            "Target Folder ID (optional)",
            help="Enter the folder ID where new charts should be created"
        )
        
        # Validate target folder
        if target_folder:
            folder_data = validate_and_display_folder(target_folder)
            if not folder_data:
                st.stop()
        
        uploaded_file = st.file_uploader(
            "Upload CSV file with chart details",
            type="csv",
            help="Upload a CSV file containing the details for each chart you want to create"
        )
        
        if uploaded_file is not None:
            try:
                df = pd.read_csv(uploaded_file)
                is_valid, error_message = validate_csv_data(df)
                
                if not is_valid:
                    st.error(error_message)
                    st.stop()
                
                st.write("Preview of charts to be created:")
                st.dataframe(df[['title', 'description', 'data_source']])
                
                if st.button("Create Charts"):
                    progress_bar = st.progress(0)
                    
                    def update_progress(progress):
                        progress_bar.progress(progress)
                    
                    with st.spinner("Creating charts..."):
                        results = bulk_create_charts(
                            template_id=template_id,
                            charts_data=df,
                            folder_id=target_folder if target_folder else None,
                            progress_callback=update_progress
                        )
                    
                    # Show results
                    success_count = sum(1 for r in results if r['success'])
                    if success_count > 0:
                        st.success(f"Successfully created {success_count} out of {len(results)} charts")
                    else:
                        st.error(f"Failed to create any charts ({len(results)} attempted)")
                    
                    # Display results in expandable section
                    with st.expander("See detailed results", expanded=True):
                        for result in results:
                            if result['success']:
                                st.write(f"✅ Created: {result['title']} (ID: {result['chart_id']})")
                                # Display details in columns instead of nested expander
                                if result.get('details'):
                                    col1, col2 = st.columns(2)
                                    with col1:
                                        st.write("**Technical Details:**")
                                    with col2:
                                        st.json(result['details'])
                            else:
                                st.write(f"❌ Failed: {result['title']}")
                                if result.get('error'):
                                    st.error(f"Error: {result['error']}")
                                if result.get('details'):
                                    st.write("**Technical Details:**")
                                    st.json(result['details'])
                            st.divider()
                
            except Exception as e:
                st.error(f"Error reading CSV file: {str(e)}")
                st.exception(e)  # This will show the full traceback

    with tab3:
        st.header("IU Link Versioning Remover")
        
        st.markdown("""
        Click below to access the Guides Link Versioning Remover tool:
        
        [Open IU Link Versioning Remover](https://iu-link-versioning-remover.streamlit.app/)
        
        This tool helps you clean up versioned URLs from the Dealroom Guides / Deep Dives.
        """)

if __name__ == "__main__":
    main()
