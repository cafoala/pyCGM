#!/usr/bin/env python
# coding: utf-8

import pandas as pd
import numpy as np
import scipy
from functools import reduce

import helper
import warnings
from datetime import timedelta as time

# warnings are the worst
warnings.filterwarnings('ignore')

# setting up some regularly used timedeltas
fift_mins = time(minutes=15)
thirt_mins = time(minutes=30)


def all_metrics(df, interval_size, start_time=None, end_time=None, by_day=False, exercise_thresholds=False):
    """
    Calculates all available CGM metrics in one go. Time in range, hypoglycemic episodes, average glucose, glycemic
    variability and ea1c.

    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional

    :param interval_size: Int
        The length of time between glucose readings

    :param by_day: Bool
        Gives a breakdown of all metrics by day

    :param exercise_thresholds: Bool
        Sets the thresholds for time in range to exercise, <7 for hypoglycemia and >15 for hyperglycemia

    :return: Pandas DataFrame
        Contains all of the metric columns along with ID and exercise_thresholds if selected
    """
    df['time'] = pd.to_datetime(df['time'])

    id_bool = 'ID' in df.columns
    by_day_id = True
    # if by_day breakdown selected, add the date to id
    if by_day & id_bool:
        df['ID'] = df['ID'] + '$' + df['time'].dt.date.astype(str)
    elif by_day:
        df['ID'] = df['time'].dt.date.astype(str)
        id_bool = True
        by_day_id = False

    # calls all of functions in the package
    hypos = hypoglycemic_episodes(df, interval_size=interval_size)
    tir = time_in_range(df)
    glc_var = glycemic_variability(df)
    avg = average_glucose(df)
    ea1c_val = ea1c(df)
    perc_missing = percent_missing(df, interval_size=interval_size, start_datetime=start_time, end_datetime=end_time)

    # if exercise_thresholds are True, calculate time in range and number of hypoglycemic episodes for exercise
    if exercise_thresholds:
        tir_ex = time_in_range(df, exercise_thresholds=True)
        hypos_ex = hypoglycemic_episodes(df, interval_size=interval_size, exercise_thresholds=True)
        # dataframes to concatenate
        data_frames = [tir, tir_ex, hypos, hypos_ex, glc_var, avg, perc_missing, ea1c_val]
    else:
        data_frames = [tir, hypos, glc_var, avg, perc_missing, ea1c_val]
    # If ID column is present, merge all of the dataframes on ID
    if id_bool:
        df_merged = reduce(lambda left, right: pd.merge(left, right, on=['ID'],
                                                        how='outer'), data_frames)
        if by_day:
            df_merged[['ID', 'date']] = df_merged['ID'].str.split('$', n=1, expand=True)
        else:
            df_merged.rename({'ID': 'date'})
    else:
        df_merged = pd.concat(data_frames)

    if not exercise_thresholds:
        df_merged['number lv1 hypos'] = df_merged['number hypos'] - df_merged['number lv2 hypos']
    return df_merged


