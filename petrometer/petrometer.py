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

import argparse
import csv
import datetime
import sys
import json

import os

import errno
from itertools import groupby, chain

import numpy
import pytz
import requests
import time
from appdirs import user_cache_dir
from texttable import Texttable
from tinydb import TinyDB, JSONStorage, Query
from tinydb.middlewares import CachingMiddleware
from babel.numbers import format_decimal

HTTP_TIMEOUT = 26


class Petrometer:
    """Class which summarizes daily and total gas consumption of all transactions sent
    from or received by one or more specified Ethereum addresses"""

    def __init__(self, args: list):
        parser = argparse.ArgumentParser(prog="petrometer")
        parser.add_argument(
            "addresses",
            metavar="ADDRESSES",
            nargs="+",
            type=str,
            help="Ethereum addresses to get the gas usage of",
        )
        parser.add_argument(
            "--etherscan-api-key", help="Etherscan API key", required=True, type=str
        )
        parser.add_argument(
            "--graphite-key",
            help="Graphite API key",
            required=False,
            type=str,
        )
        parser.add_argument(
            "--graphite-endpoint",
            help="Graphite Endpoint",
            required=False,
            type=str,
        )
        parser.add_argument("--alias", help="Address alias", required=False, type=str)
        parser.add_argument(
            "-j",
            "--json",
            help="Generate result as JSON",
            dest="json",
            action="store_true",
        )
        parser.add_argument(
            "-o",
            "--output",
            help="File to save the output to",
            required=False,
            type=str,
        )
        parser.add_argument(
            "-i",
            "--incoming",
            help="Show incoming transaction gas usage, defaut outgoing",
            required=False,
            action="store_true",
        )

        self.arguments = parser.parse_args(args)
        if self.arguments.graphite_key and (
            self.arguments.alias is None or self.arguments.graphite_endpoint is None
        ):
            parser.error(
                "The --graphite-key argument requires both --alias and --graphite-endpoint to be set"
            )

    def main(self):
        """Main method"""
        transactions = list(
            chain.from_iterable(
                self.get_transactions(address) for address in self.arguments.addresses
            )
        )
        eth_prices = self.get_eth_prices()

        result = self.daily_gas_usage(transactions, eth_prices)
        if self.arguments.json:
            result = json.dumps(result)

        if self.arguments.output is not None:
            with open(self.arguments.output, "w", encoding="UTF-8") as file:
                file.write(result)

        else:
            print(result)

    def daily_gas_usage(self, transactions, eth_prices):
        """Outputs the usage of transaction gas per day"""
        transactions = sorted(transactions, key=lambda tx: int(tx["timeStamp"]))

        def table_data():
            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)
                day_eth_price = eth_prices.get(int(day.timestamp()))

                yield [
                    day.strftime("%Y-%m-%d"),
                    (len(day_transactions)),
                    (self.failed_transactions(day_transactions)),
                    "(%.1f%%)"
                    % self.percentage(
                        self.failed_transactions(day_transactions)
                        / len(day_transactions)
                    ),
                    "%.1f GWei" % self.avg_gas_price(day_transactions),
                    "%.8f ETH" % self.avg_gas_cost(day_transactions),
                    (
                        "(%s)"
                        % self.format_usd(
                            self.avg_gas_cost(day_transactions) * day_eth_price
                        )
                    )
                    if day_eth_price is not None
                    else "",
                    "%.8f ETH" % self.total_gas_cost(day_transactions),
                    (
                        "(%s)"
                        % self.format_usd(
                            self.total_gas_cost(day_transactions) * day_eth_price
                        )
                    )
                    if day_eth_price is not None
                    else "",
                ]

        def json_data():
            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)
                day_eth_price = eth_prices.get(int(day.timestamp()))

                yield {
                    "day": day.strftime("%Y-%m-%d"),
                    "all_tx": len(day_transactions),
                    "failed_tx": self.failed_transactions(day_transactions),
                    "avg_gas_price": self.avg_gas_price(day_transactions),
                    "avg_tx_cost_eth": self.avg_gas_cost(day_transactions),
                    "avg_tx_cost_usd": self.avg_gas_cost(day_transactions)
                    * day_eth_price
                    if day_eth_price is not None
                    else "",
                    "total_tx_cost_eth": self.total_gas_cost(day_transactions),
                    "total_tx_cost_usd": self.total_gas_cost(day_transactions)
                    * day_eth_price
                    if day_eth_price is not None
                    else "",
                }

        def total_usd_cost():
            result = 0.0

            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)
                day_eth_price = eth_prices.get(int(day.timestamp()))
                if day_eth_price:
                    result += self.total_gas_cost(day_transactions) * day_eth_price

            return result

        if self.arguments.json:
            return list(json_data())

        table = Texttable(max_width=250)
        table.set_deco(Texttable.HEADER)
        table.set_cols_dtype(["t", "t", "t", "t", "t", "t", "t", "t", "t"])
        table.set_cols_align(["l", "r", "r", "r", "r", "r", "r", "r", "r"])
        table.set_cols_width([11, 10, 10, 8, 25, 20, 9, 20, 12])
        table.add_rows(
            [
                [
                    "Day",
                    "All tx",
                    "Failed tx",
                    "(%)",
                    "Average gas price",
                    "Average tx cost",
                    "($)",
                    "Total tx cost",
                    "($)",
                ]
            ]
            + list(table_data())
        )

        direction = "incoming" if self.arguments.incoming else "sent"
        indent = 36 if self.arguments.incoming else 32
        addresses = ("\n" + indent * " ").join(self.arguments.addresses)

        return (
            "\n"
            + f"Gas usage summary for {direction} tx : {addresses}\n\n"
            + table.draw()
            + "\n\n"
            + f"Number of {direction} transactions: {len(transactions)}\n"
            + f"Total gas cost: {self.total_gas_cost(transactions):.8f} ETH"
            + " ("
            + self.format_usd(total_usd_cost())
            + ")\n"
        )

    def failed_transactions(self, transactions):
        """Returns the amount of failed transactions"""
        return len(list(filter(self.is_failed, transactions)))

    @staticmethod
    def percentage(ratio):
        """Returns the percentage of the given ratio"""
        return ratio * 100.0

    def avg_gas_price(self, transactions):
        """Returns average gas price of given transactions"""
        return numpy.mean(list(map(self.gas_price, transactions))) / 10**9

    def avg_gas_cost(self, transactions):
        """Returns average gas cost of given transactions"""
        return numpy.mean(list(map(self.gas_cost, transactions))) / 10**18

    def total_gas_cost(self, transactions):
        """Returns total amount of gas cost of given transactions"""
        return sum(map(self.gas_cost, transactions)) / 10**18

    @staticmethod
    def by_day(transaction: dict):
        """Returns the day of given transaction"""
        transaction_timestamp = datetime.datetime.fromtimestamp(
            int(transaction["timeStamp"]), tz=pytz.UTC
        )
        return transaction_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def is_failed(transaction: dict) -> int:
        """Returns flag whether given transaction is failed or not"""
        return transaction["txreceipt_status"] == "0"

    @staticmethod
    def gas_price(transaction: dict) -> int:
        """Returns gas price of a given transaction"""
        return int(transaction["gasPrice"])

    @staticmethod
    def gas_cost(transaction: dict) -> int:
        """Returns gas cost of a given transaction"""
        return int(transaction["gasUsed"]) * int(transaction["gasPrice"])

    @staticmethod
    def format_usd(val):
        """Formats value following USD common way"""
        return format_decimal(val, format="$#,##0.00", locale="en_US")

    def get_transactions(self, address: str) -> list:
        """Returns transactions by given address"""
        with self.get_db(address) as db:
            print(
                f"Found {len(db.all())} transactions for '{address}' in local cache.",
                file=sys.stderr,
            )
            print("Fetching new transactions from etherscan.io...", file=sys.stderr)

            while True:
                # Get all existing transactions in the db
                all_transactions = db.all()
                existing_hashes = set(map(lambda tx: tx["hash"], all_transactions))
                max_block_number = (
                    max(map(lambda tx: int(tx["blockNumber"]), all_transactions))
                    if len(all_transactions) > 0
                    else 13268736
                )

                # Fetch a new batch of transactions, select only the new ones
                new_transactions = []
                for transaction in self.fetch_transactions(address, max_block_number):
                    if transaction["hash"] not in existing_hashes:
                        existing_hashes.add(transaction["hash"])
                        new_transactions.append(transaction)

                # Insert new transactions into the db
                db.insert_multiple(new_transactions)

                # We carry on until no new transactions are being discovered
                if len(new_transactions) > 0:
                    print(
                        f"Fetched {len(new_transactions)} new transactions (block number #{max_block_number})...",
                        file=sys.stderr,
                    )
                    grafana_payload = []
                    for transaction in new_transactions:
                        gas = (int(transaction["gasPrice"]) / 10**18) * int(
                            transaction["gasUsed"]
                        )
                        print(
                            f"Tx: {transaction['hash']} | timestamp: {transaction['timeStamp']} | Gas used: {gas}"
                        )

                        if self.arguments.graphite_key is not None:
                            grafana_payload.append(
                                {
                                    "name": f"gasUsage.{self.arguments.alias or ''}",
                                    "value": gas,
                                    "interval": 5,
                                    "time": int(transaction["timeStamp"]),
                                }
                            )

                    # Only posting data to Grafana when --graphite-key is set
                    if self.arguments.graphite_key is not None:
                        self.post_to_grafana(
                            grafana_payload,
                            self.arguments.graphite_key,
                            self.arguments.graphite_endpoint,
                        )
                else:
                    print(
                        "All new transactions fetched from etherscan.io.",
                        file=sys.stderr,
                    )
                    break

            if self.arguments.incoming:
                direction = "to"
            else:
                direction = "from"
            return list(
                filter(lambda tx: tx[direction].lower() == address.lower(), db.all())
            )

    @staticmethod
    def get_db(address: str):
        """Returns TinyDB connector"""
        db_folder = user_cache_dir("petrometer", "maker")

        try:
            os.makedirs(db_folder)
        except OSError as error:
            if error.errno != errno.EEXIST:
                raise

        db_file = os.path.join(db_folder, address.lower() + ".txdb")
        return TinyDB(db_file, storage=CachingMiddleware(JSONStorage))

    def fetch_transactions(self, address: str, start_block: int) -> list:
        """Returns transactions of given address starting from given block"""
        assert isinstance(address, str)
        assert isinstance(start_block, int)

        url = (
            f"https://api.etherscan.io/api?module=account&"
            f"action=txlist&"
            f"address={address.lower()}&"
            f"startblock={start_block}&"
            f"endblock=99999999&"
            f"page=1&"
            f"offset=100&"
            f"sort=asc&"
            f"apikey={self.arguments.etherscan_api_key}"
        )

        # Always wait some time before sending a request
        # as we do not want to be banned by etherscan.io
        time.sleep(0.2)

        result = requests.get(url, timeout=HTTP_TIMEOUT).json()

        if result["message"] == "OK":
            return result["result"]

        elif result["message"] == "No transactions found":
            return []

        else:
            raise Exception(f"Invalid etherscan.io response: {result}")

    @staticmethod
    def get_eth_prices():
        """Gets the daily price of ETH grouped by days"""
        response = requests.get(
            "https://api.coingecko.com/api/v3/coins/ethereum/market_chart",
            params={"vs_currency": "usd", "days": "max", "interval": "daily"},
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch historical ETH prices from coingecko.com:"
                f" {response.status_code} {response.reason} ({response.text})"
            )

        prices_json = response.json()["prices"]
        prices = {}
        for price in prices_json:
            prices[price[0] / 1000] = price[1]

        return prices

    @staticmethod
    def post_to_grafana(data, graphite_key, graphite_endpoint):
        """Constructs the payload containing transactions data
        and posts it to Graphite (Grafana's Input Source)"""
        if "PYTEST_CURRENT_TEST" in os.environ:
            print("Running tests, ignoring")
        else:
            result = requests.request(
                method="POST",
                url=graphite_endpoint,
                data=json.dumps(data, separators=(",", ":")),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {graphite_key}",
                },
                timeout=60,
            )
            if result.ok:
                print("Succesfully posted metric to Grafana")
            else:
                print(f"Unable to post metric to Grafana, responce is {result.json()}")


if __name__ == "__main__":
    Petrometer(sys.argv[1:]).main()
