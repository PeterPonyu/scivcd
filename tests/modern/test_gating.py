from __future__ import annotations
import json
from scivcd.gating import GatePolicy, diff_reports, finding_fingerprint, gate_report


def _finding(msg='Value 1.234', sev='HIGH'):
    return {'check_id': 'x.check', 'severity': sev, 'message': msg, 'evidence': {'source_artifact': 'fig.png', 'semantic_id': 'series:a'}}


def test_fingerprint_stable_under_numeric_noise():
    assert finding_fingerprint(_finding('Value 1.234')) == finding_fingerprint(_finding('Value 9.876'))


def test_diff_reports_new_resolved_persistent():
    base = {'findings': [_finding('A 1', 'HIGH'), {'check_id':'old','severity':'LOW','message':'old'}]}
    cur = {'findings': [_finding('A 2', 'HIGH'), {'check_id':'new','severity':'LOW','message':'new'}]}
    diff = diff_reports(cur, base)
    assert len(diff['persistent']) == 1
    assert len(diff['new']) == 1
    assert len(diff['resolved']) == 1


def test_gate_report_fails_on_new_high():
    result = gate_report({'findings': [_finding(sev='HIGH')]}, {'findings': []}, GatePolicy())
    assert result['exit_code'] == 1


def test_gate_policy_from_pyproject(tmp_path):
    p = tmp_path / 'pyproject.toml'
    p.write_text('[tool.scivcd.gate]\nfail_on=["BLOCKER"]\nrequire_export_audit=true\n')
    pol = GatePolicy.from_pyproject(p)
    assert pol.fail_on == ['BLOCKER']
    assert pol.require_export_audit is True