def time_in_range(df, exercise_thresholds=False):
    """
    Calculates the time in range for various set ranges option to select exercise thresholds which are
    different to regular thresholds, can be used on a dataset from a single person or combined dataset
    with IDs present df has to be have 'time' (timestamp) and 'glc' (glucose) columns

    Parameters
    ----------
    df : Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional

    exercise_thresholds : Bool
        Sets the thresholds for time in range to exercise, <7 for hypoglycemia and >15 for hyperglycemia


    Returns
    -------
    Pandas DataFrame.
        Returned results contain the time in hypoglycemia (level 1 and level 2 if exercise_threshold=False),
        time in normal range, time in hyperglycemia (if exercise_threshold=False). If ID column is provided
        this will contain results for each ID.

    """
    # create a list to add the results to
    list_results = []
    # drop any null values in the glc column
    df = df.dropna(subset=['glc'])

    # calculate the total number of readings
    df_len = df.shape[0]

    # check that there's readings in the df
    if df_len == 0:
        print('LEN ERROR')
        print('')
        # Throw some kind of error!!!???

    # if the df has an id column
    if 'ID' in df.columns:
        # exercise thresholds aren't selected
        # loop through all of the IDs making slice of dataframe then run through the tir_helper function
        # tir_helper is in helper.py
        # add the resulting list to the results along with the ID, convert to dataframe and return
        if not exercise_thresholds:
            for ID in set(df['ID'].values):
                id_glc = df[df['ID'] == ID]['glc']
                list_results.append([ID] + helper.tir_helper(id_glc))
            results = pd.DataFrame(list_results, columns=['ID', 'TIR lv2 hypo (<3)', 'TIR lv1 hypo (3-3.9)',
                                                          'TIR hypo (<3.9)', 'TIR norm (3.9-10)', 'TIR hyper (>10)',
                                                          'TIR lv1 hyper (10-13.9)', 'TIR_lv2_hyper (>13.9)'])
        # exercise thresholds are selected
        # same as above but uses tir_exercise function with different thresholds
        else:
            for ID in set(df['ID'].values):
                id_glc = df[df['ID'] == ID]['glc']
                list_results.append([ID] + helper.tir_exercise(id_glc))
            results = pd.DataFrame(list_results, columns=['ID', 'TIR hypo (<7)', 'TIR normal(7-15)', 'TIR hyper (>15)'])

    # df doesn't have an id column
    else:
        # normal thresholds
        # same as 1st block, just need to run for once rather than for all IDs
        if not exercise_thresholds:
            list_results.append(helper.tir_helper(df['glc']))
            results = pd.DataFrame(list_results,
                                   columns=['TIR lv2 hypo (<3)', 'TIR lv1 hypo (3-3.9)', 'TIR hypo (<3.9)',
                                            'TIR norm (3.9-10)', 'TIR hyper (>10)',
                                            'TIR lv1 hyper (10-13.9)', 'TIR_lv2_hyper (>13.9)'])
        # exercise thresholds
        # same as 2nd block but only need to run once
        else:
            list_results.append(helper.tir_exercise(df['glc']))
            results = pd.DataFrame(list_results, columns=['TIR hypo (<7)', 'TIR normal(7-15)', 'TIR hyper (>15)'])
    return results


def ea1c(df):
    """
    Calculates ea1c for glucose data from a Pandas Dataframe. The dataframe must contain  works for df with an ID column
    or without.
    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional

    :return: Pandas DataFrame
        Contains ea1c and ID if present
    """
    list_results = []
    # loops through IDs calculating ea1c and returning
    if 'ID' in df.columns:
        for ID in set(df['ID'].values):
            id_glc = df[df['ID'] == ID]['glc']
            mean = id_glc.mean()
            ea1c_value = (mean + 2.59) / 1.59
            list_results.append([ID, ea1c_value])
        return pd.DataFrame(list_results, columns=['ID', 'ea1c'])
    # calculates ea1c and returns for single dataset
    else:
        mean = df['glc'].mean()
        ea1c_value = (mean + 2.59) / 1.59
        return pd.DataFrame(ea1c_value, columns=['ea1c'])


def glycemic_variability(df):
    """
    Calculates glycemic variability (SD, CD, min and max glucose) values for glucose data from a Pandas Dataframe. The
    dataframe must contain 'time' (timestamp) and 'glc' (glucose) columns, works for df with or without an 'ID' column

    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional

    :return: Pandas DataFrame
        Contains SD, CD, min and max glucose and ID if present
    """
    list_results = []
    # if df has an id column, set has_id to either true or false
    if 'ID' in df.columns:
        for ID in set(df['ID'].values):
            id_glc = df[df['ID'] == ID]['glc']

            mean = id_glc.mean()
            sd = id_glc.std()
            cv = sd * 100 / mean
            min_glc = id_glc.min()
            max_glc = id_glc.max()

            list_results.append([ID, sd, cv, min_glc, max_glc])
            # returns df with IDs and glyc var values
        return pd.DataFrame(list_results, columns=['ID', 'sd', 'cv', 'min glucose', 'max glucose'])
    # no IDs in df
    else:
        mean = df['glc'].mean()
        sd = df.glc.std()
        cv = sd * 100 / mean
        min_glc = df.min()
        max_glc = df.max()
        list_results.append([sd, cv, min_glc, max_glc])
        # returns df with glyc var values
        return pd.DataFrame(list_results, columns=['sd', 'cv', 'min glucose', 'max glucose'])


def average_glucose(df):
    """
    Calculates average (mean) glucose for glucose data from a Pandas Dataframe. The dataframe must contain 'time'
    (timestamp) and 'glc' (glucose) columns, works for df with or without an 'ID' column.

    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional

    :return: Pandas DataFrame
        Contains average glucose and ID if present
    """
    list_results = []
    # if df has an id column, set has_id to either true or false
    if 'ID' in df.columns:
        for ID in set(df['ID'].values):
            id_glc = df[df['ID'] == ID]['glc']
            mean = id_glc.mean()
            list_results.append([ID, mean])
        return pd.DataFrame(list_results, columns=['ID', 'avg glucose'])

    else:
        mean = df['glc'].mean()
        return mean


