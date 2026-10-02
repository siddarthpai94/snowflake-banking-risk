"""Every chart in the app, drawn with Plotly so each one shares the same hover card: a dark panel with a heading,
the headline number, then one row per part with its colour key, a small bar, the value and its share.

Charts are display only; the numbers come from the same queries as before.
"""
import html

import pandas as pd
import plotly.graph_objects as go

import ui

CARD_BG = "#111a2e"
BAR_ON, BAR_OFF = "#8fb3ff", "#34405a"
SUB = "#9fb0d0"
CONFIG = {"displayModeBar": False, "responsive": True}


def _e(x):
    return html.escape(str(x))


def mini_bar(share, width=10):
    """A small bar for the hover card, drawn with block characters (share 0..1)."""
    share = max(0.0, min(1.0, float(share or 0)))
    on = int(round(share * width))
    return (f'<span style="color:{BAR_ON}">{"▬" * on}</span>'
            f'<span style="color:{BAR_OFF}">{"▬" * (width - on)}</span>')


def _money(x):
    return f"${float(x):,.0f}"


def style(fig, height=300, unified=False):
    fig.update_layout(
        height=height, margin=dict(l=8, r=16, t=28, b=8), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=f"{ui.FONT}, sans-serif", size=12, color=ui.MUTED),
        hoverlabel=dict(bgcolor=CARD_BG, bordercolor=CARD_BG, align="left",
                        font=dict(family=f"{ui.FONT}, sans-serif", size=13, color="#ffffff")),
        hovermode="x unified" if unified else "closest", showlegend=unified,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title=None,
                    font=dict(color=ui.INK, size=12), traceorder="reversed"),
        bargap=0.35)
    fig.update_xaxes(showspikes=unified, spikecolor="#9aa7bd", spikethickness=1, spikedash="dot", spikemode="across",
                     showline=True, linecolor="#c9d2e0", gridcolor="#edf0f5", zeroline=False, tickfont=dict(size=12),
                     title_font=dict(size=12, color=ui.MUTED))
    fig.update_yaxes(gridcolor="#edf0f5", zeroline=False, tickfont=dict(size=12), title_font=dict(size=12, color=ui.MUTED))
    return fig


def _header(fig, days, text):
    """The card's headline row. Unified hover lists traces bottom-up, so this invisible trace goes last."""
    fig.add_trace(go.Scatter(x=days, y=[0] * len(days), mode="markers", marker=dict(opacity=0, size=1),
                             showlegend=False, hovertemplate="%{text}<extra></extra>", text=text, name=""))


def hbar(df, label, value, axis_title, color=None, unit=None):
    """Ranking: sorted horizontal bars with value labels; hover shows the item, its value, share and rank."""
    d = df[[label, value]].copy()
    d[value] = d[value].astype(float)
    d = d.sort_values(value, ascending=True)
    total = float(d[value].sum()) or 1.0
    n = len(d)
    unit = unit or axis_title.lower()
    d["share"] = d[value] / total
    d["rank"] = d[value].rank(ascending=False, method="min").astype(int)
    hover = [f'<span style="font-size:12px;color:{SUB}">{_e(axis_title)}</span><br>'
             f'<b style="font-size:13px">{_e(r[label])}</b><br>'
             f'<b style="font-size:16px">{r[value]:,.0f}</b> <span style="color:{SUB}">{_e(unit)}</span><br>'
             f'<span style="color:{SUB}">Rank {r["rank"]} of {n} · {total:,.0f} in all</span><br>'
             f'{mini_bar(r["share"])}  <b>{r["share"] * 100:.1f}%</b> <span style="color:{SUB}">of the total</span>'
             for _, r in d.iterrows()]
    fig = go.Figure(go.Bar(
        x=d[value], y=d[label], orientation="h", marker=dict(color=color or ui.ACCENT, cornerradius=4),
        text=[f"{v:,.0f}" for v in d[value]], textposition="outside", cliponaxis=False,
        textfont=dict(color=ui.INK, size=12), hovertext=hover, hoverinfo="text"))
    fig.update_xaxes(title_text=axis_title, range=[0, float(d[value].max() or 1) * 1.15], showline=False)
    fig.update_yaxes(showgrid=False, ticksuffix="  ", tickfont=dict(color=ui.INK))
    return style(fig, height=max(170, 34 * n + 70))


