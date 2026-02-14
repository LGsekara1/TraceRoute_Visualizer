import requests
import folium
import csv
import re
import time
from geopy.distance import geodesic

# Configuration
API_KEY = "7b36300a40324bd2a00cd43f635b975b"  # ipgeolocation.io API key
FILE_PATH = "C:\\Users\\USER\\OneDrive - University of Moratuwa\\ENTC S4 ACA\\EN2150_CommNetwork\\assignement 1\\input.txt"
SOURCE_LOCATION = (6.9318 , 79.8863)  # Your source location 
REQUEST_DELAY = 0.5  # Delay between API requests to avoid rate limiting


def parse_mtr_file(file_path):
    """
    Parse MTR (My Traceroute) output file to extract site names and hop IP addresses.
    
    Args:
        file_path: Path to the MTR output file
        
    Returns:
        Dictionary with site names as keys and lists of hop IPs as values
    """
    sites_hops = {}
    current_site = None
    hops = []
    
    try:
        with open(file_path, 'r') as file:
            lines = file.readlines()
            
        for line in lines:
            # Check for the start of a new site (format: "SITE-sitename")
            if line.startswith("SITE-"):
                # Save previous site's hops
                if current_site and hops:
                    sites_hops[current_site] = hops
                
                # Start new site
                current_site = line.split("-")[1].strip()
                hops = []
                
            # Match hop lines (format: " 1.|-- ip.address")
            elif re.match(r"\s*\d+\.\|\s*-", line):
                parts = line.split()
                if len(parts) >= 2:
                    hop_ip = parts[1]
                    # Only add valid IPs (not "???" or empty)
                    if hop_ip and hop_ip != "???" and not hop_ip.startswith("?"):
                        hops.append(hop_ip)
        
        # Add the last site's hops
        if current_site and hops:
            sites_hops[current_site] = hops
            
    except FileNotFoundError:
        print(f"Error: File '{file_path}' not found.")
        return {}
    except Exception as e:
        print(f"Error parsing file: {e}")
        return {}
    
    return sites_hops


def get_ip_geolocation(ip_address, api_key):
    """
    Fetch geolocation details for an IP address using ipgeolocation.io API.
    
    Args:
        ip_address: IP address to lookup
        api_key: API key for ipgeolocation.io
        
    Returns:
        Dictionary with location details or None if lookup fails
    """
    url = f"https://api.ipgeolocation.io/ipgeo?apiKey={api_key}&ip={ip_address}"
    
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if response.status_code == 200 and data.get("latitude") and data.get("longitude"):
            return {
                "ip": data.get("ip", ip_address),
                "city": data.get("city", "Unknown"),
                "region": data.get("state_prov", "Unknown"),
                "country": data.get("country_name", "Unknown"),
                "country_code": data.get("country_code2", "??"),
                "isp": data.get("isp", "Unknown"),
                "latitude": float(data.get("latitude", 0)),
                "longitude": float(data.get("longitude", 0))
            }
        else:
            print(f"Warning: Incomplete data for IP {ip_address}")
            return None
            
    except requests.exceptions.Timeout:
        print(f"Timeout fetching data for IP: {ip_address}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data for IP {ip_address}: {e}")
        return None
    except (ValueError, KeyError) as e:
        print(f"Error parsing response for IP {ip_address}: {e}")
        return None


def create_traceroute_map(locations, site_name, output_dir="."):
    """
    Create an interactive map showing the traceroute path.
    
    Args:
        locations: List of tuples containing (latitude, longitude, label, details)
        site_name: Name of the destination site
        output_dir: Directory to save the map HTML file
    """
    if not locations or len(locations) < 2:
        print(f"Not enough location data to create map for {site_name}")
        return
    
    # Create map centered on the first hop
    map_center = [locations[0][0], locations[0][1]]
    map_object = folium.Map(location=map_center, zoom_start=3, tiles='OpenStreetMap')
    
    # Extract coordinates for polyline
    coords = [(loc[0], loc[1]) for loc in locations]
    
    # Draw the path with a colored line
    folium.PolyLine(
        coords,
        color="red",
        weight=3,
        opacity=0.7,
        popup=f"Route to {site_name}"
    ).add_to(map_object)
    
    # Add markers for each hop
    for idx, (lat, lon, label, details) in enumerate(locations):
        if idx == 0:
            # Source marker (green)
            icon_color = 'green'
            icon = 'home'
            popup_text = f"<b>Source</b><br>{label}"
        elif idx == len(locations) - 1:
            # Destination marker (red)
            icon_color = 'red'
            icon = 'flag'
            popup_text = f"<b>Destination</b><br>{label}<br>{details}"
        else:
            # Intermediate hop (blue)
            icon_color = 'blue'
            icon = 'info-sign'
            popup_text = f"<b>Hop {idx}</b><br>{label}<br>{details}"
        
        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_text, max_width=300),
            tooltip=label,
            icon=folium.Icon(color=icon_color, icon=icon)
        ).add_to(map_object)
    
    # Save the map
    output_file = f"{output_dir}/{site_name}_traceroute_map.html"
    map_object.save(output_file)
    print(f"Map saved to '{output_file}'")


