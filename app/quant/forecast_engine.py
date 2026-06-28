import os
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing
from statsmodels.tsa.seasonal import STL
from statsmodels.tsa.statespace.sarimax import SARIMAX

warnings.filterwarnings("ignore")


@dataclass
class ForecastConfig:
    feature_path: str = "data/features/demo_model_feature_matrix.csv"
    target_col: str = "ebitda_proxy"
    date_col: str = "period_end"
    periods: int = 20
    seasonal_periods: int = 4
    output_path: str = "data/processed/quant_ebitda_forecast.csv"
    stl_output_path: str = "data/processed/stl_components.csv"


MACRO_COLS = ["fed_funds_rate", "cpi", "credit_spread"]


def _ensure_output_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def load_model_features(config: ForecastConfig) -> pd.DataFrame:
    path = Path(config.feature_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Missing model feature matrix: {path}. "
            "Run the feature matrix pipeline first."
        )

    df = pd.read_csv(path)
    df[config.date_col] = pd.to_datetime(df[config.date_col])
    df = df.sort_values(config.date_col).reset_index(drop=True)

    if config.target_col not in df.columns:
        raise ValueError(f"Missing target column: {config.target_col}")

    df[config.target_col] = pd.to_numeric(df[config.target_col], errors="coerce")
    df[config.target_col] = df[config.target_col].interpolate(method="linear")
    df[config.target_col] = df[config.target_col].ffill().bfill()

    for col in MACRO_COLS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].interpolate(method="linear")
            df[col] = df[col].ffill().bfill()

    return df


def make_future_dates(last_date: pd.Timestamp, periods: int) -> pd.DatetimeIndex:
    # Pandas 3+ deprecates "Q"; use "QE" for quarter end.
    return pd.date_range(
        start=last_date,
        periods=periods + 1,
        freq="QE",
    )[1:]


