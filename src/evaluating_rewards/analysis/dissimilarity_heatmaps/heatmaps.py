# Copyright 2019, 2020 DeepMind Technologies Limited, Adam Gleave
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#            http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Helper methods for plotting dissimilarity heatmaps."""

import functools
import math
from typing import Any, Callable, Dict, Iterable, Mapping, Optional

from matplotlib import pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from evaluating_rewards import serialize
from evaluating_rewards.analysis import results
from evaluating_rewards.analysis.dissimilarity_heatmaps import reward_masks, transformations


def short_e(x: float, precision: int = 2) -> str:
    """Formats 1.2345 as 1.2e-1, rather than Python 1.2e-01."""
    if not math.isfinite(x):
        return str(x)
    fmt = "{:." + str(precision) + "e}"
    formatted = fmt.format(x)
    base, exponent = formatted.split("e")
    exponent = int(exponent)
    return f"{base}e{exponent}"


def horizontal_ticks() -> None:
    plt.xticks(rotation="horizontal")
    plt.yticks(rotation="horizontal")


def _drop_zero_reward(s: pd.Series) -> pd.Series:
    """Exclude rows for Zero source reward type."""
    zero_source = s.index.get_level_values("source_reward_type") == serialize.ZERO_REWARD
    return s[~zero_source]


def comparison_heatmap(
    vals: pd.Series,
    ax: plt.Axes,
    log: bool = True,
    fmt: Callable[[float], str] = short_e,
    cbar_kws: Optional[Dict[str, Any]] = None,
    cmap: str = "GnBu",
    robust: bool = False,
    preserve_order: bool = False,
    label_fstr: Optional[str] = None,
    normalize: bool = False,
    mask: Optional[pd.Series] = None,
    **kwargs,
) -> None:
    """Plot a heatmap, with target_reward_type as x-axis and remainder as y-axis.

    This is intended for plotting the output of `model_comparison.py` runs,
    comparing models on the y-axis to those on the x-axis. Values visualized may
    include loss, other distance measures and scale transformations.

    Args:
        vals: The values to visualize.
        log: log-10 scale for the values if True.
        fmt: format string for annotated values.
        cmap: color map.
        robust: If true, set vmin and vmax to 25th and 75th quantiles.
            This makes the color scale robust to outliers, but will compress it
            more than is desirable if the data does not contain outliers.
        preserve_order: If True, retains the same order as the input index
            after rewriting the index values for readability. If false,
            sorts the rewritten values alphabetically.
        label_fstr: Format string to use for the label for the colorbar legend.` {args}` is
            replaced with arguments to distance and `{transform_start}` and `{transform_end}`
            is replaced with any transformations of the distance (e.g. log).
        normalize: If True, divides by distance from Zero reward to target, rescaling
            all values between 0 and 1. (Values may exceed 1 due to optimisation error.)
        mask: If provided, only display cells where mask is True.
        **kwargs: passed through to sns.heatmap.
    """
    if normalize:
        vals = vals / vals.loc[serialize.ZERO_REWARD]
        vals = _drop_zero_reward(vals)
        if mask is not None:
            mask = _drop_zero_reward(mask)

    vals = transformations.index_reformat(vals, preserve_order)
    if mask is not None:
        mask = transformations.index_reformat(mask, preserve_order)

    data = np.log10(vals) if log else vals
    annot = vals.applymap(fmt)
    cbar_kws = dict(cbar_kws or {})

    if label_fstr is None:
        label_fstr = "{transform_start}D({args}){transform_end}"
    transform_start = r"\log_{10}\left(" if log else ""
    transform_end = r"\right)" if log else ""
    label = label_fstr.format(
        transform_start=transform_start, args="R_S,R_T", transform_end=transform_end
    )
    cbar_kws.setdefault("label", f"${label}$")

    if robust:
        flat = data.values.flatten()
        kwargs["vmin"], kwargs["vmax"] = np.quantile(flat, [0.25, 0.75])
    sns.heatmap(
        data, annot=annot, fmt="s", cmap=cmap, cbar_kws=cbar_kws, mask=mask, ax=ax, **kwargs
    )

    ax.set_xlabel(r"Target $R_T$")
    ax.set_ylabel(r"Source $R_S$")


def median_seeds(series: pd.Series) -> pd.Series:
    """Take the median over any seeds in a series."""
    seeds = [name for name in series.index.names if "seed" in name]
    if seeds:
        non_seeds = [name for name in series.index.names if name not in seeds]
        series = series.groupby(non_seeds).median()
    return series


def compact(series: pd.Series) -> pd.Series:
    """Make series smaller, suitable for e.g. small figures."""
    series = median_seeds(series)
    if "target_reward_type" in series.index.names:
        targets = series.index.get_level_values("target_reward_type")
        series = series.loc[targets != serialize.ZERO_REWARD]
    return series


short_fmt = functools.partial(short_e, precision=1)


def compact_heatmaps(
    dissimilarity: pd.Series,
    masks: Mapping[str, Iterable[results.FilterFn]],
    order: Optional[Iterable[str]] = None,
    fmt: Callable[[float], str] = short_fmt,
    after_plot: Callable[[], None] = lambda: None,
    **kwargs: Dict[str, Any],
) -> Mapping[str, plt.Figure]:
    """Plots a series of compact heatmaps, suitable for presentations.

    Args:
        dissimilarity: The loss between source and target.
                The index should consist of target_reward_type, one of
                source_reward_{type,path}, and any number of seed indices.
                source_reward_path, if present, is rewritten into source_reward_type
                and a seed index.
        order: The order to plot the source and reward types.
        masks: A mapping from strings to collections of filter functions. Any
                (source, reward) pair not matching one of these filters is masked
                from the figure.
        fmt: A Callable mapping losses to strings to annotate cells in heatmap.
        after_plot: Called after plotting, for environment-specific tweaks.
        kwargs: passed through to `comparison_heatmap`.

    Returns:
        A mapping from strings to figures.
    """
    dissimilarity = dissimilarity.copy()
    dissimilarity = transformations.rewrite_index(dissimilarity)
    dissimilarity = compact(dissimilarity)

    if order is not None:
        source_order = list(order)
        if serialize.ZERO_REWARD in dissimilarity.index.get_level_values("source_reward_type"):
            if serialize.ZERO_REWARD not in source_order:
                source_order.append(serialize.ZERO_REWARD)

        # This is meant to reorder, but not remove anything.
        idx = dissimilarity.index
        source_matches = set(source_order) == set(idx.get_level_values("source_reward_type"))
        target_matches = set(order) == set(idx.get_level_values("target_reward_type"))
        assert source_matches, "reindexing would remove/add elements not just change order"
        assert target_matches, "reindexing would remove/add elements not just change order"
        dissimilarity = dissimilarity.reindex(index=source_order, level="source_reward_type")
        dissimilarity = dissimilarity.reindex(index=order, level="target_reward_type")

    figs = {}
    for name, matchings in masks.items():
        fig, ax = plt.subplots(1, 1, squeeze=True)
        match_mask = reward_masks.compute_mask(dissimilarity, matchings)
        comparison_heatmap(
            dissimilarity, ax=ax, fmt=fmt, preserve_order=True, mask=match_mask, **kwargs
        )
        after_plot()
        figs[name] = fig

    return figs