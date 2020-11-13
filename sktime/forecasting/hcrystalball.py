# -*- coding: utf-8 -*-
import pandas as pd

from sktime.forecasting.base._base import DEFAULT_ALPHA
from sktime.forecasting.base._sktime import (
    _OptionalForecastingHorizonMixin,
    _SktimeForecaster,
)
from sktime.utils.validation.series import check_equal_time_index


def _ensure_datetime_index(index):
    return index.to_timestamp() if isinstance(index, pd.PeriodIndex) else index


def _adapt_fit_data(y_train, X_train):
    """Adapt fit data to HCB compliant format

    Parameters
    ----------
    y_train : pandas.Series
        Target variable
    X_train : pandas.Series, pandas.DataFrame
        Exogenous variables

    Returns
    -------
    tuple
        y_train - pandas.Series with datetime index
        X_train - pandas.DataFrame with datetime index
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
        if isinstance(X_train.index, type(X.index)):
            X = X.merge(X_train, left_index=True, right_index=True)
        else:
            try:
                X = pd.DataFrame(data=X_train.values, index=X.index)
            except ValueError as e:
                raise ValueError(
                    "Combination of datetime information in y_train, "
                    "no datetime information in X_train and different lenghts "
                    f"(y_train:{len(y_train)}, X_train:{len(X_train)})"
                    "is ambiguous and not supported."
                ) from e

    elif isinstance(X_train.index, (pd.PeriodIndex, pd.DatetimeIndex)):
        if len(X_train) != len(y_train):
            raise ValueError(
                "Combination of datetime information in X_train, "
                "no datetime information in y_train and different lenghts "
                f"(X_train:{len(X_train)}, y_train:{len(y_train)})"
                "is ambiguous and not supported."
            )
        dt_index = _ensure_datetime_index(X_train.index)
        X = pd.DataFrame(data=X_train.values, index=dt_index)
        y_train = pd.Series(data=y_train.values, index=dt_index)

    else:
        raise ValueError(
            "At least one of y_train or X_train "
            "must have Period or DateTime index. "
            f"You provided {type(X_train.index)} for X_train.index "
            f"and {type(y_train.index)} for y_train.index"
        )

    return y_train, X


def _adapt_predict_data(X_pred, fh):
    """Translate forecast horizon interface to HCB native dataframe

    Parameters
    ----------
    X_pred : pandas.DataFrame
        Exogenous data for predictions
    fh : sktime.forecasting.base.ForecastingHorizon
        Forecasting horizon in its absolute form

    Returns
    -------
    pandas.DataFrame
        index - datetime
        columns - exogenous variables (optional)
    """
    X = pd.DataFrame(index=pd.PeriodIndex(fh).to_timestamp())
    X_pred = X_pred if X_pred is not None else pd.DataFrame()
    if not X_pred.empty:
        check_equal_time_index(X_pred, X)
        X = X.merge(X_pred, left_index=True, right_index=True)

    return X


def _convert_predictions(preds):
    """Translate wrapper prediction to sktime format

    From Dataframe with DatetimeIndex to series with PeriodIndex

    Parameters
    ----------
    preds : pandas.DataFrame
        Predictions provided from HCrystalball estimator

    Returns
    -------
    pandas.Series
        Predictions in form of series with PeriodIndex
    """
    preds = preds.iloc[:, 0]
    preds.index = preds.index.to_period()

    return preds


class HCrystalBallForecaster(_OptionalForecastingHorizonMixin, _SktimeForecaster):
    def __init__(self, model):
        self.model = model
        self._is_fitted = False

    def fit(self, y_train, fh=None, X_train=None):
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

        X = _adapt_predict_data(X, fh=self.fh.to_absolute(self.cutoff))

        preds = self.model.predict(X=X)

        return _convert_predictions(preds)

    # TODO: update per model/once the support is there for all models
    def _check_model_consistent_with_pred_int(alpha):
        raise NotImplementedError(
            "Full support for confidence intervals is not implemented."
        )
