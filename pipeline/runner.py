"""Lightweight runner for orchestrating prediction pipelines.

The module exposes :func:`run_pipeline` as the integration point for worker
jobs. The initial implementation writes mock artifacts but keeps the structure
needed to plug in real components such as structure alignment, binding-site
prediction, and scoring models.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping, Optional

from pipeline.cdr import CDRArtifacts, annotate_cdrs
from pipeline.epitope.mapping import (
    ResolveResult,
    MappingResultV2,
    ResolveResultV2,
    build_residue_mapping,
    build_residue_mapping_v2,
    mapping_v1_from_v2,
    resolve_hotspots,
    resolve_hotspots_v2,
)
from pipeline.epitope.standardize import standardize_structure
from pipeline.epitope.spec import normalize_target_hotspots


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
class PipelineConfig:
    """Top-level configuration passed to the pipeline runner."""

    mode: str
    output_dir: Path
    cdr_numbering_scheme: str = "chothia"
    alignment: AlignmentConfig = field(default_factory=AlignmentConfig)
    binding_site: BindingSiteConfig = field(default_factory=BindingSiteConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    keep_intermediates: bool = True


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
    target_residue_mapping_v2: Optional[Path] = None
    target_hotspots_resolved_v2: Optional[Path] = None


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
    target_hotspots_resolved: Optional[ResolveResult | ResolveResultV2]
    target_mapping_file: Optional[Path]
    config: Dict[str, Any]
    target_hotspots_resolved_v2: Optional[ResolveResultV2] = None
    target_mapping_file_v2: Optional[Path] = None


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

    numbering_scheme = _resolve_numbering_scheme(inputs)
    config = _build_config(mode, inputs, numbering_scheme)
    config.output_dir.mkdir(parents=True, exist_ok=True)

    predicted_path = config.output_dir / "predicted.pdb"
    scores_csv_path = config.output_dir / "scores.csv"
    scores_tsv_path = config.output_dir / "scores.tsv"
    summary_path = config.output_dir / "pipeline_summary.json"
    cdr_json_path = config.output_dir / "cdr_annotations.json"
    cdr_csv_path = config.output_dir / "cdr_annotations.csv"

    alignment_result = _run_structure_alignment(config.alignment, inputs)
    binding_site_result = _predict_binding_sites(config.binding_site, inputs)
    scoring_result = _score_models(config.scoring, binding_site_result, inputs)
    cdr_annotation = _maybe_annotate_cdrs(inputs, CDRArtifacts(cdr_json_path, cdr_csv_path))
    hotspot_payload = _maybe_process_hotspots(inputs, config.output_dir)

    mock_score = scoring_result.get("summary_score", 0.0)

    _write_mock_structure(predicted_path, mode)
    _write_mock_scores(scores_csv_path, scores_tsv_path, mock_score)

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
        "target_mapping_file": str(hotspot_payload.get("mapping_path_v2")) if hotspot_payload else None,
        "artifacts": {
            "structure": str(predicted_path),
            "scores_csv": str(scores_csv_path),
            "scores_tsv": str(scores_tsv_path),
            "cdr_json": str(cdr_json_path) if cdr_annotation else None,
            "cdr_csv": str(cdr_csv_path) if cdr_annotation else None,
            "target_residue_mapping": str(hotspot_payload.get("mapping_path")) if hotspot_payload else None,
            "target_hotspots_resolved": str(hotspot_payload.get("resolved_path")) if hotspot_payload else None,
            "target_residue_mapping_v2": str(hotspot_payload.get("mapping_path_v2")) if hotspot_payload else None,
            "target_hotspots_resolved_v2": str(hotspot_payload.get("resolved_path_v2")) if hotspot_payload else None,
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
        target_residue_mapping_v2=hotspot_payload.get("mapping_path_v2") if hotspot_payload else None,
        target_hotspots_resolved_v2=hotspot_payload.get("resolved_path_v2") if hotspot_payload else None,
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
        target_hotspots_resolved=hotspot_payload.get("resolve_result_v2") if hotspot_payload else None,
        target_mapping_file=hotspot_payload.get("mapping_path_v2") if hotspot_payload else None,
        target_hotspots_resolved_v2=hotspot_payload.get("resolve_result_v2") if hotspot_payload else None,
        target_mapping_file_v2=hotspot_payload.get("mapping_path_v2") if hotspot_payload else None,
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

    config = PipelineConfig(
        mode=mode,
        output_dir=output_dir,
        cdr_numbering_scheme=numbering_scheme,
        alignment=alignment,
        binding_site=binding_site,
        scoring=scoring,
        keep_intermediates=inputs.get("keep_intermediates", True),
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


def _maybe_process_hotspots(inputs: Mapping[str, Any], output_dir: Path) -> Optional[Dict[str, Any]]:
    user_params = inputs.get("user_params") or {}
    raw_hotspots = user_params.get("target_hotspots")
    if raw_hotspots is None:
        return None

    auth_hotspots = normalize_target_hotspots(raw_hotspots)
    structure_path = _select_structure_for_hotspots(inputs.get("files", {}))
    scope = user_params.get("hotspot_residue_scope", "protein")

    standardized = standardize_structure(structure_path, output_dir)
    mapping_result_v2 = build_residue_mapping_v2(standardized)
    mapping_path_v2 = output_dir / "target_residue_mapping_v2.json"
    mapping_result_v2.write_json(mapping_path_v2)

    # legacy mapping for backward compatibility
    mapping_result = mapping_v1_from_v2(mapping_result_v2)
    mapping_path = output_dir / "target_residue_mapping.json"
    mapping_result.write_json(mapping_path)

    resolve_result_v2 = resolve_hotspots_v2(auth_hotspots, mapping_result_v2, scope=scope)
    resolved_path_v2 = output_dir / "target_hotspots_resolved_v2.json"
    resolve_result_v2.write_json(resolved_path_v2)

    resolve_result = resolve_hotspots(auth_hotspots, mapping_result)
    resolved_path = output_dir / "target_hotspots_resolved.json"
    resolve_result.write_json(resolved_path)

    if resolve_result_v2.unmatched:
        raise ValueError(
            "Failed to resolve target hotspots: "
            + "; ".join(entry.get("reason", "unknown") for entry in resolve_result_v2.unmatched)
        )

    return {
        "input": [asdict(ref) for ref in auth_hotspots],
        "resolve_result": resolve_result,
        "resolve_result_v2": resolve_result_v2,
        "resolved_summary": resolve_result_v2.to_dict(),
        "mapping_path": mapping_path,
        "resolved_path": resolved_path,
        "mapping_path_v2": mapping_path_v2,
        "resolved_path_v2": resolved_path_v2,
    }


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
