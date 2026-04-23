from __future__ import annotations
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import scivcd


def test_colorblind_confusable_positive_pair():
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot([0, 1], [0, 1], color='#0072B2', label='A')
    ax.plot([0, 1], [1, 0], color='#0174B3', label='B')
    fig.canvas.draw()
    report = scivcd.check(fig)
    plt.close(fig)
    findings = [f for f in report.findings if f.check_id == 'colorblind_confusable']
    assert findings
    assert 'delta_e' in findings[0].evidence


def test_colorblind_confusable_negative_pair():
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.plot([0, 1], [0, 1], color='#000000', label='A')
    ax.plot([0, 1], [1, 0], color='#F0E442', label='B')
    fig.canvas.draw()
    report = scivcd.check(fig)
    plt.close(fig)
    assert not [f for f in report.findings if f.check_id == 'colorblind_confusable']
