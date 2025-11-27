import os
import sys
import csv
import time
import logging
import argparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

def get_config():
    """
    Parses command-line arguments and retrieves environment variables.
    """
    parser = argparse.ArgumentParser(description="Dynatrace Service Topology Mapper")
    parser.add_argument("--mz-id", help="Optional Management Zone ID to filter services", default=None)
    
    args = parser.parse_args()
    
    base_url = os.environ.get("DT_BASE_URL")
    api_token = os.environ.get("DT_API_TOKEN")
    
    if not base_url or not api_token:
        logger.error("Environment variables DT_BASE_URL and DT_API_TOKEN must be set.")
        sys.exit(1)
        
    # Ensure base URL doesn't end with slash for consistency
    base_url = base_url.rstrip("/")
    
    return base_url, api_token, args.mz_id

def create_session(api_token):
    """
    Creates a requests Session with retry logic and authorization headers.
    """
    session = requests.Session()
    
    # Auth Header
    session.headers.update({
        "Authorization": f"Api-Token {api_token}",
        "Content-Type": "application/json"
    })
    
    # Retry Logic for 429 (Too Many Requests) and 5xx errors
    # Exponential backoff: sleep 1s, 2s, 4s, etc.
    retry_strategy = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    return session

def fetch_entities(session, base_url, mz_id=None):
    """
    Fetches entities from Dynatrace API v2 using cursor-based pagination.
    """
    endpoint = f"{base_url}/api/v2/entities"
    
    # Initial Parameters
    params = {
        "entitySelector": 'type("SERVICE")',
        "fields": "+fromRelationships.calls,+toRelationships.called_by,+properties.serviceType,+displayName",
        "pageSize": 500
    }
    
    if mz_id:
        # Append Management Zone filter if provided
        # Syntax: type("SERVICE"),mzId("...")
        params["entitySelector"] += f',mzId("{mz_id}")'
        
    all_entities = []
    next_page_key = None
    page_count = 0
    
    logger.info("Starting entity fetch...")
    
    while True:
        try:
            page_count += 1
            
            # If we have a nextPageKey, we MUST NOT send other params (selector, fields)
            # or the API will return 400.
            if next_page_key:
                request_params = {"nextPageKey": next_page_key}
            else:
                request_params = params
                
            response = session.get(endpoint, params=request_params)
            response.raise_for_status()
            
            data = response.json()
            entities = data.get("entities", [])
            all_entities.extend(entities)
            
            logger.info(f"Page {page_count}: Fetched {len(entities)} entities. Total so far: {len(all_entities)}")
            
            next_page_key = data.get("nextPageKey")
            
            # If nextPageKey is null/None, we are done
            if not next_page_key:
                break
                
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching page {page_count}: {e}")
            # If it's a critical failure that retries didn't fix, we might want to stop or continue partial
            # For now, we'll exit to avoid partial data being mistaken for full data
            sys.exit(1)
            
    logger.info(f"Finished fetching. Total entities: {len(all_entities)}")
    return all_entities

def process_topology(entities):
    """
    Parses entities to build a lookup map and a list of relationships.
    """
    logger.info("Processing topology data...")
    
    # 1. Build Lookup Dictionary {entityId: displayName}
    # This is crucial for resolving Target IDs to Names later
    id_to_name = {}
    for entity in entities:
        entity_id = entity.get("entityId")
        display_name = entity.get("displayName", "Unknown")
        if entity_id:
            id_to_name[entity_id] = display_name
            
    topology_rows = []
    
    # 2. Parse Relationships
    for entity in entities:
        source_id = entity.get("entityId")
        source_name = entity.get("displayName", "Unknown")
        
        # Outgoing Calls (Source -> Target)
        # Field: fromRelationships.calls
        from_rels = entity.get("fromRelationships", {})
        outgoing_calls = from_rels.get("calls", [])
        
        for target in outgoing_calls:
            target_id = target.get("id")
            # Resolve Target Name if available in our fetched list, else use ID or "External/Unknown"
            target_name = id_to_name.get(target_id, "Unknown/External")
            
            topology_rows.append({
                "Source_Service_Name": source_name,
                "Source_Service_ID": source_id,
                "Relationship_Direction": "Calls (Outgoing)",
                "Target_Service_ID": target_id,
                "Target_Service_Name": target_name
            })
            
        # Incoming Calls (Target <- Source)
        # Field: toRelationships.called_by
        # Note: In this context, the 'entity' is the Target of the call.
        # But to keep the CSV consistent (Source -> Target), we can flip it or just log it as "Called By".
        # The requirement says: "Incoming (Called by)"
        # Let's log it as: Current Entity is the Target, the item in list is the Source.
        # HOWEVER, usually "Source" in the CSV row implies the 'Subject' of the row.
        # Let's stick to the requested columns: Source_Service_Name, Source_Service_ID, Relationship_Direction, Target_Service_ID
        # If Direction is "Called By", then Source_Service is the one being called.
        
        to_rels = entity.get("toRelationships", {})
        incoming_calls = to_rels.get("called_by", [])
        
        for caller in incoming_calls:
            caller_id = caller.get("id")
            caller_name = id_to_name.get(caller_id, "Unknown/External")
            
            topology_rows.append({
                "Source_Service_Name": source_name,
                "Source_Service_ID": source_id,
                "Relationship_Direction": "Called By (Incoming)",
                "Target_Service_ID": caller_id,
                "Target_Service_Name": caller_name
            })
            
    logger.info(f"Processed {len(topology_rows)} relationships.")
    return topology_rows

def export_to_csv(data, filename="dynatrace_service_topology.csv"):
    """
    Writes the topology data to a CSV file.
    """
    if not data:
        logger.warning("No topology data to export.")
        return

    keys = ["Source_Service_Name", "Source_Service_ID", "Relationship_Direction", "Target_Service_ID", "Target_Service_Name"]
    
    try:
        with open(filename, mode="w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
        logger.info(f"Successfully exported topology to {filename}")
    except IOError as e:
        logger.error(f"Failed to write CSV file: {e}")

def main():
    base_url, api_token, mz_id = get_config()
    
    session = create_session(api_token)
    
    try:
        entities = fetch_entities(session, base_url, mz_id)
        topology_data = process_topology(entities)
        export_to_csv(topology_data)
        
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
