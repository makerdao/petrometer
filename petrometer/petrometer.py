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
    def __init__(self, args: list):
        parser = argparse.ArgumentParser(prog='petrometer')
        parser.add_argument("addresses", metavar='ADDRESSES', nargs='+', type=str,
                            help="Ethereum addresses to get the gas usage of")
        parser.add_argument("--etherscan-api-key", help="Etherscan API key", required=True, type=str)
        parser.add_argument("-j", '--json', help="Generate result as JSON", dest='json', action='store_true')
        parser.add_argument("-o", "--output", help="File to save the output to", required=False, type=str)

        self.arguments = parser.parse_args(args)

    def main(self):
        transactions = list(chain.from_iterable(self.get_transactions(address) for address in self.arguments.addresses))
        eth_prices = self.get_eth_prices()

        result = self.daily_gas_usage(transactions, eth_prices)
        if self.arguments.json:
            result = json.dumps(result)

        if self.arguments.output is not None:
            with open(self.arguments.output, "w") as file:
                file.write(result)

        else:
            print(result)

    def daily_gas_usage(self, transactions, eth_prices):
        transactions = sorted(transactions, key=lambda tx: int(tx['timeStamp']))

        def table_data():
            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)
                day_eth_price = eth_prices.get(int(day.timestamp()))

                yield [day.strftime('%Y-%m-%d'),
                       (len(day_transactions)),
                       (self.failed_transactions(day_transactions)),
                       "(%.1f%%)" % self.percentage(self.failed_transactions(day_transactions) / len(day_transactions)),
                       "%.1f GWei" % self.avg_gas_price(day_transactions),
                       "%.8f ETH" % self.avg_gas_cost(day_transactions),
                       ("(%s)" % self.format_usd(self.avg_gas_cost(day_transactions) * day_eth_price)) if day_eth_price is not None else "",
                       "%.8f ETH" % self.total_gas_cost(day_transactions),
                       ("(%s)" % self.format_usd(self.total_gas_cost(day_transactions) * day_eth_price)) if day_eth_price is not None else ""]

        def json_data():
            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)
                day_eth_price = eth_prices.get(int(day.timestamp()))

                yield {
                    'day': day.strftime('%Y-%m-%d'),
                    'all_tx': len(day_transactions),
                    'failed_tx': self.failed_transactions(day_transactions),
                    'avg_gas_price': self.avg_gas_price(day_transactions),
                    'avg_tx_cost_eth': self.avg_gas_cost(day_transactions),
                    'avg_tx_cost_usd': self.avg_gas_cost(day_transactions) * day_eth_price if day_eth_price is not None else "",
                    'total_tx_cost_eth': self.total_gas_cost(day_transactions),
                    'total_tx_cost_usd': self.total_gas_cost(day_transactions) * day_eth_price if day_eth_price is not None else ""
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
        table.set_cols_dtype(['t', 't', 't', 't', 't', 't', 't', 't', 't'])
        table.set_cols_align(['l', 'r', 'r', 'r', 'r', 'r', 'r', 'r', 'r'])
        table.set_cols_width([11, 10, 10, 8, 25, 20, 8, 20, 12])
        table.add_rows([["Day", "All tx", "Failed tx", "(%)", "Average gas price", "Average tx cost", "($)", "Total tx cost", "($)"]]
                       + list(table_data()))

        addresses = ("\n" + 23 * " ").join(self.arguments.addresses)

        return f"\n" + \
               f"Gas usage summary for: {addresses}\n\n" + \
               table.draw() + "\n\n" + \
               f"Number of transactions: {len(transactions)}\n" + \
               f"Total gas cost: %.8f ETH" % self.total_gas_cost(transactions) + " (" + self.format_usd(total_usd_cost()) + ")\n"

    def failed_transactions(self, transactions):
        return len(list(filter(self.is_failed, transactions)))

    @staticmethod
    def percentage(ratio):
        return ratio * 100.0

    def avg_gas_price(self, transactions):
        return numpy.mean(list(map(self.gas_price, transactions))) / 10 ** 9

    def avg_gas_cost(self, transactions):
        return numpy.mean(list(map(self.gas_cost, transactions))) / 10 ** 18

    def total_gas_cost(self, transactions):
        return sum(map(self.gas_cost, transactions)) / 10 ** 18

    @staticmethod
    def by_day(transaction: dict):
        transaction_timestamp = datetime.datetime.fromtimestamp(int(transaction['timeStamp']), tz=pytz.UTC)
        return transaction_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def is_failed(transaction: dict) -> int:
        return transaction['txreceipt_status'] == "0"

    @staticmethod
    def gas_price(transaction: dict) -> int:
        return int(transaction['gasPrice'])

    @staticmethod
    def gas_cost(transaction: dict) -> int:
        return int(transaction['gasUsed']) * int(transaction['gasPrice'])

    @staticmethod
    def format_usd(val):
        return format_decimal(val, format='$#,##0.00', locale='en_US')

    def get_transactions(self, address: str) -> list:
        with self.get_db(address) as db:
            print(f"Found {len(db.all())} transactions for '{address}' in local cache.", file=sys.stderr)
            print(f"Fetching new transactions from etherscan.io...", file=sys.stderr)

            while True:
                # Get all existing transactions in the db
                all_transactions = db.all()
                existing_hashes = set(map(lambda tx: tx['hash'], all_transactions))
                max_block_number = max(map(lambda tx: int(tx['blockNumber']), all_transactions)) \
                    if len(all_transactions) > 0 else 0

                # Fetch a new batch of transactions, select only the new ones
                new_transactions = []
                for transaction in self.fetch_transactions(address, max_block_number):
                    if transaction['hash'] not in existing_hashes:
                        existing_hashes.add(transaction['hash'])
                        new_transactions.append(transaction)

                # Insert new transactions into the db
                db.insert_multiple(new_transactions)

                # We carry on until no new transactions are being discovered
                if len(new_transactions) > 0:
                    print(f"Fetched {len(new_transactions)} new transactions (block number #{max_block_number})...", file=sys.stderr)
                else:
                    print(f"All new transactions fetched from etherscan.io.", file=sys.stderr)
                    break

            return list(filter(lambda tx: tx['from'].lower() == address.lower(), db.all()))

    @staticmethod
    def get_db(address: str):
        db_folder = user_cache_dir("petrometer", "maker")

        try:
            os.makedirs(db_folder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        db_file = os.path.join(db_folder, address.lower() + ".txdb")
        return TinyDB(db_file, storage=CachingMiddleware(JSONStorage))

    def fetch_transactions(self, address: str, start_block: int) -> list:
        assert(isinstance(address, str))
        assert(isinstance(start_block, int))

        url = f"https://api.etherscan.io/api?module=account&" \
              f"action=txlist&" \
              f"address={address.lower()}&" \
              f"startblock={start_block}&" \
              f"endblock=99999999&" \
              f"page=1&" \
              f"offset=100&" \
              f"sort=asc&" \
              f"apikey={self.arguments.etherscan_api_key}"

        # Always wait some time before sending a request as we do not want to be banned by etherscan.io
        time.sleep(0.2)

        result = requests.get(url, timeout=HTTP_TIMEOUT).json()

        if result['message'] == 'OK':
            return result['result']

        elif result['message'] == 'No transactions found':
            return []

        else:
            raise Exception(f"Invalid etherscan.io response: {result}")

    @staticmethod
    def get_eth_prices():
        response = requests.get("https://etherscan.io/chart/etherprice?output=csv",
                                headers={
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.76 Safari/537.36'
                                },
                                timeout=HTTP_TIMEOUT,
                                allow_redirects=False)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch historical ETH prices from etherscan.io:"
                            f" {response.status_code} {response.reason} ({response.text})")

        prices = {}

        prices_reader = csv.reader(response.text.split("\n"))
        for row in prices_reader:
            if len(row) == 3 and row[2] != "Value":
                prices[int(row[1])] = float(row[2])

        return prices


if __name__ == '__main__':
    Petrometer(sys.argv[1:]).main()
