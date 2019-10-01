# Copyright 2019 DeepMind Technologies Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Methods to generate plots and visualize data."""

import os
import re
from typing import Callable, Iterable, Optional, Tuple

from absl import logging
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

# Internal dependencies


TRANSFORMATIONS = {
    r"evaluating_rewards[_/](.*)-v0$": r"\1",
    "^PointMassDense$": "Dense",
    "^PointMassDenseNoCtrl$": "Dense\nNo Ctrl",
    "^PointMassGroundTruth$": "Norm",
    "^PointMassSparse$": "Sparse",
    "^PointMassSparseNoCtrl$": "Sparse\nNo Ctrl",
    "^Zero-v0$": "Zero",
    r"^Hopper(.*)": r"\1",
    r"^HalfCheetah(.*)": r"\1",
    r"(.*)GroundTruth(.*)": "\\1\U0001f3c3\\2",  # Runner emoji
    r"(.*)Backflip(.*)": "\\1\U0001f938\\2",  # Cartwheel emoji
    r"^(.*)Backward(.*)": r"\1←\2",
    r"^(.*)Forward(.*)": r"\1→\2",
    r"^(.*)WithCtrl(.*)": "\\1\U0001F40C\\2",  # Snail Emoji
    r"^(.*)NoCtrl(.*)": "\\1\U0001F406\\2",  # Cheetah emoji
}


LEVEL_NAMES = {
    # Won't normally use both type and path in one plot
    "source_reward_type": "Source",
    "source_reward_path": "Source",
    "target_reward_type": "Target",
    "target_reward_path": "Target",
}


def pretty_rewrite(x):
  if not isinstance(x, str):
    return x

  for pattern, repl in TRANSFORMATIONS.items():
    x = re.sub(pattern, repl, x)
  return x


def plot_shaping_comparison(df: pd.DataFrame,
                            cols: Optional[Iterable[str]] = None,
                            **kwargs) -> pd.DataFrame:
  """Plots return value of experiments.compare_synthetic."""
  if cols is None:
    cols = ["Intrinsic", "Shaping"]
  df = df.loc[:, cols]
  longform = df.reset_index()
  longform = pd.melt(longform, id_vars=["Reward Noise", "Potential Noise"],
                     var_name="Metric", value_name="Distance")
  sns.lineplot(x="Reward Noise", y="Distance", hue="Potential Noise",
               style="Metric", data=longform, **kwargs)
  return longform


def save_fig(path: str, fig: plt.Figure, fmt: str = "pdf", dpi: int = 300,
             **kwargs):
  path = f"{path}.{fmt}"
  root_dir = os.path.dirname(path)
  os.makedirs(root_dir, exist_ok=True)
  logging.info(f"Saving figure to {path}")
  with open(path, "wb") as f:
    fig.savefig(f, format=fmt, dpi=dpi, transparent=True, **kwargs)


def save_figs(root_dir: str,
              generator: Iterable[Tuple[str, plt.Figure]],
              **kwargs) -> None:
  for name, fig in generator:
    name = name.replace("/", "_")
    path = os.path.join(root_dir, name)
    save_fig(path, fig, **kwargs)


def path_rewrite(index: pd.Index) -> pd.Index:
  prefix = os.path.commonprefix(list(index))
  # We only want to strip common path components.
  # e.g. [a/b/cat, a/b/cod] -> [cat, cod] not [at, od].
  prefix = os.path.dirname(prefix)
  return index.str.extract(f"{prefix}/(.*?)(?:/model|)$", expand=False)


def short_e(x: float, precision: int = 2) -> str:
  """Formats 1.2345 as 1.2e-1, rather than Python 1.2e-01."""
  fmt = "{:." + str(precision) + "e}"
  formatted = fmt.format(x)
  base, exponent = formatted.split("e")
  exponent = int(exponent)
  return f"{base}e{exponent}"


def comparison_heatmap(vals: pd.Series,
                       log: bool = True,
                       fmt: Callable[[float], str] = short_e,
                       cmap: str = "GnBu",
                       robust: bool = False,
                       mask: Optional[pd.Series] = None,
                       **kwargs) -> None:
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
    mask: If provided, only display cells where mask is True.
    **kwargs: passed through to sns.heatmap.
  """
  def to_df(series):
    """Helper to reformat labels for ease of interpretability."""
    series = series.rename(index=pretty_rewrite)
    for i, level in enumerate(series.index.levels):
      if "path" in level.name:
        new_level = path_rewrite(level)
        series.index = series.index.set_levels(new_level, level=i)
    series.index.names = [LEVEL_NAMES.get(name, name)
                          for name in series.index.names]

    # Preserve order of inputs
    df = series.unstack("Target")
    df = df.reindex(columns=series.index.get_level_values("Target").unique())
    for level in series.index.names:
      kwargs = dict(level=level) if isinstance(df.index, pd.MultiIndex) else {}
      if level != "Target":
        df = df.reindex(index=series.index.get_level_values(level).unique(),
                        **kwargs)
    return df

  vals = to_df(vals)
  if mask is not None:
    mask = to_df(mask)

  data = np.log10(vals) if log else vals
  cbar_kws = dict(label=r"$-\log_{10}(q)$") if log else dict()

  annot = vals.applymap(fmt)

  if robust:
    flat = data.values.flatten()
    kwargs["vmin"], kwargs["vmax"] = np.quantile(flat, [0.25, 0.75])
  sns.heatmap(data, annot=annot, fmt="s", cmap=cmap, cbar_kws=cbar_kws,
              mask=mask, **kwargs)