def hypoglycemic_episodes(df, interval_size=5, breakdown=False, exercise_thresholds=False, interpolate=False,
                          interp_method='pchip'):
    """
    Calculates the number of level 1 and level 2 hypoglycemic episodes from the glucose data in a Pandas DataFrame. The
    results can either be an overview of episodes or a breakdown of each episode with a start and end time. Threshold
    can be set to exercise threshold (<7mmol/L). This method gives the option of interpolating and allows the selection
    of the interpolation method. The dataframe must contain 'time' (timestamp) and 'glc' (glucose) columns, works for
    df with or without an 'ID' column.

    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional
    :param interval_size: Int
        The length of time between glucose readings
    :param exercise_thresholds: Bool
        Whether exercise threshold (<7mmol/L) should be used to determine a hypoglycemic episode. If False, regular
        thresholds of 3.9mmol/L and 3mmol/L will be used to determine level 1 and level 2 episodes.
    :param breakdown: Bool
        Whether an episode by episode breakdown of the results should be returned or an overview of episodes for each ID
    :param interpolate: Bool
        Whether the data should be interpolated before the hypoglycemic episodes are calculated
    :param interp_method:
        The interpolation method used if interpolation is True
    :return: Pandas DataFrame
        If breakdown is False, will return an overview with the number of hypoglycemic episodes (level 1 & 2 or
        <7mmol/L), mean length of episode, total time in hypoglycemia for each ID.
        If breakdown is True, will return a breakdown of each episode with start time, end time, whether it is a level 2
        episode and the min glucose for each ID
    """
    # has an id column to loop through ids
    if 'ID' in df.columns:
        df[['ID', 'glc', 'time']].dropna(inplace=True)
        # loop through all ids applying helper_hypo_episodes function, found in helper.py
        # returned in a multi-index format so need to select level
        results = df.groupby('ID').apply(
            lambda group: helper.helper_hypo_episodes(group, gap_size=interval_size, breakdown=breakdown,
                                                      interpolate=interpolate, exercise=exercise_thresholds,
                                                      interp_method=interp_method)).reset_index().drop(
            columns='level_1')
        if exercise_thresholds & (breakdown is False):
            results.drop(columns='number lv2 hypos', inplace=True)
            results.columns = ['ID', 'number hypos (<7)', 'avg length (<7)', 'total time in hypo (<7)']
        return results

    else:
        df[['glc', 'time']].dropna(inplace=True)
        results = helper.helper_hypo_episodes(df, interpolate=interpolate, interp_method=interp_method,
                                              exercise=exercise_thresholds, gap_size=interval_size, breakdown=breakdown)
        return results


def percent_missing(df, interval_size, start_datetime=None, end_datetime=None):
    """
    Calculates the percentage of missing data from the glucose data in a Pandas DataFrame. Can enter start and end time
    to assess over a period of time how much data is missing, otherwise will just do from start to end of dataset.
    :param df: Pandas DataFrame
        Glucose monitor time series, must contain columns titled 'time' and 'glc', 'ID' optional
    :param interval_size: Int
        The length of time between glucose readings
    :param start_datetime: String or Datetime
        The start datetime when setting a period to check for missing data
    :param end_datetime: String or Datetime
        The end datetime when setting a period to check for missing data
    :return: Pandas DataFrame
        Contains percentage of missing data, start time, end time and interval size
    """
    df['time'] = pd.to_datetime(df['time'])

    # Some check that checks start_time and end_time are dt objects
    start_datetime = pd.to_datetime(start_datetime)
    end_datetime = pd.to_datetime(end_datetime)

    list_results = []

    if 'ID' in df.columns:
        for ID in set(df['ID'].values):
            id_time = df[df['ID'] == ID]
            list_results.append([ID] + helper.helper_missing(id_time, gap_size=interval_size, start_time=start_datetime,
                                                             end_time=end_datetime))
        df_results = pd.DataFrame(list_results,
                                  columns=['ID', 'percent missing']) #, 'start time', 'end time', 'interval'])
        return df_results
    else:
        return pd.DataFrame([helper.helper_missing(df, gap_size=interval_size, start_time=start_datetime,
                                                   end_time=end_datetime)],
                            columns=['percent missing']) #, 'start time', 'end time', 'interval'])
