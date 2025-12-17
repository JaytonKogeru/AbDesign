"""Lightweight runner for orchestrating prediction pipelines.

The module exposes :func:`run_pipeline` as the integration point for worker
jobs. The initial implementation writes mock artifacts but keeps the structure
needed to plug in real components such as structure alignment, binding-site
prediction, and scoring models.
"""
from __future__ import annotations
"""Lightweight runner for orchestrating prediction pipelines.

The module exposes :func:`run_pipeline` as the integration point for worker
jobs. The initial implementation writes mock artifacts but keeps the structure
needed to plug in real components such as structure alignment, binding-site
prediction, and scoring models.
"""

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from integrations.boltzgen import run_boltzgen
from integrations.normalize import normalize_and_derive
from integrations.rfantibody import run_rfantibody
from pipeline.cdr import CDRArtifacts, annotate_cdrs
from pipeline.epitope.mapping import (
    MappingResultV2,
    ResolveResultV2,
    build_residue_mapping_v2,
    resolve_hotspots_v2,
)
from pipeline.epitope.standardize import standardize_structure
from pipeline.epitope.spec import normalize_target_hotspots

LOGGER = logging.getLogger(__name__)


@dataclass
class AlignmentConfig:
    """Configuration for structure alignment engines."""

    enabled: bool = True
    method: str = "rmsd_alignment"
    reference_structure: Optional[Path] = None


@dataclass
class BindingSiteConfig:
    """Configuration for binding-site prediction."""

    enabled: bool = True
    predictor: str = "p2rank"
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoringConfig:
    """Configuration for downstream scoring models."""

    enabled: bool = True
    model_name: str = "graph-attention-scoring"
    weights_path: Optional[Path] = None
    extra_features: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RFantibodyIntegrationConfig:
    """Configuration for RFantibody adapter."""

    enabled: bool = False
    use_docker: bool = True
    docker_image: str = "rfantibody"
    num_designs: int = 20
    timeout: int = 3600
    retries: int = 1


@dataclass
class BoltzgenIntegrationConfig:
    """Configuration for BoltzGen adapter."""

    enabled: bool = False
    use_docker: bool = True
    docker_image: str = "boltzgen"
    protocol: str = "nanobody-anything"
    num_designs: int = 50
    timeout: int = 3600
    retries: int = 1


@dataclass
class IntegrationConfig:
    """Container for optional downstream integrations."""

    rfantibody: RFantibodyIntegrationConfig = field(default_factory=RFantibodyIntegrationConfig)
    boltzgen: BoltzgenIntegrationConfig = field(default_factory=BoltzgenIntegrationConfig)


