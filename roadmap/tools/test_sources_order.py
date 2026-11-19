from pathlib import Path
import unittest

from build_sources import station_order


class SourcesOrder(unittest.TestCase):
    def test_equal_station_numbers_have_a_stable_reading_order(self):
        names = ['station5', 'station5-linux', 'station7', 'station7-netlab',
                 'station7-traffic', 'station8', 'station9-sql', 'station9', 'station10']
        paths = [Path(n + '.json') for n in names]
        for input_order in (paths, reversed(paths), paths[::2] + paths[1::2]):
            self.assertEqual([p.stem for p in sorted(input_order, key=station_order)], names)