def run_stl_decomposition(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> pd.DataFrame:
    series = df.set_index(config.date_col)[config.target_col]

    stl = STL(
        series,
        period=config.seasonal_periods,
        robust=True,
    )

    result = stl.fit()

    stl_df = pd.DataFrame(
        {
            "period_end": series.index,
            "observed": result.observed.values,
            "trend": result.trend.values,
            "seasonal": result.seasonal.values,
            "residual": result.resid.values,
        }
    )

    _ensure_output_dir(config.stl_output_path)
    stl_df.to_csv(config.stl_output_path, index=False)

    return stl_df


def _residual_band(
    actual: pd.Series,
    fitted: pd.Series,
    horizon: int,
    scale_growth: float = 1.03,
) -> tuple[np.ndarray, np.ndarray]:
    residuals = actual - fitted
    residuals = residuals.dropna()

    if len(residuals) < 4:
        sigma = float(actual.std()) * 0.15
    else:
        sigma = float(residuals.std())

    # widen uncertainty gradually over horizon
    multipliers = np.array([scale_growth ** i for i in range(horizon)])

    p10_delta = -1.2816 * sigma * multipliers
    p90_delta = 1.2816 * sigma * multipliers

    return p10_delta, p90_delta


def forecast_holt_winters(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> pd.DataFrame:
    series = df.set_index(config.date_col)[config.target_col]
    future_dates = make_future_dates(series.index.max(), config.periods)

    try:
        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal="add",
            seasonal_periods=config.seasonal_periods,
            initialization_method="estimated",
        )
        fitted_model = model.fit(optimized=True)
    except Exception:
        model = ExponentialSmoothing(
            series,
            trend="add",
            seasonal=None,
            initialization_method="estimated",
        )
        fitted_model = model.fit(optimized=True)

    forecast = fitted_model.forecast(config.periods)

    fitted = fitted_model.fittedvalues
    p10_delta, p90_delta = _residual_band(series, fitted, config.periods)

    out = pd.DataFrame(
        {
            "period_end": future_dates,
            "model": "holt_winters",
            "p10": forecast.values + p10_delta,
            "p50": forecast.values,
            "p90": forecast.values + p90_delta,
        }
    )

    return out


def forecast_sarima(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> pd.DataFrame:
    series = df.set_index(config.date_col)[config.target_col]
    future_dates = make_future_dates(series.index.max(), config.periods)

    model = SARIMAX(
        series,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, config.seasonal_periods),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )

    fitted_model = model.fit(disp=False)

    prediction = fitted_model.get_forecast(steps=config.periods)
    mean_forecast = prediction.predicted_mean
    conf_int = prediction.conf_int(alpha=0.20)

    lower_col = conf_int.columns[0]
    upper_col = conf_int.columns[1]

    out = pd.DataFrame(
        {
            "period_end": future_dates,
            "model": "sarima",
            "p10": conf_int[lower_col].values,
            "p50": mean_forecast.values,
            "p90": conf_int[upper_col].values,
        }
    )

    return out


def forecast_sarimax(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> Optional[pd.DataFrame]:
    available_macro_cols = [col for col in MACRO_COLS if col in df.columns]

    if not available_macro_cols:
        return None

    series = df.set_index(config.date_col)[config.target_col]
    exog = df.set_index(config.date_col)[available_macro_cols]

    future_dates = make_future_dates(series.index.max(), config.periods)

    # For demo, carry forward latest macro values as future assumptions.
    latest_macro = exog.iloc[-1]
    future_exog = pd.DataFrame(
        [latest_macro.to_dict() for _ in range(config.periods)],
        index=future_dates,
    )

    model = SARIMAX(
        series,
        exog=exog,
        order=(1, 1, 1),
        seasonal_order=(1, 1, 1, config.seasonal_periods),
        enforce_stationarity=False,
        enforce_invertibility=False,
    )

    fitted_model = model.fit(disp=False)

    prediction = fitted_model.get_forecast(
        steps=config.periods,
        exog=future_exog,
    )

    mean_forecast = prediction.predicted_mean
    conf_int = prediction.conf_int(alpha=0.20)

    lower_col = conf_int.columns[0]
    upper_col = conf_int.columns[1]

    out = pd.DataFrame(
        {
            "period_end": future_dates,
            "model": "sarimax_macro",
            "p10": conf_int[lower_col].values,
            "p50": mean_forecast.values,
            "p90": conf_int[upper_col].values,
        }
    )

    return out


def forecast_prophet(
    df: pd.DataFrame,
    config: ForecastConfig,
) -> Optional[pd.DataFrame]:
    try:
        from prophet import Prophet
    except Exception as exc:
        print(f"[WARN] Prophet unavailable, skipping: {exc}")
        return None

    prophet_df = df[[config.date_col, config.target_col]].copy()
    prophet_df = prophet_df.rename(
        columns={
            config.date_col: "ds",
            config.target_col: "y",
        }
    )

    macro_cols = [col for col in MACRO_COLS if col in df.columns]

    for col in macro_cols:
        prophet_df[col] = df[col].values

    model = Prophet(
        interval_width=0.80,
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
    )

    for col in macro_cols:
        model.add_regressor(col)

    model.fit(prophet_df)

    # Prophet creates the immediate quarter-end after the latest historical date.
    # If latest history is 2026-03-28, Prophet first future date becomes 2026-03-31.
    # For our 20-quarter forward curve, we want to start from the next quarter-end:
    # 2026-06-30. Therefore, request one extra period and filter out the current quarter.
    future = model.make_future_dataframe(
        periods=config.periods + 1,
        freq="QE",
    )

    if macro_cols:
        latest_macro = df[macro_cols].iloc[-1]
        for col in macro_cols:
            existing_len = len(prophet_df)
            future.loc[: existing_len - 1, col] = prophet_df[col].values
            future.loc[existing_len:, col] = latest_macro[col]

    forecast = model.predict(future)

    last_history_quarter_end = (
        pd.Timestamp(df[config.date_col].max())
        .to_period("Q")
        .to_timestamp("Q")
    )

    forecast = forecast[forecast["ds"] > last_history_quarter_end]

    out = forecast[["ds", "yhat_lower", "yhat", "yhat_upper"]].head(
        config.periods
    )

    out = out.rename(
        columns={
            "ds": "period_end",
            "yhat_lower": "p10",
            "yhat": "p50",
            "yhat_upper": "p90",
        }
    )

    out["model"] = "prophet_macro" if macro_cols else "prophet"

    return out[["period_end", "model", "p10", "p50", "p90"]]


def build_ensemble(forecasts: List[pd.DataFrame], periods: int = 20) -> pd.DataFrame:
    clean_forecasts = [f for f in forecasts if f is not None and not f.empty]

    if not clean_forecasts:
        raise ValueError("No forecasts available for ensemble.")

    normalized = []

    for forecast_df in clean_forecasts:
        temp = forecast_df.copy()
        temp["period_end"] = pd.to_datetime(temp["period_end"])

        # Normalize every model output to quarter-end.
        temp["period_end"] = temp["period_end"].dt.to_period("Q").dt.to_timestamp("Q")

        # If a model produces duplicate quarter-end rows, keep the last one.
        temp = (
            temp.sort_values("period_end")
            .drop_duplicates(subset=["model", "period_end"], keep="last")
        )

        normalized.append(temp)

    all_forecasts = pd.concat(normalized, ignore_index=True)

    expected_model_count = all_forecasts["model"].nunique()

    ensemble = (
        all_forecasts.groupby("period_end")
        .agg(
            p10=("p10", "mean"),
            p50=("p50", "mean"),
            p90=("p90", "mean"),
            model_count=("model", "count"),
        )
        .reset_index()
        .sort_values("period_end")
    )

    # Keep only forecast quarters where every model contributes.
    ensemble = ensemble[ensemble["model_count"] == expected_model_count]

    # Keep exactly requested forecast horizon.
    ensemble = ensemble.head(periods)

    ensemble["model"] = "ensemble"
    ensemble["target_metric"] = "ebitda_proxy"

    return ensemble[
        [
            "period_end",
            "model",
            "target_metric",
            "p10",
            "p50",
            "p90",
            "model_count",
        ]
    ]

def run_quant_forecast(config: ForecastConfig | None = None) -> pd.DataFrame:
    if config is None:
        config = ForecastConfig()

    df = load_model_features(config)

    print(f"[Quant] Loaded model features: {len(df)} rows")
    print(f"[Quant] Target: {config.target_col}")

    stl_df = run_stl_decomposition(df, config)
    print(f"[Quant] STL components saved: {config.stl_output_path}")

    forecasts: List[pd.DataFrame] = []

    hw = forecast_holt_winters(df, config)
    print("[Quant] Holt-Winters forecast complete")
    forecasts.append(hw)

    try:
        sarima = forecast_sarima(df, config)
        print("[Quant] SARIMA forecast complete")
        forecasts.append(sarima)
    except Exception as exc:
        print(f"[WARN] SARIMA skipped: {exc}")

    try:
        sarimax = forecast_sarimax(df, config)
        if sarimax is not None:
            print("[Quant] SARIMAX macro forecast complete")
            forecasts.append(sarimax)
    except Exception as exc:
        print(f"[WARN] SARIMAX skipped: {exc}")

    prophet = forecast_prophet(df, config)
    if prophet is not None:
        print("[Quant] Prophet forecast complete")
        forecasts.append(prophet)

        ensemble = build_ensemble(forecasts, periods=config.periods)

    _ensure_output_dir(config.output_path)
    ensemble.to_csv(config.output_path, index=False)

    print(f"[Quant] Ensemble forecast saved: {config.output_path}")
    print(ensemble.tail())

    return ensemble


if __name__ == "__main__":
    run_quant_forecast()