#!/usr/bin/env python3
#
# show_metric.py: depicts how the intrinsic graph metric changes as
# a function of the number of Weisfeiler--Lehman hops.


import igraph as ig
import numpy as np

import matplotlib.animation as animation
import matplotlib.pyplot as plt

import argparse
import sys

from features import WeisfeilerLehman
from features import WeightAssigner

from itertools import cycle


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('FILE', help='Input graph')
    parser.add_argument('-n', '--num-iterations', default=3, type=int, help='Number of Weisfeiler-Lehman iterations')

    args = parser.parse_args()
    graph = ig.read(args.FILE)

    wl = WeisfeilerLehman()
    wa = WeightAssigner(metric='minkowski', p=2.0)  # TODO: make configurable

    label_dicts = wl.fit_transform([graph], args.num_iterations)
    graph_index = 0

    fig = plt.figure()
    matrices = []

    for iteration in sorted(label_dicts.keys()):
        weighted_graph = graph.copy()

        labels_raw, labels_compressed = label_dicts[iteration][graph_index]

        weighted_graph.vs['label'] = labels_raw
        weighted_graph.vs['compressed_label'] = labels_compressed

        weighted_graph = wa.fit_transform(weighted_graph)

        A = weighted_graph.get_adjacency(default=np.nan, attribute='weight')
        matrices.append(np.array(A.data))

    vmin = 0
    vmax = sys.float_info.min
    for matrix in matrices:
        vmax = max(vmax, np.nanmax(matrix))

    matrix_iterator = cycle(matrices)
    im = plt.imshow(next(matrix_iterator), animated=True, vmin=vmin, vmax=vmax)

    def update_matrix(*args):
        im.set_data(next(matrix_iterator))
        return im,

    ani = animation.FuncAnimation(fig, update_matrix, interval=1000, blit=True)
    plt.colorbar()
    plt.show()
