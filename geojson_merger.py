import streamlit as st
import json
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, mapping, MultiPolygon, shape
from shapely.ops import unary_union
import folium
from streamlit_folium import folium_static
import io

def detect_file_type(file):
    """Detect if file is JSON/GeoJSON or CSV based on content."""
    try:
        content = file.read()
        file.seek(0)
        
        try:
            content_str = content.decode('utf-8')
            parsed_json = json.loads(content_str)
            if isinstance(parsed_json, dict) and 'type' in parsed_json and 'features' in parsed_json:
                return 'geojson'
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        
        try:
            pd.read_csv(io.BytesIO(content), nrows=1)
            return 'csv'
        except:
            pass
        
        return 'unknown'
    except Exception as e:
        st.error(f"File type detection failed: {str(e)}")
        return 'unknown'

def get_property_values(geojson_data, property_name):
    """Get unique values for a specific property in GeoJSON features."""
    values = set()
    for feature in geojson_data['features']:
        if 'properties' in feature and property_name in feature['properties']:
            values.add(str(feature['properties'][property_name]))
    return sorted(list(values))

def filter_geojson(geojson_data, filters):
    """Filter GeoJSON features based on property values."""
    if not filters:
        return geojson_data

    filtered_features = []
    for feature in geojson_data['features']:
        include_feature = True
        for prop, values in filters.items():
            if not values:  # Skip if no values selected
                continue
            if prop not in feature['properties'] or str(feature['properties'][prop]) not in values:
                include_feature = False
                break
        if include_feature:
            filtered_features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": filtered_features
    }

def validate_geojson(geojson_data):
    """Validate if the uploaded file is a proper GeoJSON."""
    try:
        if not isinstance(geojson_data, dict):
            geojson_data = json.loads(geojson_data)

        required_fields = ['type', 'features']
        if not all(field in geojson_data for field in required_fields):
            return False, "Invalid GeoJSON structure: missing required fields"

        if geojson_data['type'] != 'FeatureCollection':
            return False, "Invalid GeoJSON: root type must be 'FeatureCollection'"

        if not geojson_data['features']:
            return False, "GeoJSON contains no features"

        return True, "Valid GeoJSON"
    except Exception as e:
        return False, f"Invalid GeoJSON: {str(e)}"

def validate_csv_coordinates(df, lat_col, lon_col):
    """Validate if the selected columns contain valid coordinates."""
    try:
        if lat_col not in df.columns or lon_col not in df.columns:
            return False, "Selected columns not found in CSV"
        
        lats = pd.to_numeric(df[lat_col], errors='coerce')
        lons = pd.to_numeric(df[lon_col], errors='coerce')
        
        if lats.isna().all() or lons.isna().all():
            return False, "Selected columns do not contain valid numeric data"
        
        if not ((-90 <= lats) & (lats <= 90)).all():
            return False, "Latitude values must be between -90 and 90"
        
        if not ((-180 <= lons) & (lons <= 180)).all():
            return False, "Longitude values must be between -180 and 180"
        
        return True, "Valid coordinates"
    except Exception as e:
        return False, f"Error validating coordinates: {str(e)}"

def csv_to_geojson(df, lat_col, lon_col):
    """Convert CSV data to GeoJSON format."""
    features = []
    
    df[lat_col] = pd.to_numeric(df[lat_col], errors='coerce')
    df[lon_col] = pd.to_numeric(df[lon_col], errors='coerce')
    
    df = df.dropna(subset=[lat_col, lon_col])

    for idx, row in df.iterrows():
        try:
            point = Point(float(row[lon_col]), float(row[lat_col]))
            
            properties = row.drop([lat_col, lon_col]).to_dict()
            properties = {k: str(v) if pd.notnull(v) else None for k, v in properties.items()}

            feature = {
                "type": "Feature",
                "geometry": mapping(point),
                "properties": properties
            }
            
            features.append(feature)
        except (ValueError, TypeError) as e:
            st.warning(f"Skipping row {idx}: {str(e)}")
            continue

    if not features:
        st.error("No valid features could be created from the CSV data")
        return None

    return {
        "type": "FeatureCollection",
        "features": features
    }

def process_geometries(geojson_data):
    """Convert multiple geometries into a single MultiPolygon or GeometryCollection."""
    try:
        if not geojson_data or 'features' not in geojson_data:
            st.error("Invalid GeoJSON data")
            return None

        geometries = [shape(feature['geometry']) for feature in geojson_data['features']]

        if not geometries:
            st.warning("No features found to process.")
            return None

        combined = unary_union(geometries)

        if combined.geom_type == 'Polygon':
            combined = MultiPolygon([combined])

        return combined
    except Exception as e:
        st.error(f"Error processing geometries: {str(e)}")
        return None

def display_map(geojson_data, processed_geojson=None):
    """Display both original and processed geometries on a Folium map."""
    try:
        if not geojson_data or 'features' not in geojson_data or not geojson_data['features']:
            st.error("No valid features to display")
            return None

        gdf_original = gpd.GeoDataFrame.from_features(geojson_data['features'])
        center_lat = gdf_original.unary_union.centroid.y
        center_lon = gdf_original.unary_union.centroid.x

        m = folium.Map(location=[center_lat, center_lon], zoom_start=10)

        folium.GeoJson(
            geojson_data,
            name='Original Features',
            style_function=lambda x: {'fillColor': 'blue', 'color': 'blue', 'fillOpacity': 0.3}
        ).add_to(m)

        if processed_geojson:
            folium.GeoJson(
                processed_geojson,
                name='Combined Shape',
                style_function=lambda x: {'fillColor': 'red', 'color': 'red', 'fillOpacity': 0.3}
            ).add_to(m)

        folium.LayerControl().add_to(m)
        return m
    except Exception as e:
        st.error(f"Error displaying map: {str(e)}")
        return None

