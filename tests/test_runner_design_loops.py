from integrations.rfantibody import _format_design_loops_for_rf
from pipeline.runner import _design_loops_from_cdr


def test_design_loops_from_cdr_mapping_payload():
    payload = {
        "status": "succeeded",
        "cdr_mappings": [
            {"cdr_name": "H3", "status": "mapped", "label_seq_id_start": 5, "label_seq_id_end": 13},
            {"cdr_name": "L1", "status": "failed"},
        ],
    }

    loops = _design_loops_from_cdr(payload)
    assert loops == [{"cdr_name": "H3", "label_seq_id_start": 5, "label_seq_id_end": 13}]
    formatted = _format_design_loops_for_rf(loops)
    assert formatted == "H3:5-13"
