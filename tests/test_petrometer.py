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


class TestPetrometer:
    def __init__(self) -> None:
        try:
            os.environ["ETHERSCAN_API_KEY"]
        except Exception:
            print("No ETHERSCAN_API_KEY environment variable passed, exiting")
            sys.exit(2)

    @staticmethod
    def mock_api(mock, datadir):
        mock.get(
            "https://api.etherscan.io/api?module=account&action=txlist&address=0x52a043195a2803cc7e75f17f5c9d4f84ffa33211&startblock=0&endblock=99999999&page=1&offset=100&sort=asc&apikey={}".format(
                os.environ["ETHERSCAN_API_KEY"]
            ),
            text=datadir.join("startblock_0.json").read_text("utf-8"),
        )

        mock.get(
            "https://api.etherscan.io/api?module=account&action=txlist&address=0x52a043195a2803cc7e75f17f5c9d4f84ffa33211&startblock=4981201&endblock=99999999&page=1&offset=100&sort=asc&apikey={}".format(
                os.environ["ETHERSCAN_API_KEY"]
            ),
            text=datadir.join("startblock_4981201.json").read_text("utf-8"),
        )

        mock.get(
            "https://api.etherscan.io/api?module=account&action=txlist&address=0x9041fe5b3fdea0f5e4afdc17e75180738d877a01&startblock=0&endblock=99999999&page=1&offset=100&sort=asc&apikey={}".format(
                os.environ["ETHERSCAN_API_KEY"]
            ),
            text=datadir.join("addr2_startblock_0.json").read_text("utf-8"),
        )

        mock.get(
            "https://api.etherscan.io/api?module=account&action=txlist&address=0x9041fe5b3fdea0f5e4afdc17e75180738d877a01&startblock=4981201&endblock=99999999&page=1&offset=100&sort=asc&apikey={}".format(
                os.environ["ETHERSCAN_API_KEY"]
            ),
            text=datadir.join("addr2_startblock_4981201.json").read_text("utf-8"),
        )

    def test_should_print_usage_when_no_arguments(self):
        # when
        with captured_output() as (out, err):
            with pytest.raises(SystemExit):
                Petrometer(args(""))

        # then
        assert "usage: petrometer" in err.getvalue()
        assert (
            "petrometer: error: the following arguments are required: ADDRESSES, --etherscan-api-key, --ethfiller-key, --alias"
            in err.getvalue()
        )

    def test_happy_path(self, datadir):
        # remove local cache file
        try:
            db_folder = user_cache_dir("petrometer", "maker")
            db_file = os.path.join(
                db_folder, "0x52a043195a2803cc7e75f17f5c9d4f84ffa33211.txdb"
            )
            os.remove(db_file)
        except:
            pass

        # run `petrometer`
        with captured_output() as (out, err):
            # when
            with requests_mock.Mocker(real_http=True) as mock:
                self.mock_api(mock, datadir)
                Petrometer(
                    args(
                        "--etherscan-api-key {} --ethfiller-key SOMEGRAPHITEKEY 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211 --alias SOMEALIAS".format(
                            os.environ["ETHERSCAN_API_KEY"]
                        )
                    )
                ).main()

            # then
            assert (
                out.getvalue()
                == f"""
Gas usage summary for sent tx : 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211

    Day         All tx     Failed tx      (%)          Average gas price         Average tx cost         ($)         Total tx cost           ($)     
=====================================================================================================================================================
2017-12-29            16            0     (0.0%)                    3.6 GWei         0.00972251 ETH     ($7.34)         0.15556020 ETH      ($117.50)
2017-12-30            21            0     (0.0%)                    2.5 GWei         0.00953677 ETH     ($7.03)         0.20027212 ETH      ($147.58)
2017-12-31            10            0     (0.0%)                    3.9 GWei         0.00703955 ETH     ($5.45)         0.07039553 ETH       ($54.54)
2018-01-01             2            0     (0.0%)                    2.1 GWei         0.00413893 ETH     ($3.21)         0.00827785 ETH        ($6.42)
2018-01-03             1            0     (0.0%)                   20.0 GWei         0.00061472 ETH     ($0.59)         0.00061472 ETH        ($0.59)
2018-01-05             1            0     (0.0%)                   40.0 GWei         0.03426612 ETH    ($34.43)         0.03426612 ETH       ($34.43)
2018-01-27            20            1     (5.0%)                    3.7 GWei         0.00889380 ETH     ($9.75)         0.17787595 ETH      ($194.91)

Number of sent transactions: 71
Total gas cost: 0.64726249 ETH ($555.98)

"""
            )

        # keep local cache

        # run `petrometer` again
        with captured_output() as (out, err):
            # when

            with requests_mock.Mocker(real_http=True) as mock:
                self.mock_api(mock, datadir)
                Petrometer(
                    args(
                        "--etherscan-api-key {} --ethfiller-key SOMEGRAPHITEKEY 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211 --alias SOMEALIAS".format(
                            os.environ["ETHERSCAN_API_KEY"]
                        )
                    )
                ).main()

            # then
            assert (
                out.getvalue()
                == f"""
Gas usage summary for sent tx : 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211

    Day         All tx     Failed tx      (%)          Average gas price         Average tx cost         ($)         Total tx cost           ($)     
=====================================================================================================================================================
2017-12-29            16            0     (0.0%)                    3.6 GWei         0.00972251 ETH     ($7.34)         0.15556020 ETH      ($117.50)
2017-12-30            21            0     (0.0%)                    2.5 GWei         0.00953677 ETH     ($7.03)         0.20027212 ETH      ($147.58)
2017-12-31            10            0     (0.0%)                    3.9 GWei         0.00703955 ETH     ($5.45)         0.07039553 ETH       ($54.54)
2018-01-01             2            0     (0.0%)                    2.1 GWei         0.00413893 ETH     ($3.21)         0.00827785 ETH        ($6.42)
2018-01-03             1            0     (0.0%)                   20.0 GWei         0.00061472 ETH     ($0.59)         0.00061472 ETH        ($0.59)
2018-01-05             1            0     (0.0%)                   40.0 GWei         0.03426612 ETH    ($34.43)         0.03426612 ETH       ($34.43)
2018-01-27            20            1     (5.0%)                    3.7 GWei         0.00889380 ETH     ($9.75)         0.17787595 ETH      ($194.91)

Number of sent transactions: 71
Total gas cost: 0.64726249 ETH ($555.98)

"""
            )

    def test_with_two_addresses(self, datadir):
        # remove local cache file
        try:
            db_folder = user_cache_dir("petrometer", "maker")
            db_file = os.path.join(
                db_folder, "0x52a043195a2803cc7e75f17f5c9d4f84ffa33211.txdb"
            )
            db_file = os.path.join(
                db_folder, "0x9041fe5b3fdea0f5e4afdc17e75180738d877a01.txdb"
            )
            os.remove(db_file)
        except:
            pass

        # run `petrometer`
        with captured_output() as (out, err):
            # when
            with requests_mock.Mocker(real_http=True) as mock:
                self.mock_api(mock, datadir)
                Petrometer(
                    args(
                        "--etherscan-api-key {} --ethfiller-key SOMEGRAPHITEKEY 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211 0x9041fe5b3fdea0f5e4afdc17e75180738d877a01 --alias SOMEALIAS".format(
                            os.environ["ETHERSCAN_API_KEY"]
                        )
                    )
                ).main()

            # then
            assert (
                out.getvalue()
                == f"""
Gas usage summary for sent tx : 0x52a043195a2803cc7e75f17f5c9d4f84ffa33211
                                0x9041fe5b3fdea0f5e4afdc17e75180738d877a01

    Day         All tx     Failed tx      (%)          Average gas price         Average tx cost         ($)         Total tx cost           ($)     
=====================================================================================================================================================
2017-12-29            16            0     (0.0%)                    3.6 GWei         0.00972251 ETH     ($7.34)         0.15556020 ETH      ($117.50)
2017-12-30            21            0     (0.0%)                    2.5 GWei         0.00953677 ETH     ($7.03)         0.20027212 ETH      ($147.58)
2017-12-31            10            0     (0.0%)                    3.9 GWei         0.00703955 ETH     ($5.45)         0.07039553 ETH       ($54.54)
2018-01-01             2            0     (0.0%)                    2.1 GWei         0.00413893 ETH     ($3.21)         0.00827785 ETH        ($6.42)
2018-01-03             1            0     (0.0%)                   20.0 GWei         0.00061472 ETH     ($0.59)         0.00061472 ETH        ($0.59)
2018-01-05             1            0     (0.0%)                   40.0 GWei         0.03426612 ETH    ($34.43)         0.03426612 ETH       ($34.43)
2018-01-15             1            0     (0.0%)                    2.1 GWei         0.00828180 ETH    ($11.01)         0.00828180 ETH       ($11.01)
2018-01-27            22            1     (4.5%)                    3.5 GWei         0.00881993 ETH     ($9.66)         0.19403849 ETH      ($212.62)

Number of sent transactions: 74
Total gas cost: 0.67170682 ETH ($584.71)

"""
            )
