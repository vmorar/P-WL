#!/usr/bin/env python3
#
# persistence_diagrams.py: creates persistence diagrams for Persistent
# Weisfeiler--Lehman graph kernel features.

import igraph as ig
import numpy as np

import matplotlib.pyplot as plt
import seaborn as sns

import argparse
import collections
import logging
import sys

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder
from sklearn.preprocessing import MinMaxScaler
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from features import FeatureSelector
from features import PersistentWeisfeilerLehman

from utilities import read_labels


def to_probability_distribution(persistence_diagram, C):
    '''
    Converts a persistence diagram with labels to a (discrete)
    probability distribution.

    :param persistence_diagram: Persistence diagram
    :param C: Maximum number of labels of discrete distribution

    :return: Discrete probability distribution
    '''

    P = np.zeros(C)

    for x, y, c in persistence_diagram:

        # Just to make sure that this mapping can work
        assert c < C
        assert c >= 0

        # TODO: make power configurable?
        P[c] += (y - x)**2

    # Ensures that this distribution is valid, i.e. normalized to sum to
    # one; else, we are implicitly comparing distributions whose size or
    # weight varies.
    P = P / np.sum(P)
    return P


def kullback_leibler(p, q):
    '''
    Calculates the Kullback--Leibler divergence between two discrete
    probability distributions.

    :param p: First discrete probability distribution
    :param q: Second discrete probability distribution

    :return: Value of Kullback--Leibler divergence
    '''

    return np.sum(np.where(p != 0, p * np.log(q / p), 0))


def jensen_shannon(p, q):
    '''
    Calculates the Jensen--Shannon divergence between two discrete
    probability distributions.

    :param p: First discrete probability distribution
    :param q: Second discrete probability distribution

    :return: Value of Jensen--Shannon divergence
    '''

    return 0.5 * (kullback_leibler(p, q) + kullback_leibler(q, p))


