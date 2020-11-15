# -*- coding: utf-8 -*-
import pandas as pd

from sktime.forecasting.base._base import DEFAULT_ALPHA
from sktime.forecasting.base._sktime import (
    _OptionalForecastingHorizonMixin,
    _SktimeForecaster,
)
from sktime.utils.check_imports import _check_soft_dependencies

_check_soft_dependencies("hcrystalball")


def _ensure_datetime_index(index):
    return index.to_timestamp() if isinstance(index, pd.PeriodIndex) else index


def _safe_merge(real_df, dummy_df):
    if isinstance(real_df.index, (pd.PeriodIndex, pd.DatetimeIndex)):
        return dummy_df.merge(real_df, left_index=True, right_index=True, how="left")
    else:
        return pd.DataFrame(data=real_df.values, index=dummy_df.index)


def _extract_dt_index(fh, cutoff):
    """Extract datetime index from forecasting horizon and cutoff

    Parameters
    ----------
    fh : sktime.forecasting.base.ForecastingHorizon
        Forecasting horizon
    cutoff : pd.Period, pd.Timestamp, int
        Cutoff value required to convert a relative forecasting
        horizon to an absolute one.

    Returns
    -------
    pd.DatetimeIndex
        Datetime index with frequency from cutoff
    """
    # for 1 point time-series, frequency information is lost, need to be explicit
    idx = pd.PeriodIndex(fh.to_absolute(cutoff), freq=cutoff.freq).to_timestamp()
    if len(pd.date_range(idx.min(), idx.max())) != len(set(idx.values)):
        raise NotImplementedError(
            "HCrystalBall does not support non continuous indicies"
        )
    return idx


def _adapt_fit_data(y_train, X_train):
    """Adapt fit data to HCB compliant format

    Parameters
    ----------
    y_train : pd.Series
        Target variable
    X_train : pd.Series, pd.DataFrame
        Exogenous variables

    Returns
    -------
    tuple
        y_train - pd.Series with datetime index
        X_train - pd.DataFrame with datetime index
                  and optionally exogenous variables in columns

    Raises
    ------
    ValueError
        When neither of the argument has Datetime or Period index
    """
    X_train = X_train if X_train is not None else pd.DataFrame()

    if isinstance(y_train.index, (pd.PeriodIndex, pd.DatetimeIndex)):
        dt_index = _ensure_datetime_index(y_train.index)
        y_train = pd.Series(data=y_train.values, index=dt_index)
        X = pd.DataFrame(index=dt_index)
        try:
            X = _safe_merge(X_train, X)
        except ValueError as e:
            raise NotImplementedError(
                "Combination of datetime information in y_train, "
                "no datetime information in X_train and different lenghts "
                f"(y_train:{len(y_train)}, X_train:{len(X_train)})"
                "is ambiguous and not supported."
            ) from e

    elif isinstance(X_train.index, (pd.PeriodIndex, pd.DatetimeIndex)):
        if len(X_train) != len(y_train):
            raise NotImplementedError(
                "Combination of datetime information in X_train, "
                "no datetime information in y_train and different lenghts "
                f"(X_train:{len(X_train)}, y_train:{len(y_train)})"
                "is ambiguous and not supported."
            )
        dt_index = _ensure_datetime_index(X_train.index)
        X = pd.DataFrame(data=X_train.values, index=dt_index)
        y_train = pd.Series(data=y_train.values, index=dt_index)

    else:
        raise NotImplementedError(
            "At least one of y_train or X_train "
            "must have Period or DateTime index. "
            f"You provided {type(X_train.index)} for X_train.index "
            f"and {type(y_train.index)} for y_train.index"
        )

    return y_train, X


def _adapt_predict_data(X_pred, index):
    """Translate forecast horizon interface to HCB native dataframe

    Parameters
    ----------
    X_pred : pd.DataFrame
        Exogenous data for predictions
    index : pd.DatetimeIndex
        Index generated from the forecasting horizon

    Returns
    -------
    pd.DataFrame
        index - datetime
        columns - exogenous variables (optional)
    """
    X = pd.DataFrame(index=index)

    if X_pred is not None:
        try:
            X = _safe_merge(X_pred, X)
        except ValueError as e:
            raise NotImplementedError(
                "Providing exogenous variables without datetime information in index "
                "while having different length than forecasting horizon "
                "is not supported. Make sure to align lenghts if no datetime "
                "is in X_pred or add datetime to make the information merge possible."
            ) from e

    return X


def _convert_predictions(preds, freq, index_type):
    """Translate wrapper prediction to sktime format

    From Dataframe with DatetimeIndex to series with PeriodIndex

    Parameters
    ----------
    preds : pd.DataFrame
        Predictions provided from HCrystalball estimator
    freq : pd.tseries.offsets.DateOffset
        Frequency of the data
    index_type : pd.Index
        Type of the index from the training data

    Returns
    -------
    pd.Series
        Predictions in form of series with PeriodIndex
    """
    preds = preds.iloc[:, 0]
    preds.index = index_type(preds.index.values, freq=freq)

    return preds


class HCrystalBallForecaster(_OptionalForecastingHorizonMixin, _SktimeForecaster):
    def __init__(self, model):
        self.model = model
        self._is_fitted = False
        super(HCrystalBallForecaster, self).__init__()

    def fit(self, y_train, X_train=None, fh=None):
        self._set_y_X(y_train, X_train)
        self._set_fh(fh)

        y_train, X_train = _adapt_fit_data(y_train, X_train)

        self.model.fit(X=X_train, y=y_train)
        self._is_fitted = True

        return self

    def predict(self, fh=None, X=None, return_pred_int=False, alpha=DEFAULT_ALPHA):
        if return_pred_int:
            self._check_model_consistent_with_pred_int(alpha)

        self.check_is_fitted()
        self._set_fh(fh)

        X_hcb = _adapt_predict_data(X, _extract_dt_index(self.fh, self.cutoff))

        preds_dt = self.model.predict(X=X_hcb)
        preds = _convert_predictions(preds_dt, self.cutoff.freq, type(self._y.index))

        return preds

    # TODO: update per model/once the support is there for all models
    @staticmethod
    def _check_model_consistent_with_pred_int(alpha):
        raise NotImplementedError(
            "Full support for confidence intervals is not implemented."
        )
