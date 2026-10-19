"""Service layer for the ActivityBasedCuration (ABC) replacement.

Functions here take an ``asyncpg.Connection`` rather than the ``Database``
dependency so that a route can run several of them in one transaction and so
that tests can wrap each case in a transaction that is rolled back.
"""