def main():
    st.set_page_config(page_title="Smart GeoJSON and CSV Processor", layout="wide")

    st.title("GeoJSON and CSV Feature Combiner")
    
    st.markdown("""
    ### Key Benefits:
    - Simplify complex geospatial workflows by easily converting between CSV and GeoJSON formats while combining multiple geometric features into a single shape
    - Save time with instant visualization and filtering capabilities for large geographic datasets
    """)

    st.markdown("""
    Upload your GeoJSON or CSV file to get started. 
    You can filter features based on their properties and combine them into a single shape.
    """)

    uploaded_file = st.file_uploader(
        "Drop your file here",
        type=['csv', 'json', 'geojson'],
        help="Upload a CSV file with coordinates or a GeoJSON file"
    )

    if 'current_geojson' not in st.session_state:
        st.session_state.current_geojson = None
    
    if 'filters' not in st.session_state:
        st.session_state.filters = {}

    if uploaded_file is not None:
        file_type = detect_file_type(uploaded_file)
        st.write(f"Detected file type: {file_type}")

        if file_type == 'geojson':
            try:
                geojson_data = json.load(uploaded_file)
                is_valid, message = validate_geojson(geojson_data)

                if not is_valid:
                    st.error(message)
                    return

                st.session_state.current_geojson = geojson_data
                st.success("GeoJSON file successfully loaded")

                st.subheader("Data Preview")
                if st.session_state.current_geojson['features']:
                    df = pd.json_normalize(st.session_state.current_geojson['features'])
                    st.dataframe(df.head(100))

                if st.session_state.current_geojson and st.session_state.current_geojson['features']:
                    properties = st.session_state.current_geojson['features'][0]['properties'].keys()
                    
                    st.subheader("Filter Features")
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        selected_properties = st.multiselect(
                            "Select properties to filter by",
                            options=properties
                        )
                    
                    filters = {}
                    if selected_properties:
                        with col2:
                            for prop in selected_properties:
                                values = get_property_values(st.session_state.current_geojson, prop)
                                selected_values = st.multiselect(
                                    f"Filter by {prop}",
                                    options=values,
                                    default=values
                                )
                                filters[prop] = selected_values

                    filtered_geojson = filter_geojson(st.session_state.current_geojson, filters)
                    st.write(f"Showing {len(filtered_geojson['features'])} features after filtering")
                    st.session_state.current_geojson = filtered_geojson

            except json.JSONDecodeError as e:
                st.error(f"Failed to parse GeoJSON file: {str(e)}")
            except Exception as e:
                st.error(f"Unexpected error processing GeoJSON file: {str(e)}")

        elif file_type == 'csv':
            try:
                df = pd.read_csv(uploaded_file)
                st.success("CSV file successfully loaded")
                
                st.subheader("Data Preview")
                st.dataframe(df.head(100))

                col1, col2 = st.columns(2)
                with col1:
                    lat_col = st.selectbox("Select Latitude Column", df.columns)
                with col2:
                    lon_col = st.selectbox("Select Longitude Column", df.columns)

                st.subheader("Filter Data")
                filter_columns = st.multiselect(
                    "Select columns to filter by",
                    options=[col for col in df.columns if col not in [lat_col, lon_col]]
                )
                
                for col in filter_columns:
                    unique_values = df[col].unique()
                    selected_values = st.multiselect(
                        f"Filter by {col}",
                        options=unique_values,
                        default=unique_values
                    )
                    if selected_values:
                        df = df[df[col].isin(selected_values)]

                st.write(f"Showing {len(df)} rows after filtering")

                is_valid, message = validate_csv_coordinates(df, lat_col, lon_col)
                if not is_valid:
                    st.error(message)
                    return

                geojson_result = csv_to_geojson(df, lat_col, lon_col)
                if geojson_result:
                    st.session_state.current_geojson = geojson_result
                    st.success("CSV successfully converted to GeoJSON")
                else:
                    st.error("Failed to convert CSV to GeoJSON")

            except pd.errors.EmptyDataError:
                st.error("The uploaded CSV file is empty")
            except pd.errors.ParserError as e:
                st.error(f"Error parsing CSV file: {str(e)}")
            except Exception as e:
                st.error(f"Unexpected error processing CSV file: {str(e)}")

        else:
            st.error("Unable to process this file type. Please upload a CSV or GeoJSON file.")
            return

        if st.session_state.current_geojson:
            st.subheader("Your Data")
            m = display_map(st.session_state.current_geojson)
            if m:
                folium_static(m)

            if st.button("Process Geometries"):
                with st.spinner("Processing geometries..."):
                    combined_geometry = process_geometries(st.session_state.current_geojson)
                    if combined_geometry:
                        processed_geojson = {
                            "type": "FeatureCollection",
                            "features": [{
                                "type": "Feature",
                                "geometry": mapping(combined_geometry),
                                "properties": {}
                            }]
                        }

                        st.subheader("Processed Data")
                        m = display_map(st.session_state.current_geojson, processed_geojson)
                        if m:
                            folium_static(m)

                        col1, col2 = st.columns([2, 1])
                        with col1:
                            output_filename = st.text_input(
                                "Name your output file",
                                value="processed",
                                help="Enter the name for your output file (without .geojson extension)",
                                key="output_filename"
                            )
                        
                        with col2:
                            download_name = f"{output_filename if output_filename else 'processed'}.geojson"
                            st.download_button(
                                "Download Processed GeoJSON",
                                data=json.dumps(processed_geojson, indent=2),
                                file_name=download_name,
                                mime="application/json",
                                key="download_button"  # Added unique key
                            )

if __name__ == "__main__":
    main()