@dataclass
class PipelineConfig:
    """Top-level configuration passed to the pipeline runner."""

    mode: str
    output_dir: Path
    cdr_numbering_scheme: str = "chothia"
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    binding_site: BindingSiteConfig = field(default_factory=BindingSiteConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    keep_intermediates: bool = True
    integration: IntegrationConfig = field(default_factory=IntegrationConfig)


@dataclass
class PipelineArtifacts:
    """Artifact locations produced by the pipeline."""

    structure: Path
    scores_csv: Path
    scores_tsv: Path
    summary_json: Path
    cdr_json: Optional[Path] = None
    cdr_csv: Optional[Path] = None
    target_residue_mapping: Optional[Path] = None
    target_hotspots_resolved: Optional[Path] = None
    scaffold_standardized: Optional[Path] = None
    target_standardized: Optional[Path] = None
    scaffold_hlt: Optional[Path] = None
    boltzgen_yaml: Optional[Path] = None
    rfantibody_outputs: Optional[Dict[str, Any]] = None
    boltzgen_outputs: Optional[Dict[str, Any]] = None


@dataclass
class PipelineResult:
    """Return value that encapsulates artifacts and metadata."""

    artifacts: PipelineArtifacts
    summary_score: float
    numbering_scheme: str
    alignment: Dict[str, Any]
    binding_site_prediction: Dict[str, Any]
    scoring: Dict[str, Any]
    cdr_annotation: Optional[Dict[str, Any]]
    target_hotspots_input: Optional[list]
    target_hotspots_resolved: Optional[ResolveResultV2]
    target_mapping_file: Optional[Path]
    normalization: Optional[Dict[str, Any]] = None
    integration_outputs: Optional[Dict[str, Any]] = None
    config: Dict[str, Any] = field(default_factory=dict)


def run_pipeline(mode: str, inputs: Mapping[str, Any]) -> PipelineResult:
    """Execute the prediction pipeline for the given mode and inputs.

    Parameters
    ----------
    mode:
        Submission mode (e.g. "separate" or "complex"). The value is recorded in
        the configuration and may influence downstream components.
    inputs:
        A mapping that contains user parameters, uploaded file locations, and an
        optional ``output_dir`` where artifacts will be written.

    Returns
    -------
    PipelineResult
        A structured response that references the created mock artifacts. The
        layout matches the expected production outputs, making it easy to swap
        in real algorithms later.
    """

    LOGGER.info("Starting pipeline in %s mode", mode)

    numbering_scheme = _resolve_numbering_scheme(inputs)
    config = _build_config(mode, inputs, numbering_scheme)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    predicted_path = config.output_dir / "predicted.pdb"
    scores_csv_path = config.output_dir / "scores.csv"
    scores_tsv_path = config.output_dir / "scores.tsv"
    summary_path = config.output_dir / "pipeline_summary.json"
    cdr_json_path = config.output_dir / "cdr_annotations.json"
    cdr_csv_path = config.output_dir / "cdr_annotations.csv"

    files = inputs.get("files", {})
    scaffold_path = files.get("vhh_file") or files.get("scaffold_file") or files.get("complex_file")
    target_path = files.get("target_file") or files.get("target")
    chain_role_map = (inputs.get("user_params") or {}).get("chain_role_map") or {}

    alignment_result = _run_structure_alignment(config.alignment, inputs)
    binding_site_result = _predict_binding_sites(config.binding_site, inputs)
    scoring_result = _score_models(config.scoring, binding_site_result, inputs)

    normalization: Dict[str, Any] | None = None
    cdr_annotation: Optional[Dict[str, Any]] = None
    cdr_mapping_payload: Optional[Dict[str, Any]] = None
    if scaffold_path:
        normalization = normalize_and_derive(
            scaffold_path,
            target_path,
            str(config.output_dir / "normalized"),
            numbering_scheme=numbering_scheme,
            chain_role_map=chain_role_map,
        )
        cdr_annotation = normalization.get("scaffold_cdr_payload") or normalization.get("scaffold_cdr_mapping_payload")
        cdr_mapping_payload = normalization.get("scaffold_cdr_mapping_payload")
        cdr_json_path = Path(normalization.get("scaffold_cdr_annotations", cdr_json_path))
        cdr_csv_path = cdr_json_path.with_suffix(".csv")
        predicted_path = Path(normalization.get("scaffold_standardized", predicted_path))

    if cdr_annotation is None:
        cdr_annotation = _maybe_annotate_cdrs(inputs, CDRArtifacts(cdr_json_path, cdr_csv_path))

    hotspot_payload = _maybe_process_hotspots(
        inputs,
        config.output_dir,
        mapping_override=normalization.get("target_mapping") if normalization else None,
        standardized_override=normalization.get("target_standardized") if normalization else None,
    )

    rfantibody_output: Optional[Dict[str, Any]] = None
    boltzgen_output: Optional[Dict[str, Any]] = None

    if normalization and config.integration.rfantibody.enabled and normalization.get("scaffold_hlt_path"):
        design_loops = _design_loops_from_cdr(cdr_mapping_payload)
        rfantibody_output = run_rfantibody(
            config.output_dir,
            normalization.get("scaffold_hlt_path"),
            normalization.get("target_standardized") or target_path,
            hotspots_resolved=(hotspot_payload or {}).get("resolved_summary"),
            design_loops=design_loops,
            num_designs=config.integration.rfantibody.num_designs,
            use_docker=config.integration.rfantibody.use_docker,
            docker_image=config.integration.rfantibody.docker_image,
            timeout=config.integration.rfantibody.timeout,
            retries=config.integration.rfantibody.retries,
        )
        if rfantibody_output.get("design_pdbs"):
            predicted_path = Path(rfantibody_output["design_pdbs"][0])

    if normalization and normalization.get("boltzgen_yaml") and config.integration.boltzgen.enabled:
        boltzgen_output = run_boltzgen(
            config.output_dir,
            normalization.get("boltzgen_yaml"),
            protocol=config.integration.boltzgen.protocol,
            num_designs=config.integration.boltzgen.num_designs,
            mapping=normalization.get("scaffold_mapping_json"),
            use_docker=config.integration.boltzgen.use_docker,
            docker_image=config.integration.boltzgen.docker_image,
            timeout=config.integration.boltzgen.timeout,
            retries=config.integration.boltzgen.retries,
        )
        if boltzgen_output.get("final_ranked_designs"):
            predicted_path = Path(boltzgen_output["final_ranked_designs"][0])

    mock_score = scoring_result.get("summary_score", 0.0)

    _write_mock_structure(predicted_path, mode)
    _write_mock_scores(scores_csv_path, scores_tsv_path, mock_score)

    normalization_summary = _summarize_normalization(normalization)

    summary_payload: MutableMapping[str, Any] = {
        "mode": mode,
        "files": inputs.get("files", {}),
        "config": config.config_dict,
        "cdr_scheme": numbering_scheme,
        "numbering_scheme": numbering_scheme,
        "alignment": alignment_result,
        "binding_site_prediction": binding_site_result,
        "scoring": scoring_result,
        "cdr_annotation": cdr_annotation,
        "target_hotspots_input": hotspot_payload.get("input") if hotspot_payload else None,
        "target_hotspots_resolved": hotspot_payload.get("resolved_summary") if hotspot_payload else None,
        "target_mapping_file": str(hotspot_payload.get("mapping_path")) if hotspot_payload else None,
        "normalization": normalization_summary,
        "integrations": {
            "rfantibody": rfantibody_output,
            "boltzgen": boltzgen_output,
        },
        "artifacts": {
            "target_residue_mapping": str(hotspot_payload.get("mapping_path")) if hotspot_payload else None,
            "target_hotspots_resolved": str(hotspot_payload.get("resolved_path")) if hotspot_payload else None,
        },
    }
    summary_path.write_text(json.dumps(summary_payload, indent=2))

    artifacts = PipelineArtifacts(
        structure=predicted_path,
        scores_csv=scores_csv_path,
        scores_tsv=scores_tsv_path,
        summary_json=summary_path,
        cdr_json=cdr_json_path if cdr_annotation else None,
        cdr_csv=cdr_csv_path if cdr_annotation else None,
        target_residue_mapping=hotspot_payload.get("mapping_path") if hotspot_payload else None,
        target_hotspots_resolved=hotspot_payload.get("resolved_path") if hotspot_payload else None,
        scaffold_standardized=Path(normalization.get("scaffold_standardized"))
        if normalization and normalization.get("scaffold_standardized")
        else None,
        target_standardized=Path(normalization.get("target_standardized"))
        if normalization and normalization.get("target_standardized")
        else None,
        scaffold_hlt=Path(normalization.get("scaffold_hlt_path"))
        if normalization and normalization.get("scaffold_hlt_path")
        else None,
        boltzgen_yaml=Path(normalization.get("boltzgen_yaml"))
        if normalization and normalization.get("boltzgen_yaml")
        else None,
        rfantibody_outputs=rfantibody_output,
        boltzgen_outputs=boltzgen_output,
    )
    return PipelineResult(
        artifacts=artifacts,
        summary_score=mock_score,
        numbering_scheme=numbering_scheme,
        alignment=alignment_result,
        binding_site_prediction=binding_site_result,
        scoring=scoring_result,
        cdr_annotation=cdr_annotation,
        target_hotspots_input=hotspot_payload.get("input") if hotspot_payload else None,
        target_hotspots_resolved=hotspot_payload.get("resolve_result") if hotspot_payload else None,
        target_mapping_file=hotspot_payload.get("mapping_path") if hotspot_payload else None,
        normalization=normalization_summary,
        integration_outputs={"rfantibody": rfantibody_output, "boltzgen": boltzgen_output},
        config={**config.config_dict, "cdr_annotation": cdr_annotation},
    )


def _resolve_numbering_scheme(inputs: Mapping[str, Any]) -> str:
    scheme = inputs.get("numbering_scheme")
    if not scheme:
        scheme = inputs.get("cdr_scheme")
    return str(scheme or "chothia")


def _build_config(
    mode: str, inputs: Mapping[str, Any], numbering_scheme: str
) -> PipelineConfig:
    output_dir = Path(inputs.get("output_dir", Path.cwd() / "outputs"))

    alignment = AlignmentConfig(
        enabled=inputs.get("alignment_enabled", True),
        method=inputs.get("alignment_method", "rmsd_alignment"),
        reference_structure=_maybe_path(inputs.get("reference_structure")),
    )
    binding_site = BindingSiteConfig(
        enabled=inputs.get("binding_site_enabled", True),
        predictor=inputs.get("binding_site_predictor", "p2rank"),
        parameters=inputs.get("binding_site_params", {}),
    )
    scoring = ScoringConfig(
        enabled=inputs.get("scoring_enabled", True),
        model_name=inputs.get("scoring_model", "graph-attention-scoring"),
        weights_path=_maybe_path(inputs.get("scoring_weights")),
        extra_features=inputs.get("scoring_features", {}),
    )

    integration_params = inputs.get("integration") or {}
    rfantibody_params = integration_params.get("rfantibody") or {}
    boltzgen_params = integration_params.get("boltzgen") or {}

    integration = IntegrationConfig(
        rfantibody=RFantibodyIntegrationConfig(
            enabled=rfantibody_params.get("enabled", False),
            use_docker=rfantibody_params.get("use_docker", True),
            docker_image=rfantibody_params.get("docker_image", "rfantibody"),
            num_designs=rfantibody_params.get("num_designs", 20),
            timeout=rfantibody_params.get("timeout", 3600),
            retries=rfantibody_params.get("retries", 1),
        ),
        boltzgen=BoltzgenIntegrationConfig(
            enabled=boltzgen_params.get("enabled", False),
            use_docker=boltzgen_params.get("use_docker", True),
            docker_image=boltzgen_params.get("docker_image", "boltzgen"),
            protocol=boltzgen_params.get("protocol", "nanobody-anything"),
            num_designs=boltzgen_params.get("num_designs", 50),
            timeout=boltzgen_params.get("timeout", 3600),
            retries=boltzgen_params.get("retries", 1),
        ),
    )

    config = PipelineConfig(
        mode=mode,
        output_dir=output_dir,
        cdr_numbering_scheme=numbering_scheme,
        alignment=alignment,
        binding_site=binding_site,
        scoring=scoring,
        keep_intermediates=inputs.get("keep_intermediates", True),
        integration=integration,
    )
    config.config_dict = _serialize_config(config)  # type: ignore[attr-defined]
    return config


def _serialize_config(config: PipelineConfig) -> Dict[str, Any]:
    def _convert(value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {key: _convert(val) for key, val in value.items()}
        return value

    config_dict = asdict(config)
    return {key: _convert(val) for key, val in config_dict.items()}


def _maybe_process_hotspots(
    inputs: Mapping[str, Any],
    output_dir: Path,
    *,
    mapping_override: MappingResultV2 | None = None,
    standardized_override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    user_params = inputs.get("user_params") or {}
    raw_hotspots = user_params.get("target_hotspots")
    if raw_hotspots is None:
        return None

    auth_hotspots = normalize_target_hotspots(raw_hotspots)
    structure_path = _select_structure_for_hotspots(inputs.get("files", {}))
    scope = user_params.get("hotspot_residue_scope", "protein")

    if mapping_override:
        mapping_result_v2 = mapping_override
        mapping_path = output_dir / "target_residue_mapping.json"
        mapping_result_v2.write_json(mapping_path)
    else:
        standardized_path = Path(standardized_override) if standardized_override else structure_path
        standardized = standardize_structure(standardized_path, output_dir)
        mapping_result_v2 = build_residue_mapping_v2(standardized)
        mapping_path = output_dir / "target_residue_mapping.json"
        mapping_result_v2.write_json(mapping_path)

    resolve_result_v2 = resolve_hotspots_v2(auth_hotspots, mapping_result_v2, scope=scope)
    resolved_path = output_dir / "target_hotspots_resolved.json"
    resolve_result_v2.write_json(resolved_path)

    if resolve_result_v2.unmatched:
        errors = []
        for entry in resolve_result_v2.unmatched:
            auth = entry.get("auth", {})
            token = f"{auth.get('chain', '?')}:{auth.get('resi', '?')}{auth.get('ins', '')}"
            reason = entry.get("reason", "unknown")
            hint = entry.get("hint")
            message = f"{token} -> {reason}"
            if hint:
                message += f" (hint: {hint})"
            errors.append(message)
        raise ValueError("Failed to resolve target hotspots: " + "; ".join(errors))

    return {
        "input": [asdict(ref) for ref in auth_hotspots],
        "resolve_result": resolve_result_v2,
        "resolved_summary": resolve_result_v2.to_dict(),
        "mapping_path": mapping_path,
        "resolved_path": resolved_path,
    }


def _design_loops_from_cdr(cdr_payload: Optional[Mapping[str, Any]]) -> list[Dict[str, int | str]]:
    """Extract mapped loops from normalized CDR payload."""

    loops: list[Dict[str, int | str]] = []
    if not cdr_payload or cdr_payload.get("status") != "succeeded":
        return loops

    for cdr in cdr_payload.get("cdr_mappings", []):
        if cdr.get("status") != "mapped":
            continue
        start = cdr.get("label_seq_id_start") or cdr.get("start")
        end = cdr.get("label_seq_id_end") or cdr.get("end")
        if start is None or end is None:
            continue
        name = cdr.get("cdr_name") or cdr.get("name") or "loop"
        loops.append({"cdr_name": name, "label_seq_id_start": int(start), "label_seq_id_end": int(end)})
    return loops


def _summarize_normalization(normalization: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not normalization:
        return None

    fields = [
        "scaffold_standardized",
        "scaffold_mapping_json",
        "scaffold_cdr_annotations",
        "scaffold_cdr_mappings_json",
        "scaffold_hlt_path",
        "scaffold_chain_map_json",
        "boltzgen_yaml",
        "target_standardized",
        "target_mapping_json",
    ]
    summary: Dict[str, Any] = {}
    for key in fields:
        value = normalization.get(key)
        if value is not None:
            summary[key] = str(value)
    if normalization.get("scaffold_cdr_mapping_payload"):
        summary["cdr_mapping"] = normalization.get("scaffold_cdr_mapping_payload")
    return summary


def _run_structure_alignment(
    config: AlignmentConfig, inputs: Mapping[str, Any]
) -> Dict[str, Any]:
    if not config.enabled:
        return {"status": "skipped", "reason": "alignment disabled"}

    return {
        "status": "mocked",
        "method": config.method,
        "reference_structure": str(config.reference_structure) if config.reference_structure else None,
        "notes": "Replace with real structure alignment implementation.",
        "inputs": list(inputs.get("files", {}).keys()),
    }


def _predict_binding_sites(
    config: BindingSiteConfig, inputs: Mapping[str, Any]
) -> Dict[str, Any]:
    if not config.enabled:
        return {"status": "skipped", "reason": "binding-site prediction disabled"}

    return {
        "status": "mocked",
        "predictor": config.predictor,
        "parameters": config.parameters,
        "notes": "Hook up binding-site prediction algorithm here.",
        "inputs": list(inputs.get("files", {}).keys()),
    }


def _score_models(
    config: ScoringConfig, binding_site_result: Mapping[str, Any], inputs: Mapping[str, Any]
) -> Dict[str, Any]:
    if not config.enabled:
        return {
            "status": "skipped",
            "reason": "scoring disabled",
            "summary_score": 0.0,
            "models": [],
        }

    file_count = len(inputs.get("files", {}))
    summary_score = 0.75 + 0.05 * file_count

    return {
        "status": "mocked",
        "model": config.model_name,
        "weights_path": str(config.weights_path) if config.weights_path else None,
        "summary_score": round(summary_score, 3),
        "models": [
            {
                "model_id": "mock_model_1",
                "score": round(summary_score, 3),
                "features_used": list(config.extra_features.keys()),
                "binding_site_source": binding_site_result.get("predictor"),
            }
        ],
        "notes": "Connect your scoring model here.",
    }


def _run_cdr_annotation(
    inputs: Mapping[str, Any],
    numbering_scheme: str,
    json_destination: Path,
    csv_destination: Path,
) -> Dict[str, Any]:
    files = inputs.get("files", {})
    scheme = numbering_scheme or "chothia"
    structure_path = files.get("vhh_file") or files.get("complex_file")

    if not structure_path:
        payload = {
            "status": "skipped",
            "reason": "no VHH structure provided",
            "scheme": scheme,
            "chains": [],
            "abnumber_version": getattr(abnumber, "__version__", "unknown"),
        }
        _write_cdr_outputs(payload, json_destination, csv_destination)
        return payload

    try:
        annotations = annotate_cdrs(structure_path, scheme=scheme)
    except Exception as exc:  # noqa: BLE001
        payload = {
            "status": "failed",
            "error": str(exc),
            "scheme": scheme,
            "chains": [],
            "abnumber_version": getattr(abnumber, "__version__", "unknown"),
        }
        _write_cdr_outputs(payload, json_destination, csv_destination)
        return payload

    annotation_payload = _serialize_cdr_annotation(annotations)
    enriched_payload = {
        **annotation_payload,
        "status": "succeeded",
        "abnumber_version": getattr(abnumber, "__version__", "unknown"),
    }
    _write_cdr_outputs(enriched_payload, json_destination, csv_destination)

    return {
        "status": "succeeded",
        "scheme": annotation_payload["scheme"],
        "chains": annotation_payload["chains"],
        "abnumber_version": getattr(abnumber, "__version__", "unknown"),
        "artifacts": {
            "json": str(json_destination),
            "csv": str(csv_destination),
        },
    }


def _serialize_cdr_annotation(result: CDRAnnotationResult) -> Dict[str, Any]:
    chains = []
    for chain in result.chains:
        chains.append(
            {
                "chain_id": chain.chain_id,
                "sequence": chain.sequence,
                "cdrs": chain.cdrs,
                "numbering": chain.numbering,
            }
        )

    return {
        "scheme": result.scheme,
        "chains": chains,
    }


def _write_cdr_outputs(payload: Mapping[str, Any], json_destination: Path, csv_destination: Path) -> None:
    json_destination.write_text(json.dumps(payload, indent=2))

    lines = ["chain_id,cdr_name,start,end,sequence"]
    for chain in payload.get("chains", []):
        for cdr in chain.get("cdrs", []):
            lines.append(
                f"{chain.get('chain_id','')},{cdr.get('name','')},{cdr.get('start','')},{cdr.get('end','')},{cdr.get('sequence','')}"
            )
    csv_destination.write_text("\n".join(lines) + "\n")


def _write_mock_structure(destination: Path, mode: str) -> None:
    if destination.exists():
        return

    pdb_content = f"""
HEADER    MOCK PREDICTION GENERATED BY pipeline.runner
REMARK    MODE: {mode}
ATOM      1  CA  ALA A   1      11.104  13.207  10.334  1.00 20.00           C
ATOM      2  CA  GLY A   2      12.104  14.207  11.334  1.00 20.00           C
TER
END
""".strip()
    destination.write_text(pdb_content + "\n")


def _write_mock_scores(
    csv_destination: Path, tsv_destination: Path, summary_score: float
) -> None:
    header = "model_id,score,comment\n"
    row = f"mock_model_1,{summary_score:.3f},placeholder score based on inputs\n"
    csv_destination.write_text(header + row)
    tsv_destination.write_text(header.replace(",", "\t") + row.replace(",", "\t"))


def _maybe_path(value: Any) -> Optional[Path]:
    if value is None:
        return None
    return Path(value)


def _select_structure_for_hotspots(files: Mapping[str, Any]) -> Path:
    structure_path = files.get("target_file") or files.get("complex_file") or next(iter(files.values()), None)
    if not structure_path:
        raise ValueError("No structure file available to build hotspot mapping")

    path = Path(structure_path)
    if not path.exists():
        raise ValueError(f"Hotspot structure file does not exist: {path}")

    return path


def _maybe_annotate_cdrs(inputs: Mapping[str, Any], artifacts: CDRArtifacts) -> Optional[Dict[str, Any]]:
    files = inputs.get("files", {})
    cdr_source = files.get("vhh_file") or files.get("complex_file") or next(iter(files.values()), None)

    if not cdr_source:
        return None

    scheme = inputs.get("numbering_scheme", "chothia")
    chain_type = inputs.get("chain_type", "H")
    chain_id = inputs.get("chain_id")

    try:
        result = annotate_cdrs(Path(cdr_source), artifacts.json_path.parent, scheme=scheme, chain_type=chain_type, chain_id=chain_id)
    except Exception as exc:  # noqa: BLE001
        result = {"status": "failed", "reason": str(exc), "scheme": scheme, "chain_type": chain_type}
        artifacts.json_path.write_text(json.dumps(result, indent=2))
        artifacts.csv_path.write_text("name,start,end,length,sequence\n")
    return result