def main(args, logger):

    graphs = [ig.read(filename) for filename in args.FILES]
    labels = read_labels(args.labels)

    # Set the label to be uniform over all graphs in case no labels are
    # available. This essentially changes our iteration to degree-based
    # checks.
    for graph in graphs:
        if 'label' not in graph.vs.attributes():
            graph.vs['label'] = [0] * len(graph.vs)

    logger.info('Read {} graphs and {} labels'.format(len(graphs), len(labels)))

    assert len(graphs) == len(labels)

    pwl = PersistentWeisfeilerLehman(
            use_cycle_persistence=args.use_cycle_persistence,
            use_original_features=args.use_original_features,
            use_label_persistence=True,
            store_persistence_diagrams=True,
    )

    if args.use_cycle_persistence:
        logger.info('Using cycle persistence')

    y = LabelEncoder().fit_transform(labels)
    X, num_columns_per_iteration = pwl.transform(graphs, args.num_iterations)

    persistence_diagrams = pwl._persistence_diagrams

    # Will store *all* persistence diagrams in a compressed form, i.e.
    # as a sequence of vertex destruction values.
    M = np.zeros((len(graphs), args.num_iterations))

    fig, ax = plt.subplots(args.num_iterations + 1)

    for iteration in persistence_diagrams.keys():
        M = collections.defaultdict(list)

        for index, pd in enumerate(persistence_diagrams[iteration]):
            label = y[index]
            for _, d, _ in pd:
                M[label].append(d)

        d_min = sys.float_info.max
        d_max = -d_min

        for hist in M.values():
            d_min = min(d_min, min(hist))
            d_max = max(d_max, max(hist))

        bins = np.linspace(d_min, d_max, 10)

        for label, hist in M.items():
            sns.distplot(hist,
                bins=bins,
                rug=True,
                kde=True,
                hist=False,
                ax=ax[iteration])

    plt.show()

    raise 'heck'

    logger.info('Finished persistent Weisfeiler-Lehman transformation')
    logger.info('Obtained ({} x {}) feature matrix'.format(X.shape[0], X.shape[1]))

    np.random.seed(42)
    cv = StratifiedKFold(n_splits=10, shuffle=True)
    mean_accuracies = []

    for i in range(10):

        # Contains accuracy scores for each cross validation step; the
        # means of this list will be used later on.
        accuracy_scores = []

        for train_index, test_index in cv.split(X, y):
            rf_clf = RandomForestClassifier(
                n_estimators=50,
                class_weight='balanced' if args.balanced else None
            )

            if args.grid_search:
                pipeline = Pipeline(
                    [
                        ('fs', FeatureSelector(num_columns_per_iteration)),
                        ('clf', rf_clf)
                    ],
                )

                grid_params = {
                    'fs__num_iterations': np.arange(0, args.num_iterations + 1),
                    'clf__n_estimators': [10, 20, 50, 100, 150, 200],
                }

                clf = GridSearchCV(
                        pipeline,
                        grid_params,
                        cv=StratifiedKFold(n_splits=10, shuffle=True),
                        iid=False,
                        scoring='accuracy',
                        n_jobs=4)
            else:
                clf = rf_clf

            X_train, X_test = X[train_index], X[test_index]
            y_train, y_test = y[train_index], y[test_index]

            # TODO: need to discuss whether this is 'allowed' or smart
            # to do; this assumes normality of the attributes.
            scaler = StandardScaler()
            X_train = scaler.fit_transform(X_train)
            X_test = scaler.transform(X_test)

            scaler = MinMaxScaler()
            X_train = scaler.fit_transform(X_train)
            X_test = scaler.transform(X_test)

            clf.fit(X_train, y_train)
            y_pred = clf.predict(X_test)

            importances = np.argsort(clf.feature_importances_)[::-1][:20]
            print(min(importances), max(importances))

            accuracy_scores.append(accuracy_score(y_test, y_pred))

            logger.debug('Best classifier for this fold: {}'.format(clf))

            if args.grid_search:
                logger.debug('Best parameters for this fold: {}'.format(clf.best_params_))
            else:
                logger.debug('Best parameters for this fold: {}'.format(clf.get_params()))

        mean_accuracies.append(np.mean(accuracy_scores))
        logger.info('  - Mean 10-fold accuracy: {:2.2f} [running mean over all folds: {:2.2f}]'.format(mean_accuracies[-1] * 100, np.mean(mean_accuracies) * 100))

    logger.info('Accuracy: {:2.2f} +- {:2.2f}'.format(np.mean(mean_accuracies) * 100, np.std(mean_accuracies) * 100))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('FILES', nargs='+', help='Input graphs (in some supported format)')
    parser.add_argument('-b', '--balanced', action='store_true', help='Make random forest classifier balanced')
    parser.add_argument('-d', '--dataset', help='Name of data set')
    parser.add_argument('-l', '--labels', type=str, help='Labels file', required=True)
    parser.add_argument('-n', '--num-iterations', default=3, type=int, help='Number of Weisfeiler-Lehman iterations')
    parser.add_argument('-f', '--filtration', type=str, default='sublevel', help='Filtration type')
    parser.add_argument('-g', '--grid-search', action='store_true', default=False, help='Whether to do hyperparameter grid search')
    parser.add_argument('-c', '--use-cycle-persistence', action='store_true', default=False, help='Indicates whether cycle persistence should be calculated or not')
    parser.add_argument('-o', '--use-original-features', action='store_true', default=False, help='Indicates that original features should be used as well')

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG,
        filename='{}_{:02d}.log'.format(args.dataset, args.num_iterations)
    )

    logger = logging.getLogger('P-WL')

    # Create a second stream handler for logging to `stderr`, but set
    # its log level to be a little bit smaller such that we only have
    # informative messages
    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)

    # Use the default format; since we do not adjust the logger before,
    # this is all right.
    stream_handler.setFormatter(logging.Formatter(logging.BASIC_FORMAT))
    logger.addHandler(stream_handler)

    main(args, logger)