"""Simulated scenarios: a world of entities and timed events, a claim checked by code, text last.

The blueprints start from hand-written lines and the label is whatever the lines were written to
mean. Here the order is reversed: `sample_world` draws a lab's events from distributions, the
claim's check (`check`) computes the label from those events, and only then are the events
phrased as log lines. A label can't disagree with its own timestamps, and every scenario carries
its attributes (how many facts decide it, how many of the links between them run through a
secret) as measurements rather than as the category it was built for.
"""
