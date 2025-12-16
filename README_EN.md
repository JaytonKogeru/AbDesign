# AbDesign - Antibody Design Service

## Overview

AbDesign is a web service platform for antibody structure analysis and design. The system focuses on CDR (Complementarity-Determining Region) annotation, structure prediction, and binding site analysis for VHH (Variable domain of Heavy-chain-only antibodies, also known as nanobodies).

## Key Features

### 1. CDR Region Annotation
- Support for multiple numbering schemes (Chothia, IMGT, etc.)
- Automatic identification and annotation of CDR1, CDR2, CDR3 regions
- Precise numbering based on [AbNumber](https://github.com/prihoda/abnumber) library
- Output in JSON and CSV formats

### 2. Structure Analysis
- Support for PDB and mmCIF format structure files
- Two submission modes:
  - **separate mode**: Upload VHH and target structures separately
  - **complex mode**: Upload complex structure
- Automatic sequence and chain information extraction

### 3. Asynchronous Task Processing
- Task queue system based on Redis and RQ (Redis Queue)
- Support for long-running computational tasks
- Real-time task status queries

## Technical Architecture

### System Architecture Diagram

```
┌──────────┐      ┌──────────────┐      ┌──────────┐
│  Client  │ HTTP │   FastAPI    │      │  Worker  │
│(Requests)│─────▶│  API Service │◀────▶│ Process  │
└──────────┘      └──────────────┘      └──────────┘
                          │                    │
                          │                    │
                          ▼                    ▼
                  ┌──────────────┐      ┌────────────┐
                  │    Redis     │      │  Pipeline  │
                  │ Message Queue│      │(CDR Annot.)│
                  └──────────────┘      └────────────┘
                          │
                          ▼
                  ┌──────────────┐
                  │File Storage  │
                  │  (/tmp/...)  │
                  └──────────────┘
```

### Core Components

#### 1. API Layer (`api/`)
- **main.py**: FastAPI application entry point
  - `/health`: Health check endpoint
  - `/submit`: Submit analysis tasks
  - `/result/{task_id}`: Query task results
  - `/download/{task_id}/{artifact}`: Download generated files
- **config.py**: Environment configuration management
- **schemas.py**: Data model definitions
- **storage.py**: File storage management
- **task_store.py**: Task state persistence
- **validators.py**: Input validation

#### 2. Pipeline Layer (`pipeline/`)
- **runner.py**: Main pipeline orchestrator
  - Structure alignment (interface reserved)
  - Binding site prediction (interface reserved)
  - Scoring model (mock implementation)
  - CDR annotation (full implementation)
- **cdr.py**: Core CDR annotation logic
  - Uses gemmi for structure parsing
  - Uses abnumber for CDR identification

#### 3. Worker Process (`worker/`)
- **worker.py**: RQ worker main program
- **tasks.py**: Background task definitions
- **queue.py**: Redis queue management

#### 4. AbNumber Integration (`abnumber/`)
- Built-in minimal AbNumber implementation (optional)
- Support for using abnumber package directly from PyPI

## Installation and Deployment

### Requirements
- Python 3.10+
- Redis Server
- Dependencies (see requirements.txt)

### Quick Start

#### 1. Install Dependencies

Using Conda (recommended):
```bash
# Create environment
conda create -n abdesign python=3.10 -y
conda activate abdesign

# Install Redis
conda install -c conda-forge redis-server -y

# Install Python dependencies
pip install -r requirements.txt
```

Using uv (optional):
```bash
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

#### 2. Start Services

You need to start three components (recommended in three separate terminals):

**Terminal 1 - Redis:**
```bash
redis-server --daemonize yes
```

**Terminal 2 - API Service:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
# Or use the startup script
./start_uvicorn.sh
```

**Terminal 3 - Worker:**
```bash
python -m worker.worker
```

#### 3. Run Tests

```bash
# Smoke test
python scripts/smoke_test.py --base-url http://localhost:8000

# With API Key (if enabled)
python scripts/smoke_test.py --base-url http://localhost:8000 --api-key YOUR_KEY
```

## API Usage Examples

### Submit Task

**Separate mode (separate uploads):**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "numbering_scheme=chothia"
```

Response example:
```json
{
  "task_id": "abc123def456",
  "job_id": "rq:job:xyz789",
  "mode": "separate",
  "numbering_scheme": "chothia",
  "received_files": ["vhh_file", "target_file"],
  "status": "queued"
}
```

**Complex mode (complex upload):**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=complex" \
  -F "complex_file=@samples/complex.pdb" \
  -F "numbering_scheme=imgt"
```

### Query Results

```bash
curl "http://localhost:8000/result/{task_id}"
```

Response example:
```json
{
  "task_id": "abc123def456",
  "status": "succeeded",
  "result_metadata": {
    "structure_path": "/tmp/submissions/abc123def456/predicted.pdb",
    "scores_csv": "/tmp/submissions/abc123def456/scores.csv",
    "scores_tsv": "/tmp/submissions/abc123def456/scores.tsv",
    "cdr_json": "/tmp/submissions/abc123def456/cdr_annotations.json",
    "cdr_csv": "/tmp/submissions/abc123def456/cdr_annotations.csv",
    "summary_score": 0.8,
    "numbering_scheme": "chothia",
    "cdr_summary": {
      "scheme": "chothia",
      "chains": [
        {
          "chain_id": "H",
          "cdrs": [
            {
              "name": "CDR1",
              "start": "26",
              "end": "32",
              "sequence": "GFTFNTY"
            }
          ]
        }
      ]
    }
  }
}
```

### Download Files

```bash
# Download predicted structure
curl "http://localhost:8000/download/{task_id}/structure" -o predicted.pdb

# Download CDR annotations (JSON)
curl "http://localhost:8000/download/{task_id}/cdr_annotations_json" -o cdr.json

# Download CDR annotations (CSV)
curl "http://localhost:8000/download/{task_id}/cdr_annotations_csv" -o cdr.csv

# Download scores
curl "http://localhost:8000/download/{task_id}/scores_csv" -o scores.csv
```

## Configuration Options

Configure system behavior through environment variables:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `STORAGE_ROOT` | `/tmp/submissions` | File storage root directory |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `QUEUE_NAME` | `default` | Task queue name |
| `MAX_FILE_SIZE` | `52428800` (50MB) | Maximum file size |
| `API_KEY` | Empty string | API access key (optional) |
| `CORS_ORIGINS` | `*` | Allowed CORS origins |
| `RATE_LIMIT_PER_MINUTE` | `30` | Request rate limit per minute |

Example:
```bash
export STORAGE_ROOT=/var/abdesign/data
export API_KEY=my_secret_key
export RATE_LIMIT_PER_MINUTE=60
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

## Project Structure

```
AbDesign/
├── api/                    # FastAPI Web Service
│   ├── main.py            # Main application and routes
│   ├── config.py          # Configuration management
│   ├── schemas.py         # Data models
│   ├── storage.py         # File storage
│   ├── task_store.py      # Task state management
│   ├── validators.py      # Input validation
│   └── results.py         # Result processing
├── pipeline/              # Core analysis pipeline
│   ├── runner.py          # Pipeline orchestrator
│   └── cdr.py             # CDR annotation logic
├── worker/                # Background task processing
│   ├── worker.py          # Worker main program
│   ├── tasks.py           # Task definitions
│   └── queue.py           # Queue management
├── abnumber/              # AbNumber integration
│   └── __init__.py
├── scripts/               # Utility scripts
│   └── smoke_test.py      # Smoke test
├── samples/               # Sample files
│   ├── vhh_sample.pdb     # VHH sample structure
│   └── target_sample.pdb  # Target sample structure
├── third_party/           # Third-party libraries (unused)
├── requirements.txt       # Python dependencies
├── start_uvicorn.sh       # Startup script
├── TESTING.md            # Testing guide
└── README.md             # This file
```

## Key Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.115.5 | Web framework |
| `uvicorn` | 0.32.0 | ASGI server |
| `redis` | 5.2.1 | Redis client |
| `rq` | 1.16.2 | Task queue |
| `abnumber` | 2.2.1 | Antibody numbering and CDR recognition |
| `biopython` | 1.83 | Bioinformatics tools |
| `gemmi` | 0.6.8 | Structure file parsing |
| `numpy` | 1.26.4 | Numerical computation |

## Development Features

### Middleware
- **CORS**: Cross-origin request support
- **Logging**: Log all requests and response times
- **Exception Handling**: Unified error response format

### Security Features
- **API Key Authentication**: Optional API key protection
- **Rate Limiting**: Request frequency control to prevent abuse
- **File Validation**: Strict file type and size limits

### Scalability
- **Modular Design**: Loosely coupled components, easy to extend
- **Reserved Interfaces**: 
  - Structure alignment module (to be implemented)
  - Binding site prediction (to be implemented)
  - Scoring model (to be implemented)
- **Configuration-driven**: Flexible configuration through environment variables

## CDR Numbering Schemes

Supported numbering schemes:
- **Chothia** (default): Improved version of Kabat, widely used in antibody engineering
- **IMGT**: International ImMunoGeneTics information system standard
- **Kabat**: Classic antibody numbering system
- **AHo**: Another commonly used scheme
- **Martin**: Structure-based alignment numbering

## Troubleshooting

### 1. Worker Cannot Receive Tasks
**Cause**: Redis not started or incorrect connection configuration

**Solution**:
```bash
# Check if Redis is running
ps aux | grep redis-server

# Test connection
redis-cli ping
# Should return PONG

# Ensure environment variables are consistent
echo $REDIS_URL
```

### 2. Port Conflict
**Solution**:
```bash
# Use a different port
uvicorn api.main:app --port 8080

# Update test script
python scripts/smoke_test.py --base-url http://localhost:8080
```

### 3. CDR Annotation Failure
**Common causes**:
- Incorrect structure file format
- Missing ATOM records
- Sequence not recognizable as antibody

**Debugging**:
```bash
# View task logs
tail -f worker.log

# Check structure file
python -c "import gemmi; print(gemmi.read_structure('your_file.pdb'))"
```

### 4. Clean Up Historical Tasks
```bash
# Delete task state
rm -f /tmp/task_state.json

# Clean storage directory
rm -rf /tmp/submissions/*
```

## Extension Development

### Add New Analysis Module

1. Create a new module in `pipeline/`
2. Integrate in `runner.py`
3. Update `PipelineConfig` and `PipelineResult`

Example:
```python
# pipeline/new_module.py
def analyze_something(inputs):
    # Your analysis logic
    return result

# pipeline/runner.py
from pipeline.new_module import analyze_something

def run_pipeline(mode, inputs):
    # ...
    new_result = analyze_something(inputs)
    # ...
```

### Add New API Endpoint

```python
# api/main.py
@app.get("/custom-endpoint/{task_id}")
async def custom_handler(task_id: str):
    # Your handler logic
    return {"result": "data"}
```

## Testing

See [TESTING.md](TESTING.md) for detailed testing guide.

## License

Please check the repository for license information.

## Contributing

Issues and Pull Requests are welcome!

## Contact

For questions, please create an issue in the GitHub repository.

---

**Version**: 0.1.0  
**Last Updated**: December 2025
