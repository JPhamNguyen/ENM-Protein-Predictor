"""Developed by: Matthew Findlay 2017
Modified by: Joseph Pham Nguyen 2021

This module contains the database class that handles all of the data gathering
and cleaning. It also contains functions that help us work with our data.
"""
import os
import pandas as pd
import numpy as np
from sklearn import preprocessing, model_selection
import random
import csv


def apply_RFECV_mask(mask, *args):
    """Applies a binary mask to a dataframe to remove columns. Binary mask is created from recursive feature elimination
     and cross validation and optimizes the generalization of the model
    Args:
        :param: mask (string): text file containing the binary mask
        :param: *args (pandas dataframe): Dataframes containing columns to mask
    Returns:
        :updated_args (pandas df): new dataframes with columns removed
    """
    assert os.path.isfile(mask), "please pass a string specifying mask location"
    dir_path = os.path.dirname(os.path.realpath(__file__))
    mask = os.path.join(dir_path, mask)
    # get mask data
    updated_args = []
    with open(mask, 'r') as f:
        reader = csv.reader(f)
        column_mask = list(reader)[0]
    # apply mask to columns
    column_indexes = []
    for dataframe in args:
        if len(column_mask) != len(list(dataframe)):
            column_mask = remove_extra_entries(column_mask)
            assert len(column_mask) == len(list(dataframe)), 'mask length {} does not match dataframe length {}'\
                .format(len(column_mask), len(list(dataframe)))

        for i, col in enumerate(column_mask):
            if col.strip() == 'False':
                column_indexes.append(i)

        updated_args.append(dataframe.drop(dataframe.columns[column_indexes], axis=1))
    return updated_args


def remove_extra_entries(mask):
    """Remove extra entries like '' or '\n' in the binary mask iff the length of mask does not match the corresponding
    dataframe length
    Args:
        :param: mask (array): the binary mask as a list of values
    Returns: mask (array): the binary mask with extraneous values removed from end of list
    """
    for i, col in reversed(list(enumerate(mask))):
        stripped_col = col.strip()
        if stripped_col == "True" or stripped_col == "False":
            break
        else:
            del mask[i]
    return mask