def process_traceroute(site_name, hop_ips, source_location, api_key):
    """
    Process a traceroute by fetching geolocation for each hop and creating visualization.
    
    Args:
        site_name: Name of the destination site
        hop_ips: List of IP addresses for each hop
        source_location: Tuple of (latitude, longitude) for the source
        api_key: API key for geolocation service
    """
    print(f"\n{'='*60}")
    print(f"Processing traceroute to: {site_name}")
    print(f"{'='*60}")
    
    # Start with source location
    locations = [(source_location[0], source_location[1], "Source (Negombo, Sri Lanka)", "Your location")]
    
    # CSV file to store hop details
    csv_filename = f"{site_name}_hops.csv"
    
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        writer.writerow(['Hop', 'IP Address', 'Country', 'City', 'ISP', 'Distance (km)', 'Cumulative Distance (km)'])
        
        cumulative_distance = 0.0
        
        for hop_num, ip_address in enumerate(hop_ips, start=1):
            print(f"  Hop {hop_num}: {ip_address} ... ", end='', flush=True)
            
            # Fetch geolocation
            details = get_ip_geolocation(ip_address, api_key)
            
            if details:
                current_location = (details["latitude"], details["longitude"])
                previous_location = (locations[-1][0], locations[-1][1])
                
                # Calculate distance from previous hop
                distance = geodesic(previous_location, current_location).kilometers
                cumulative_distance += distance
                
                # Create label for this hop
                label = f"{details['city']}, {details['country_code']}"
                detail_text = f"IP: {details['ip']}<br>ISP: {details['isp']}<br>Distance: {distance:.2f} km"
                
                # Add to locations list
                locations.append((details["latitude"], details["longitude"], label, detail_text))
                
                # Write to CSV
                writer.writerow([
                    hop_num,
                    details['ip'],
                    details['country'],
                    details['city'],
                    details['isp'],
                    f"{distance:.2f}",
                    f"{cumulative_distance:.2f}"
                ])
                
                print(f"✓ {label} ({distance:.2f} km)")
                
            else:
                print(f"✗ Failed to get location")
                writer.writerow([hop_num, ip_address, 'Unknown', 'Unknown', 'Unknown', 'N/A', 'N/A'])
            
            # Rate limiting delay
            time.sleep(REQUEST_DELAY)
    
    print(f"\nTotal distance: {cumulative_distance:.2f} km")
    print(f"CSV data saved to '{csv_filename}'")
    
    # Create the map
    create_traceroute_map(locations, site_name)


def main():
    """Main function to orchestrate the traceroute visualization."""
    print("="*60)
    print("Traceroute Path Visualizer")
    print("="*60)
    
    # Parse the MTR file
    sites_hops = parse_mtr_file(FILE_PATH)
    
    if not sites_hops:
        print("No sites found in the input file. Please check the file format.")
        return
    
    print(f"\nFound {len(sites_hops)} site(s) to process:")
    for site in sites_hops.keys():
        print(f"  - {site} ({len(sites_hops[site])} hops)")
    
    # Process each site
    for site_name, hop_ips in sites_hops.items():
        if not hop_ips:
            print(f"\nSkipping {site_name} (no valid hops)")
            continue
            
        process_traceroute(site_name, hop_ips, SOURCE_LOCATION, API_KEY)
    
    print(f"\n{'='*60}")
    print("Processing complete!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()