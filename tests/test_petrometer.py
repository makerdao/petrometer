# This file is part of Petrometer.
#
# Copyright (C) 2018 reverendus
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import sys
from contextlib import contextmanager
from io import StringIO

import os
import py
import pytest
import requests_mock
from appdirs import user_cache_dir
from pytest import fixture

from petrometer.petrometer import Petrometer


@contextmanager
def captured_output():
    new_out, new_err = StringIO(), StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    try:
        sys.stdout, sys.stderr = new_out, new_err
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr = old_out, old_err


@fixture
def datadir(request):
    return py.path.local(request.module.__file__).join("..").join("data")


def args(arguments):
    return arguments.split()


class TestPlunger:
    @staticmethod
    def mock_api(mock, datadir):
        mock.get("https://api.etherscan.io/api?module=account&action=txlist&address=0x52a043195a2803cc7e75f17f5c9d4f84ffa33211&startblock=0&endblock=99999999&page=1&offset=100&sort=asc&apikey=SOMEKEY",
                 text=datadir.join('startblock_0.json').read_text('utf-8'))

        mock.get("https://api.etherscan.io/api?module=account&action=txlist&address=0x52a043195a2803cc7e75f17f5c9d4f84ffa33211&startblock=4981201&endblock=99999999&page=1&offset=100&sort=asc&apikey=SOMEKEY",
                 text=datadir.join('startblock_4981201.json').read_text('utf-8'))

    def test_should_print_usage_when_no_arguments(self):
        # when
        with captured_output() as (out, err):
            with pytest.raises(SystemExit):
                Petrometer(args(""))

        # then
        assert "usage: petrometer" in err.getvalue()
        assert "petrometer: error: the following arguments are required: ADDRESSES, --etherscan-api-key" in err.getvalue()

    def test_happy_path(self, datadir):
        # remove local cache file
        try:
            db_folder = user_cache_dir("petrometer", "maker")
            db_file = os.path.join(db_folder, "0x52a043195a2803cc7e75f17f5c9d4f84ffa33211.txdb")
            os.remove(db_file)
        except:
            pass

        # run `petrometer`
        with captured_output() as (out, err):
            # when
            with requests_mock.Mocker(real_http=True) as mock:
                self.mock_api(mock, datadir)
                Petrometer(args(f"--etherscan-api-key SOMEKEY 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211")).main()

            # then
            assert out.getvalue() == f"""Found 0 transactions for '0x52a043195a2803cc7e75f17f5c9d4f84ffa33211' in local cache.
Fetching new transactions from etherscan.io...
Fetched 72 new transactions (block number #0)...
All new transactions fetched from etherscan.io.

Gas usage summary for: 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211

    Day         All tx     Failed tx      (%)          Average gas price         Average tx cost        ($)         Total tx cost           ($)
====================================================================================================================================================
2017-12-29            16            0     (0.0%)                    3.6 GWei         0.00972251 ETH    ($7.19)         0.15556020 ETH      ($115.05)
2017-12-30            21            0     (0.0%)                    2.5 GWei         0.00953677 ETH    ($6.61)         0.20027212 ETH      ($138.79)
2017-12-31            10            0     (0.0%)                    3.9 GWei         0.00703955 ETH    ($5.22)         0.07039553 ETH       ($52.17)
2018-01-01             2            0     (0.0%)                    2.1 GWei         0.00413893 ETH    ($3.13)         0.00827785 ETH        ($6.26)
2018-01-03             1            0     (0.0%)                   20.0 GWei         0.00061472 ETH    ($0.58)         0.00061472 ETH        ($0.58)
2018-01-05             1            0     (0.0%)                   40.0 GWei         0.03426612 ETH   ($33.14)         0.03426612 ETH       ($33.14)
2018-01-27            20            1     (5.0%)                    3.7 GWei         0.00889380 ETH    ($9.86)         0.17787595 ETH      ($197.28)

Number of transactions: 71
Total gas cost: 0.64768249 ETH ($543.27)

"""

        # keep local cache as `plunger` left it

        # run `petrometer` again
        with captured_output() as (out, err):
            # when
            with requests_mock.Mocker(real_http=True) as mock:
                self.mock_api(mock, datadir)
                Petrometer(args(f"--etherscan-api-key SOMEKEY 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211")).main()

            # then
            assert out.getvalue() == f"""Found 72 transactions for '0x52a043195a2803cc7e75f17f5c9d4f84ffa33211' in local cache.
Fetching new transactions from etherscan.io...
All new transactions fetched from etherscan.io.

Gas usage summary for: 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211

    Day         All tx     Failed tx      (%)          Average gas price         Average tx cost        ($)         Total tx cost           ($)
====================================================================================================================================================
2017-12-29            16            0     (0.0%)                    3.6 GWei         0.00972251 ETH    ($7.19)         0.15556020 ETH      ($115.05)
2017-12-30            21            0     (0.0%)                    2.5 GWei         0.00953677 ETH    ($6.61)         0.20027212 ETH      ($138.79)
2017-12-31            10            0     (0.0%)                    3.9 GWei         0.00703955 ETH    ($5.22)         0.07039553 ETH       ($52.17)
2018-01-01             2            0     (0.0%)                    2.1 GWei         0.00413893 ETH    ($3.13)         0.00827785 ETH        ($6.26)
2018-01-03             1            0     (0.0%)                   20.0 GWei         0.00061472 ETH    ($0.58)         0.00061472 ETH        ($0.58)
2018-01-05             1            0     (0.0%)                   40.0 GWei         0.03426612 ETH   ($33.14)         0.03426612 ETH       ($33.14)
2018-01-27            20            1     (5.0%)                    3.7 GWei         0.00889380 ETH    ($9.86)         0.17787595 ETH      ($197.28)

Number of transactions: 71
Total gas cost: 0.64768249 ETH ($543.27)

"""
