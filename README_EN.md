# AbDesign - Antibody Design Tool Integration Platform

[![中文](https://img.shields.io/badge/docs-中文-blue)](README.md)
[![Architecture](https://img.shields.io/badge/docs-Architecture-green)](ARCHITECTURE.md)
[![Development](https://img.shields.io/badge/docs-Development-orange)](DEVELOPMENT.md)
[![Testing](https://img.shields.io/badge/docs-Testing-red)](TESTING.md)

## Overview

AbDesign is a **unified gateway platform for antibody design tools**, designed to transform user-provided structure information into configuration languages and execution commands that various antibody design tools can understand. The platform integrates mainstream antibody design tools such as RFantibody and BoltzGen, and can easily be extended to integrate more tools.

## 📚 Documentation Navigation

- **[README (中文)](README.md)** - Chinese version documentation
- **[Architecture Documentation (ARCHITECTURE.md)](ARCHITECTURE.md)** - Detailed technical architecture and modules
- **[Development Guide (DEVELOPMENT.md)](DEVELOPMENT.md)** - API details, development guide and troubleshooting
- **[Testing Guide (TESTING.md)](TESTING.md)** - Environment setup and testing methods

## Core Positioning

AbDesign serves as a **unified gateway**, solving the following problems:

1. **Unified Input Interface**: Provides standardized structure file upload and parameter configuration
2. **Automatic Format Conversion**: Transforms user inputs into tool-specific configuration files (YAML, JSON, command-line arguments, etc.)
3. **Tool Orchestration**: Coordinates the execution workflow of multiple antibody design tools
4. **Result Integration**: Collects and standardizes outputs from various tools
5. **Extensibility**: Easily add new antibody design tool integrations

## Integrated Tools

### 🧬 RFantibody
An RFdiffusion-based antibody design tool focused on hotspot-driven antibody optimization.

**Capabilities provided by AbDesign:**
- Automatically converts PDB/mmCIF structures to RFantibody input format
- Parses user-specified hotspot residues and generates HLT files
- Configures design parameters (design regions, number of designs, etc.)
- Executes via Docker containerization or direct invocation
- Collects and standardizes design results

**Usage Example:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@nanobody.pdb" \
  -F "target_file=@target.pdb" \
  -F "user_params={\"integrations\":{\"rfantibody\":{\"enabled\":true,\"num_designs\":20}}}"
```

### 🔬 BoltzGen
A structure prediction tool based on the Boltz-1 model, suitable for nanobody-target complex prediction.

**Capabilities provided by AbDesign:**
- Automatically generates BoltzGen YAML configuration files
- Handles nanobody and target chain mapping relationships
- Manages batch design tasks
- Supports Docker containerized execution
- Validates and collects output results

**Usage Example:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@nanobody.pdb" \
  -F "target_file=@target.pdb" \
  -F "user_params={\"integrations\":{\"boltzgen\":{\"enabled\":true,\"protocol\":\"nanobody-anything\",\"num_designs\":50}}}"
```

## Supporting Modules

To support tool integration, AbDesign provides the following auxiliary features:

### 1. Structure Standardization and Residue Mapping
- Unified PDB and mmCIF format handling
- Generates standardized mmCIF structures
- Establishes auth/label residue identifier mappings
- Supports hotspot residue format conversion

### 2. CDR Region Annotation
- Automatically identifies and annotates CDR1, CDR2, CDR3 regions
- Supports multiple numbering schemes (Chothia, IMGT, Kabat, etc.)
- Provides precise sequence and structure information for tools

### 3. Asynchronous Task Management
- Task queue based on Redis and RQ
- Supports long-running design tasks
- Real-time task status queries and result downloads

## Technical Architecture

AbDesign adopts a microservices architecture with a core focus on **configuration generation and tool orchestration**:

```
┌─────────────────┐
│  User Input     │
│ (Structures +   │
│  Parameters)    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│Standardization  │
│   Layer         │
│ - Format Conv.  │
│ - Residue Map.  │
│ - CDR Annot.    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Configuration   │
│  Generation     │
│ - YAML Config   │
│ - HLT Files     │
│ - CLI Args      │
└────────┬────────┘
         │
         ├──────────┬──────────┬─────────┐
         ▼          ▼          ▼         ▼
    ┌────────┐ ┌────────┐ ┌────────┐  ...
    │RFanti- │ │BoltzGen│ │ Future │
    │ body   │ │        │ │  Tools │
    └────┬───┘ └───┬────┘ └───┬────┘
         │         │          │
         └─────────┴──────────┘
                   │
                   ▼
         ┌─────────────────┐
         │Result Collection│
         │ & Integration   │
         └─────────────────┘
```

### Core Modules

1. **API Layer (`api/`)**: Provides HTTP interface, handles file uploads and task submission
2. **Pipeline Layer (`pipeline/`)**: Structure standardization, CDR annotation, residue mapping
3. **Integration Layer (`integrations/`)**: Tool adapters and configuration generators
4. **Worker Process (`worker/`)**: Asynchronous task execution and result collection

For detailed architecture documentation, see [ARCHITECTURE.md](ARCHITECTURE.md)

## Quick Start

### Requirements
- Python 3.10+
- Redis Server
- Dependencies (see requirements.txt)

### Installation Steps

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

#### 2. Start Services

You need to start three components (recommended in three separate terminals):

**Terminal 1 - Redis:**
```bash
redis-server --daemonize yes
```

**Terminal 2 - API Service:**
```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000 --log-level info
```

**Terminal 3 - Worker:**
```bash
python -m worker.worker
```

#### 3. Submit Design Tasks

**Basic usage (standardization and CDR annotation only):**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb"
```

**Enable RFantibody design:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "user_params={\"target_hotspots\":[\"A:305\",\"A:456\"],\"integrations\":{\"rfantibody\":{\"enabled\":true,\"num_designs\":20,\"design_loops\":[\"H1\",\"H3\"]}}}"
```

**Enable BoltzGen prediction:**
```bash
curl -X POST "http://localhost:8000/submit" \
  -F "mode=separate" \
  -F "vhh_file=@samples/vhh_sample.pdb" \
  -F "target_file=@samples/target_sample.pdb" \
  -F "user_params={\"integrations\":{\"boltzgen\":{\"enabled\":true,\"protocol\":\"nanobody-anything\",\"num_designs\":50}}}"
```

#### 4. Query Results

```bash
# Get task status and results
curl "http://localhost:8000/result/{task_id}"

# Download generated configuration files
curl "http://localhost:8000/download/{task_id}/rfantibody_config" -o config.yaml
```

## Adding New Tool Integrations

AbDesign is designed with an extensible architecture. Adding a new tool requires only three steps:

### Step 1: Create Tool Adapter

Create a new file in the `integrations/` directory, e.g., `newtool.py`:

```python
from pathlib import Path
from typing import Dict, Any

def run_newtool(
    task_dir: Path,
    input_structure: Path,
    config: Dict[str, Any],
    **kwargs
) -> Dict[str, Any]:
    """
    Adapter function for the new tool
    
    Args:
        task_dir: Task working directory
        input_structure: Input structure file
        config: Tool configuration parameters
    
    Returns:
        Dictionary containing output file paths and metadata
    """
    # 1. Generate tool-specific configuration file
    config_path = task_dir / "newtool_config.yaml"
    # ... write configuration
    
    # 2. Execute tool (Docker or direct invocation)
    # ... invoke command
    
    # 3. Collect and return results
    return {
        "status": "success",
        "output_files": [...],
        "metadata": {...}
    }
```

### Step 2: Integrate into Pipeline

Add integration point in `pipeline/runner.py`:

```python
from integrations.newtool import run_newtool

# Add configuration in IntegrationConfig
@dataclass
class NewToolIntegrationConfig:
    enabled: bool = False
    param1: str = "default"
    # ... other parameters

# Call in run_pipeline function
if config.integrations.newtool.enabled:
    newtool_result = run_newtool(
        task_dir=config.output_dir,
        input_structure=inputs.get("structure"),
        config=config.integrations.newtool
    )
```

### Step 3: Update API Schema

Add configuration model in `api/schemas.py`:

```python
class NewToolConfig(BaseModel):
    enabled: bool = False
    param1: Optional[str] = None
```

That's it! The new tool can now be invoked via the API.

## Configuration Options

Main configuration via environment variables:

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `STORAGE_ROOT` | `/tmp/submissions` | File storage root directory |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis connection URL |
| `QUEUE_NAME` | `default` | Task queue name |
| `MAX_FILE_SIZE` | `52428800` (50MB) | Maximum file size |
| `API_KEY` | Empty string | API access key (optional) |

For detailed API documentation and configuration options, see [DEVELOPMENT.md](DEVELOPMENT.md)

## Project Structure

```
AbDesign/
├── integrations/          # 🔧 Tool Adapters (Core)
│   ├── rfantibody.py      # RFantibody adapter
│   ├── boltzgen.py        # BoltzGen adapter
│   └── normalize.py       # Standardization utilities
├── pipeline/              # 📋 Supporting Processing Modules
│   ├── runner.py          # Pipeline orchestrator
│   ├── cdr.py             # CDR annotation
│   └── epitope/           # Structure standardization & mapping
├── api/                   # 🌐 Web Interface
├── worker/                # ⚙️ Asynchronous Task Processing
├── scripts/               # 🛠️ Utility Scripts
├── tests/                 # ✅ Test Suite
└── samples/               # 📁 Sample Files
```

## Key Dependencies

| Package | Purpose |
|---------|---------|
| `fastapi` + `uvicorn` | Web service framework |
| `redis` + `rq` | Asynchronous task queue |
| `gemmi` | Structure file parsing |
| `abnumber[anarci]` | CDR recognition and numbering |
| `biopython` | Bioinformatics tools |

## Testing and Validation

```bash
# Quick self-check (no services needed)
make selftest

# Full test (requires services running)
python scripts/smoke_test.py --base-url http://localhost:8000

# Unit tests
pytest
```

For detailed testing guide, see [TESTING.md](TESTING.md)

## Frequently Asked Questions

### Tool Integration Related

**Q: How to confirm if RFantibody/BoltzGen is available?**

Check Docker images or direct invocation:
```bash
docker images | grep rfantibody
docker images | grep boltzgen
```

**Q: How to view generated configuration files?**

Configuration files are saved in the task directory and can be obtained via download endpoint:
```bash
curl "http://localhost:8000/download/{task_id}/rfantibody_config" -o config.yaml
```

**Q: Can multiple tools run simultaneously?**

Yes, multiple integrations can be enabled in `user_params`:
```json
{
  "integrations": {
    "rfantibody": {"enabled": true, "num_designs": 20},
    "boltzgen": {"enabled": true, "num_designs": 50}
  }
}
```

### Service Running Related

**Q: Redis connection failed?**

Check if Redis is running and confirm connection address:
```bash
ps aux | grep redis-server
redis-cli ping  # Should return PONG
```

**Q: How to view task logs?**

Worker logs contain detailed execution information:
```bash
# View real-time logs in worker terminal
# Or view log file (if configured)
tail -f worker.log
```

For more technical details and API documentation, see [DEVELOPMENT.md](DEVELOPMENT.md)

## License

Please check the repository for license information.

## Contributing

Issues and Pull Requests are welcome!

## Contact

For questions, please create an issue in the GitHub repository.

---

**Version**: 0.1.0  
**Last Updated**: December 2025
