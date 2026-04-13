"""
Chart builder — converts DuckDB query results into Plotly JSON specs.
All charts use a dark theme compatible with the frontend.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import duckdb

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Colour palette (dark theme)
# ---------------------------------------------------------------------------

_INDIGO = "#6366f1"
_CYAN = "#22d3ee"
_AMBER = "#f59e0b"
_EMERALD = "#10b981"
_ROSE = "#f43f5e"
_VIOLET = "#8b5cf6"
_SKY = "#0ea5e9"
_PINK = "#ec4899"
_TEAL = "#14b8a6"
_ORANGE = "#f97316"

_PALETTE = [_INDIGO, _CYAN, _AMBER, _EMERALD, _ROSE, _VIOLET, _SKY, _PINK, _TEAL, _ORANGE]

# ---------------------------------------------------------------------------
# Shared layout template
# ---------------------------------------------------------------------------

_BASE_LAYOUT: dict[str, Any] = {
    "paper_bgcolor": "#0f172a",
    "plot_bgcolor": "#1e293b",
    "font": {"color": "#94a3b8", "family": "Inter, ui-sans-serif, sans-serif", "size": 12},
    "xaxis": {
        "gridcolor": "#334155",
        "zerolinecolor": "#475569",
        "linecolor": "#334155",
        "tickfont": {"color": "#94a3b8"},
        "titlefont": {"color": "#cbd5e1"},
    },
    "yaxis": {
        "gridcolor": "#334155",
        "zerolinecolor": "#475569",
        "linecolor": "#334155",
        "tickfont": {"color": "#94a3b8"},
        "titlefont": {"color": "#cbd5e1"},
    },
    "margin": {"t": 55, "r": 30, "b": 65, "l": 70},
    "hoverlabel": {
        "bgcolor": "#1e293b",
        "bordercolor": "#475569",
        "font": {"color": "#f1f5f9"},
    },
    "legend": {
        "font": {"color": "#94a3b8"},
        "bgcolor": "rgba(0,0,0,0)",
        "bordercolor": "#334155",
    },
}


def _layout(title: str, extra: dict | None = None) -> dict:
    base = {
        **_BASE_LAYOUT,
        "title": {"text": title, "font": {"color": "#e2e8f0", "size": 15}},
    }
    if extra:
        base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def build_plotly_spec(
    rows: list[dict[str, Any]],
    chart_type: str,
    title: str,
    x_col: str | None,
    y_col: str | None,
) -> dict[str, Any]:
    """Build a Plotly JSON spec from query rows."""
    if not rows:
        return _empty(title)

    try:
        ct = chart_type.lower()
        if ct in ("bar", "histogram"):
            return _bar(rows, x_col, y_col, title)
        elif ct == "line":
            return _line(rows, x_col, y_col, title)
        elif ct == "scatter":
            return _scatter(rows, x_col, y_col, title)
        elif ct == "pie":
            return _pie(rows, x_col, y_col, title)
        elif ct == "heatmap":
            return _heatmap(rows, title)
        elif ct == "box":
            return _box(rows, x_col, y_col, title)
        else:
            return _bar(rows, x_col, y_col, title)
    except Exception as exc:
        logger.warning("Chart build failed for '%s': %s", title, exc)
        return _empty(title)


# ---------------------------------------------------------------------------
# Chart-type builders
# ---------------------------------------------------------------------------


def _bar(rows, x_col, y_col, title) -> dict:
    x_vals = [str(r.get(x_col, "")) for r in rows]
    y_vals = [_num(r.get(y_col)) for r in rows]
    return {
        "data": [{
            "type": "bar",
            "x": x_vals,
            "y": y_vals,
            "marker": {
                "color": _INDIGO,
                "opacity": 0.85,
                "line": {"color": "#818cf8", "width": 0.5},
            },
            "hovertemplate": f"<b>%{{x}}</b><br>{y_col or 'value'}: %{{y:,.2f}}<extra></extra>",
        }],
        "layout": {
            **_layout(title),
            "xaxis": {**_BASE_LAYOUT["xaxis"], "title": {"text": x_col or ""}},
            "yaxis": {**_BASE_LAYOUT["yaxis"], "title": {"text": y_col or "Count"}},
        },
    }


def _line(rows, x_col, y_col, title) -> dict:
    x_vals = [str(r.get(x_col, "")) for r in rows]
    y_vals = [_num(r.get(y_col)) for r in rows]
    return {
        "data": [{
            "type": "scatter",
            "mode": "lines+markers",
            "x": x_vals,
            "y": y_vals,
            "line": {"color": _CYAN, "width": 2.5},
            "marker": {"color": _CYAN, "size": 5},
            "fill": "tozeroy",
            "fillcolor": "rgba(34,211,238,0.06)",
            "hovertemplate": f"%{{x}}<br>{y_col or 'value'}: %{{y:,.2f}}<extra></extra>",
        }],
        "layout": {
            **_layout(title),
            "xaxis": {**_BASE_LAYOUT["xaxis"], "title": {"text": x_col or ""}},
            "yaxis": {**_BASE_LAYOUT["yaxis"], "title": {"text": y_col or ""}},
        },
    }


def _scatter(rows, x_col, y_col, title) -> dict:
    x_vals = [_num(r.get(x_col)) for r in rows]
    y_vals = [_num(r.get(y_col)) for r in rows]
    return {
        "data": [{
            "type": "scatter",
            "mode": "markers",
            "x": x_vals,
            "y": y_vals,
            "marker": {
                "color": _AMBER,
                "opacity": 0.45,
                "size": 5,
                "line": {"color": "rgba(0,0,0,0)"},
            },
            "hovertemplate": f"{x_col}: %{{x}}<br>{y_col}: %{{y}}<extra></extra>",
        }],
        "layout": {
            **_layout(title),
            "xaxis": {**_BASE_LAYOUT["xaxis"], "title": {"text": x_col or ""}},
            "yaxis": {**_BASE_LAYOUT["yaxis"], "title": {"text": y_col or ""}},
        },
    }


def _pie(rows, x_col, y_col, title) -> dict:
    top = rows[:12]
    labels = [str(r.get(x_col, "")) for r in top]
    values = [_num(r.get(y_col)) for r in top]
    return {
        "data": [{
            "type": "pie",
            "labels": labels,
            "values": values,
            "hole": 0.36,
            "marker": {"colors": _PALETTE[:len(labels)]},
            "textfont": {"color": "#e2e8f0"},
            "hovertemplate": "<b>%{label}</b><br>%{value:,.0f} (%{percent})<extra></extra>",
        }],
        "layout": _layout(title, {"showlegend": True}),
    }


def _heatmap(rows, title) -> dict:
    """Expect rows: [{col_a, col_b, correlation}]."""
    if not rows:
        return _empty(title)

    cols_a = sorted({str(r.get("col_a", "")) for r in rows})
    cols_b = sorted({str(r.get("col_b", "")) for r in rows})
    idx_a = {c: i for i, c in enumerate(cols_a)}
    idx_b = {c: i for i, c in enumerate(cols_b)}

    matrix = [[None] * len(cols_b) for _ in cols_a]
    for r in rows:
        i = idx_a.get(str(r.get("col_a", "")))
        j = idx_b.get(str(r.get("col_b", "")))
        if i is not None and j is not None:
            matrix[i][j] = _num(r.get("correlation"))

    return {
        "data": [{
            "type": "heatmap",
            "x": cols_b,
            "y": cols_a,
            "z": matrix,
            "colorscale": [[0, _ROSE], [0.5, "#1e293b"], [1, _CYAN]],
            "zmid": 0,
            "zmin": -1,
            "zmax": 1,
            "hoverongaps": False,
            "hovertemplate": "%{y} × %{x}<br>r = %{z:.3f}<extra></extra>",
        }],
        "layout": _layout(title, {"xaxis": {**_BASE_LAYOUT["xaxis"], "side": "bottom"}}),
    }


def _box(rows, x_col, y_col, title) -> dict:
    categories = list({str(r.get(x_col, "Unknown")) for r in rows})
    traces = []
    for i, cat in enumerate(categories[:10]):
        vals = [_num(r.get(y_col)) for r in rows if str(r.get(x_col, "")) == cat]
        traces.append({
            "type": "box",
            "name": cat,
            "y": vals,
            "marker": {"color": _PALETTE[i % len(_PALETTE)]},
            "boxmean": True,
        })
    return {
        "data": traces,
        "layout": {
            **_layout(title, {"boxmode": "group"}),
            "yaxis": {**_BASE_LAYOUT["yaxis"], "title": {"text": y_col or ""}},
        },
    }


def _empty(title: str) -> dict:
    return {
        "data": [],
        "layout": {
            **_layout(title),
            "annotations": [{
                "text": "No data available",
                "showarrow": False,
                "font": {"size": 14, "color": "#64748b"},
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
            }],
        },
    }


# ---------------------------------------------------------------------------
# Correlation matrix helper
# ---------------------------------------------------------------------------


def build_correlation_heatmap(
    conn: "duckdb.DuckDBPyConnection",
    table: str,
    numeric_cols: list[str],
    max_cols: int = 10,
) -> dict[str, Any] | None:
    """Compute pairwise Pearson correlations in DuckDB and return heatmap spec."""
    from .duckdb_tool import execute_query

    cols = [c for c in numeric_cols if c][:max_cols]
    if len(cols) < 2:
        return None

    corr_rows: list[dict] = []
    for i, col_a in enumerate(cols):
        for col_b in cols[i:]:
            try:
                sql = f"""
                    SELECT
                        '{col_a}'  AS col_a,
                        '{col_b}'  AS col_b,
                        CORR("{col_a}", "{col_b}") AS correlation
                    FROM {table}
                    WHERE "{col_a}" IS NOT NULL AND "{col_b}" IS NOT NULL
                """
                result = execute_query(conn, sql, max_rows=1)
                if result and result[0].get("correlation") is not None:
                    corr_rows.append(result[0])
                    if col_a != col_b:
                        corr_rows.append({
                            "col_a": col_b,
                            "col_b": col_a,
                            "correlation": result[0]["correlation"],
                        })
            except Exception as exc:
                logger.debug("Correlation failed for %s×%s: %s", col_a, col_b, exc)

    if not corr_rows:
        return None

    return _heatmap(corr_rows, "Correlation Matrix")


# ---------------------------------------------------------------------------
# Util
# ---------------------------------------------------------------------------


def _num(val: Any) -> float:
    if val is None:
        return 0.0
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0
