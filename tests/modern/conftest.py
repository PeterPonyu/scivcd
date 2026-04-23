"""Shared pytest fixtures for the scivcd test suite.

All fixtures produce synthetic matplotlib figures — no external data files.
Figures are closed after each test via ``plt.close(fig)`` in teardown.
"""

from __future__ import annotations

import matplotlib
matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.lines as mlines
import numpy as np
import pytest


@pytest.fixture()
def small_fig():
    """A minimal single-axes figure with one plotted line."""
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1, 2], [0, 1, 0], label="series")
    ax.set_xlabel("X")
    ax.set_ylabel("Y")
    ax.set_title("Small figure")
    yield fig
    plt.close(fig)


@pytest.fixture()
def multi_panel_fig():
    """A 2×2 grid figure — four axes, each with a simple line."""
    fig, axs = plt.subplots(2, 2, figsize=(8, 6))
    for i, ax in enumerate(axs.flat):
        ax.plot([0, 1, 2], [i, i + 1, i], label=f"s{i}")
        ax.set_title(f"Panel {i}")
    yield fig
    plt.close(fig)


@pytest.fixture()
def fig_with_overlap():
    """Figure containing a Text artist that visually overlaps a Line2D.

    The text is placed exactly at (0.5, 0.5) in axes coordinates and the
    diagonal line also passes through that point, so any bounding-box
    overlap test on the centre of the axes will fire.
    """
    fig, ax = plt.subplots(figsize=(4, 4))
    # Diagonal line through the centre of the axes
    ax.plot([0, 1], [0, 1], color="black", lw=2)
    # Text parked on top of that line at mid-axes
    ax.text(
        0.5,
        0.5,
        "Overlapping label",
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=14,
    )
    fig.canvas.draw()
    yield fig
    plt.close(fig)


@pytest.fixture()
def clean_fig():
    """A figure designed to produce zero scivcd findings.

    - Single axes, no annotations
    - Adequate margins, legible font sizes
    - No overlapping artists
    """
    fig, ax = plt.subplots(figsize=(6, 4))
    x = np.linspace(0, 2 * np.pi, 100)
    ax.plot(x, np.sin(x), lw=1.5)
    ax.set_xlabel("x", fontsize=11)
    ax.set_ylabel("sin(x)", fontsize=11)
    ax.set_title("Clean figure", fontsize=12)
    fig.tight_layout()
    yield fig
    plt.close(fig)