class data_base(object):
    """Handles all data fetching and preparation. Attributes
       can be assigned to csv files with the assignment operator. Typical use
       case is to set raw_data to a csv file matching the format found in
       Input files and then calling clean_raw_data(). This sets the clean_X_data and target values.
       From this point you can split the data to train/test the model using our data.
       To predict your own data, make sure your excel sheet matches the format in <Input_Files/database.csv>.
       Then you can call db.predict = <your_csv_path>. The X_test and Y_test data will now
       be your data. Just remove the stratified_data_split from the pipeline
       because you will now not need to split any data.

       Args:
            None
       Attributes:
            :self._raw_data (Pandas Dataframe): Holds raw data in the same form as excel file. initialized after fetch_raw_data() is called
            :self._clean_X_data (Pandas Dataframe): Holds cleaned and prepared X data.
            :self._target (np.array): holds target values for predictions
            :self._X_train (Pandas Dataframe): Holds the X training data
            :self._X_test (Pandas Dataframe): Holds the X test data
            :self._Y_train (Pandas Dataframe): Holds the Y training data
            :self._Y_test (Pandas Dataframe): Holds the Y testing data
            :self._test_accession_numbers (list): holds the accession_numbers
            :self._original (Pandas Dataframe): holds the original cleaned data before it's normalized so it can be used
            for data visualizations
        """
    categorical_data = ['Enzyme Commission Number', 'Particle Size', 'Particle Charge', 'Solvent Cysteine Concentration', 'Solvent NaCl Concentration']
    columns_to_drop = ['Protein Length', 'Sequence', 'Accession Number', 'Bound Fraction']

    def __init__(self):
        self._raw_data = None
        self._clean_X_data = None
        self._target = None
        self._X_train = None
        self._Y_train = None
        self._X_test = None
        self._Y_test = None
        self._test_accession_numbers = None
        self._original = None
        # If you want to use our model set this to your csv file using the assignment operator
        self._predict = None

    def clean_raw_data(self):
        """ Cleans the raw data, drops useless columns, one hot encodes, and extracts class information
        Args, Returns: None
        """
        self.clean_X_data = self.raw_data
        # one hot encode categorical data
        for category in self.categorical_data:
            self.clean_X_data = one_hot_encode(self.clean_X_data, category)

        # Fill in missing values in target label and 'Protein Abundance before dropping independent variables
        self.clean_X_data['Bound Fraction'].fillna(self.clean_X_data['Bound Fraction'].mean())

        # grab target label and accession numbers
        self._target = self.clean_X_data['Bound Fraction'].to_numpy()
        self.Y_train = self.target
        accession_numbers = self.clean_X_data['Accession Number']

        # drop useless columns
        for column in self.columns_to_drop:
            self.clean_X_data = self.clean_X_data.drop(column, 1)

        # fill in missing protein abundance values with the mean value
        self.clean_X_data = fill_nan(self.clean_X_data, 'Protein Abundance')

        # This grabs the original cleaned data so that it can be visualized in visualization_utils.py
        self._original = self.clean_X_data
        self.clean_X_data = normalize_and_reshape(self.clean_X_data, accession_numbers)
        self.X_train = self.clean_X_data

    def clean_user_test_data(self, user_data):
        """This method makes it easy for other people to make predictions on their data.
        Called by assignment operator when users set db.predict = <path_to_csv>
        Args:
            :param user_data: users data they wish to predict
        Returns:
            None
        """
        # one hot encode categorical data
        for category in self.categorical_data:
            user_data = one_hot_encode(user_data, category)

        # Grab some useful data before dropping from independent variables
        self.Y_test = user_data['Bound Fraction'].to_numpy()
        accession_numbers = user_data['Accession Number']

        for column in self.columns_to_drop:
            user_data = user_data.drop(column, 1)

        user_data = fill_nan(user_data, 'Protein Abundance')
        self.X_test = normalize_and_reshape(user_data, accession_numbers)

        # Get accession number
        self.test_accession_numbers = self.X_test['Accession Number']
        self.X_train = self.X_train.drop('Accession Number', 1)
        self.X_test = self.X_test.drop('Accession Number', 1)

    def data_split(self):
        """Uses KFold Cross Validation with 5 folds to randomly split our data into training and testing sets
        Args, Returns: None
        """
        assert self.predict is None, "Remove data_split() if using your own data"

        kf = model_selection.KFold(n_splits=5, random_state=int((random.random()*100)), shuffle=True)
        for train_index, test_index in kf.split(self.clean_X_data):
            self.X_train, self.X_test = self.clean_X_data.iloc[list(train_index)], self.clean_X_data.iloc[list(test_index)]
            self.Y_train, self.Y_test = self.target[train_index], self.target[test_index]

        self.test_accession_numbers = self.X_test['Accession Number']
        self.X_train = self.X_train.drop('Accession Number', 1)
        self.X_test = self.X_test.drop('Accession Number', 1)

    @staticmethod
    def fetch_raw_data(enm_database):
        """Fetches enm-protein data from a csv file called by assignment operator for db.raw_data
        Args:
            :param enm_database (str): path to csv database
        Returns:
            None
        """
        assert os.path.isfile(enm_database), "please pass a string specifying database location"

        dir_path = os.path.dirname(os.path.realpath(__file__))
        enm_database = os.path.join(dir_path, enm_database)
        try:
            raw_data = pd.read_csv(enm_database)
        except ValueError:
            raise ValueError("File is not a valid csv")

        return raw_data

    @property
    def X_train(self):
        if self._X_train is None:
            raise ValueError("Initialize X_train by calling stratified_data_split()")
        else:
            return self._X_train

    @property
    def X_test(self):
        if self._X_test is None:
            raise ValueError("Initialize X_test by calling stratified_data_split()")
        else:
            return self._X_test

    @property
    def Y_train(self):
        if self._Y_train is None:
            raise ValueError("Initialize Y_train by calling stratified_data_split()")
        else:
            return self._Y_train

    @property
    def Y_test(self):
        return self._Y_test

    @property
    def raw_data(self):
        if self._raw_data is None:
            raise ValueError("Initialize raw data by setting raw_data=<path.csv>")
        return self._raw_data

    @property
    def clean_X_data(self):
        if self._clean_X_data is None:
            raise ValueError("Initialize clean_X_data by calling clean_data()")
        else:
            return self._clean_X_data

    @property
    def original(self):
        if self._original is None:
            raise ValueError("Initialize original by calling clean_data()")
        else:
            return self._original

    @property
    def target(self):
        if self._target is None:
            raise ValueError("Initialize target by calling clean_data()")
        else:
            return self._target

    @property
    def test_accession_numbers(self):
        if self._test_accession_numbers is None:
            raise ValueError("Initialize test_accession_numbers by calling stratified_data_split()")
        else:
            return self._test_accession_numbers

    @property
    def predict(self):
        return self._predict

    @X_train.setter
    def X_train(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            self._X_train = self.fetch_raw_data(path)
        else:
            # If trying to set to already imported array
            self._X_train = path

    @X_test.setter
    def X_test(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            self._X_test = self.fetch_raw_data(path)
        else:
            # If trying to set to already imported array
            self._X_test = path

    @Y_train.setter
    def Y_train(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            self._Y_train = self.fetch_raw_data(path)
        else:
            # If trying to set to already imported array
            self._Y_train = path

    @Y_test.setter
    def Y_test(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            self._Y_test = self.fetch_raw_data(path)
        else:
            # If trying to set to already imported array
            self._Y_test = path

    @raw_data.setter
    def raw_data(self, enm_database):
        if isinstance(enm_database, str) and os.path.isfile(enm_database):
            self._raw_data = self.fetch_raw_data(enm_database)
        else:
            self._raw_data = enm_database

    @clean_X_data.setter
    def clean_X_data(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            self.clean_X_data = self.fetch_raw_data(path)
        else:
            # If trying to set to already imported array
            self._clean_X_data = path

    @test_accession_numbers.setter
    def test_accession_numbers(self, path):
        if isinstance(path, str) and os.path.isfile(path):
            # If trying to set to value from excel
            # self._Y_enrichment = fetch_raw_data(path)
            print("Enrichment factors don't exist anymore")
        else:
            # If trying to set to already imported array
            self._test_accession_numbers = path

    @predict.setter
    def predict(self, path):
        if os.path.isfile(path):
            self._predict = self.fetch_raw_data(path)
            self.clean_user_test_data(self._predict)
        else:
            self._predict = path


def normalize_and_reshape(data, labels):
    """Normalize and reshape the data by columns while preserving labels information
    Args:
        :param: data (pandas df): The data to normalize
        :param: labels (pandas series): The column labels
    Returns:
        :param data (pandas df): normalized dataframe with preserved column labels
    """
    norm_df = preprocessing.MinMaxScaler().fit_transform(data)
    data = pd.DataFrame(norm_df,columns=list(data))
    data = pd.concat([labels, data], axis=1)
    data.reset_index(drop=True, inplace=True)
    return data


def fill_nan(data, column):
    """ Fills nan values with mean in specified column.
    Args:
        :param: data (pandas Dataframe): Dataframe containing column with nan values
        :param: column (String): specifying column to fill_nans
    Returns:
        :data (pandas Dataframe): Containing the column with filled nan values
    """
    assert isinstance(data, pd.DataFrame), 'data argument needs to be pandas dataframe'
    assert isinstance(column, str), 'Column must be a string'

    count = 0
    total = 0
    for val in data[column]:
        if not np.isnan(val):
            count += 1
            total += val
    data[column] = data[column].fillna(total/count)
    return data


def one_hot_encode(dataframe, category):
    """This function converts categorical variables into one hot vectors
    Args:
        :param: dataframe (pandas Dataframe): Dataframe containing column to be encoded
        :param: category (String): specifying the column to encode
    Returns:
        :dataframe (Pandas Dataframe): With the specified column now encoded into a one
        hot representation
    """
    assert isinstance(dataframe, pd.DataFrame), 'data argument needs to be pandas dataframe'
    dummy = pd.get_dummies(dataframe[category], prefix=category)
    dataframe = pd.concat([dataframe, dummy], axis=1)
    dataframe.drop(category, axis=1, inplace=True)
    return dataframe


def save_metrics(error_metrics, feature_importances, predicted_value_stats):
    """Prints error metrics and feature importances, and saves this information into a text file.
    Saves the model statistics into a CSV file.
    Args:
        :param: error_metrics (dict): contains averaged error metrics for model performance
        :param: feature_importances (dict): contains Gini importance scores for optimized features
    Returns: None
    """
    # sort dictionary by highest ranked features
    feature_importances = dict(sorted(feature_importances.items(), key=lambda item: item[1], reverse=True))

    with open('Output_Files/model_evaluation_info.txt', 'w') as f:
        print("\n############ Average Error Metric Scores ############\n")
        f.write("\n############ Average Error Metric Scores ############\n")
        for key in error_metrics.keys():
            print("{}: {}".format(key, error_metrics[key]))
            f.write("{}: {}\n".format(key, error_metrics[key]))

        print("\n############ Average Feature Importance Scores ############\n")
        f.write("\n############ Average Feature Importance Scores ############\n")
        for feat in feature_importances.keys():
            print("Average Gini importance for {}: {}".format(feat, feature_importances[feat]))
            f.write("Average Gini importance for {}: {}\n".format(feat, feature_importances[feat]))

    # simply output formatted DataFrame to an easy to read CSV file
    predicted_value_stats.to_csv(path_or_buf='Output_Files/predicted_value_statistics.csv', index=False)


if __name__ == "__main__":
    db = data_base()
    db.clean_data()
