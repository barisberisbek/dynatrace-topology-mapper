# Dynatrace Service Topology Mapper

This Python script automates the extraction of microservice topology (Service Flow) from the Dynatrace API v2. It fetches services and their "Incoming" (Called by) and "Outgoing" (Calls) dependencies, resolving them into a readable CSV format.

## Features

-   **Automated Extraction**: Fetches all services and their relationships.
-   **Cursor-based Pagination**: Handles large environments efficiently using Dynatrace's v2 pagination logic.
-   **Name Resolution**: Automatically resolves Entity IDs to human-readable Service Names.
-   **Resilience**: Implements exponential backoff and retry logic for HTTP 429 (Too Many Requests) errors.
-   **Security**: Uses Environment Variables for sensitive credentials.

## Prerequisites

-   Python 3.6+
-   `requests` library

## Installation

1.  Clone the repository:
    ```bash
    git clone https://github.com/barisberisbek/dynatrace-topology-mapper.git
    cd dynatrace-topology-mapper
    ```

2.  Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

You must set the following environment variables before running the script:

-   `DT_BASE_URL`: Your Dynatrace Environment URL (e.g., `https://{env-id}.live.dynatrace.com`).
-   `DT_API_TOKEN`: A Dynatrace API Token with the **`entities.read`** scope.

**Windows (PowerShell):**
```powershell
$env:DT_BASE_URL = "https://your-env.live.dynatrace.com"
$env:DT_API_TOKEN = "dt0c01.YOUR.TOKEN"
```

**Linux/Mac:**
```bash
export DT_BASE_URL="https://your-env.live.dynatrace.com"
export DT_API_TOKEN="dt0c01.YOUR.TOKEN"
```

## Usage

Run the script directly:

```bash
python dynatrace_topology_mapper.py
```

### Optional Arguments

-   `--mz-id`: Filter services by a specific Management Zone ID.

```bash
python dynatrace_topology_mapper.py --mz-id "YOUR_MZ_ID"
```

## Output

The script generates a file named `dynatrace_service_topology.csv` in the current directory with the following columns:

-   `Source_Service_Name`
-   `Source_Service_ID`
-   `Relationship_Direction`
-   `Target_Service_ID`
-   `Target_Service_Name`

## License

This project is open source.