def daily_cash(cash, ctr_threshold):
    """Cash deposited per day, stacked by core, against the CTR line. Hover: the day's total and each core's part."""
    d = cash.copy()
    d["day"] = pd.to_datetime(d["posted_at"]).dt.normalize()
    d["amount_usd"] = d["amount_usd"].astype(float)
    cores = [("core_a", "Core A", ui.CORE_A), ("core_b", "Core B", ui.CORE_B)]
    days = sorted(d["day"].unique())
    piv = d.pivot_table(index="day", columns="source_system", values="amount_usd", aggfunc="sum").reindex(days).fillna(0)
    cnt = d.pivot_table(index="day", columns="source_system", values="amount_usd", aggfunc="count").reindex(days).fillna(0)
    ctr = d.groupby("day")["ctr_filed"].apply(lambda s: bool(pd.Series(s).fillna(False).astype(bool).any())).reindex(days)
    total = piv.sum(axis=1)

    fig = go.Figure()
    # first row of the card: the day's total, and whether it crossed the CTR line
    head = [f'<b style="font-size:16px">{_money(t)}</b> <span style="color:{SUB}">cash deposited</span><br>'
            f'<span style="color:{SUB}">CTR threshold {_money(ctr_threshold)}'
            + (f' · over by {_money(t - ctr_threshold)}' if t > ctr_threshold else '') + '</span><br>'
            + ('<span style="color:#86efac">CTR filed</span>' if ctr[day] else
               ('<span style="color:#fca5a5"><b>No CTR filed</b></span>' if t > ctr_threshold else
                f'<span style="color:{SUB}">Under the threshold</span>'))
            for day, t in total.items()]
    for key, name, col in reversed(cores):
        vals = piv[key] if key in piv else pd.Series(0.0, index=days)
        n = cnt[key] if key in cnt else pd.Series(0, index=days)
        rows = [f'{name}  {mini_bar(v / t if t else 0)}  <b>{_money(v)}</b>  '
                f'<span style="color:{SUB}">{(v / t * 100 if t else 0):.1f}% · {int(k)} deposit{"s" if k != 1 else ""}</span>'
                for v, t, k in zip(vals, total, n)]
        fig.add_trace(go.Bar(x=days, y=vals, name=name, marker=dict(color=col, cornerradius=3),
                             hovertemplate="%{text}<extra></extra>", text=rows, textposition="none"))
    _header(fig, days, head)
    fig.add_hline(y=ctr_threshold, line=dict(color=ui.RED, dash="dash", width=1.5),
                  annotation_text=f"CTR threshold {_money(ctr_threshold)} per person per day",
                  annotation_position="top right", annotation_font=dict(color=ui.RED, size=12),
                  annotation_bgcolor="rgba(255,255,255,.85)")
    for day, t in total.items():
        if t > ctr_threshold and not ctr[day] and piv.loc[day].gt(0).sum() >= 2:
            fig.add_annotation(x=day, y=t, text="<b>No CTR filed</b>", showarrow=False, yshift=12,
                               font=dict(color=ui.RED, size=12))
    fig.update_layout(barmode="stack")
    fig.update_xaxes(tickformat="%d %b", hoverformat="%A, %d %b %Y", showgrid=False)
    fig.update_yaxes(title_text="Cash deposited that day", tickformat="$,.0f",
                     range=[0, max(float(total.max()), ctr_threshold) * 1.22])
    return style(fig, height=300, unified=True)


def running_cash(cash, per_core_rule, cross_core_rule):
    """Running total of cash per core and for both cores, against each core's legacy rule and the cross-core rule."""
    d = cash.copy()
    d["day"] = pd.to_datetime(d["posted_at"]).dt.normalize()
    d["amount_usd"] = d["amount_usd"].astype(float)
    days = sorted(d["day"].unique())
    piv = d.pivot_table(index="day", columns="source_system", values="amount_usd", aggfunc="sum").reindex(days).fillna(0)
    run = piv.cumsum()
    both = run.sum(axis=1)

    fig = go.Figure()
    head = [f'<b style="font-size:16px">{_money(b)}</b> <span style="color:{SUB}">in both cores so far</span><br>'
            f'<span style="color:{SUB}">Cross-core rule {_money(cross_core_rule)} · '
            + (f'<span style="color:#fca5a5"><b>crossed</b></span>' if b >= cross_core_rule
               else f'{_money(cross_core_rule - b)} to go') + '</span>'
            for b in both]
    lines = [("core_a", "Core A", ui.CORE_A, per_core_rule, "its legacy rule"),
             ("core_b", "Core B", ui.CORE_B, per_core_rule, "its legacy rule"),
             (None, "Both cores", ui.BOTH, cross_core_rule, "the cross-core rule")]
    for key, name, col, rule, rule_name in reversed(lines):
        y = both if key is None else (run[key] if key in run else pd.Series(0.0, index=days))
        rows = [f'{name}  {mini_bar(v / rule)}  <b>{_money(v)}</b>  '
                f'<span style="color:{SUB}">{v / rule * 100:.0f}% of {rule_name}</span>' for v in y]
        fig.add_trace(go.Scatter(x=days, y=y, name=name, mode="lines+markers", line=dict(color=col, width=3, shape="hv"),
                                 marker=dict(size=7, color=col), hovertemplate="%{text}<extra></extra>", text=rows))
    _header(fig, days, head)
    fig.add_hline(y=per_core_rule, line=dict(color=ui.GREY, dash="dash", width=1.5),
                  annotation_text=f"Each core's legacy alert rule {_money(per_core_rule)} in 30 days",
                  annotation_position="bottom left", annotation_font=dict(color=ui.GREY, size=12), annotation_bgcolor="rgba(255,255,255,.85)")
    fig.add_hline(y=cross_core_rule, line=dict(color=ui.RED, dash="dash", width=1.5),
                  annotation_text=f"Cross-core rule {_money(cross_core_rule)} in 30 days",
                  annotation_position="top left", annotation_font=dict(color=ui.RED, size=12),
                  annotation_bgcolor="rgba(255,255,255,.85)")
    fig.update_xaxes(tickformat="%d %b", hoverformat="%A, %d %b %Y", showgrid=False)
    fig.update_yaxes(title_text="Running total of cash", tickformat="$,.0f",
                     range=[0, max(float(both.max()), cross_core_rule) * 1.15])
    return style(fig, height=300, unified=True)
