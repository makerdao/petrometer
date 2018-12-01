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
import datetime
import sys

import os

import errno
from itertools import groupby

import numpy
import pytz
import requests
import time
from appdirs import user_cache_dir
from texttable import Texttable
from tinydb import TinyDB, JSONStorage, Query
from tinydb.middlewares import CachingMiddleware


class Petrometer:
    def __init__(self, args: list):
        parser = argparse.ArgumentParser(prog='petrometer')
        parser.add_argument("address", help="Ethereum address to get the gas usage of", type=str)
        parser.add_argument("--etherscan-api-key", help="Etherscan API key", required=True, type=str)

        self.arguments = parser.parse_args(args)

    def main(self):
        transactions = self.get_transactions()
        self.print_daily_gas_usage(transactions)

    def print_daily_gas_usage(self, transactions):
        def table_data(outgoing_transactions: list):
            for day, day_transactions in groupby(outgoing_transactions, self.by_day):
                day_transactions = list(day_transactions)

                yield [day.strftime('%Y-%m-%d'),
                       (len(day_transactions)),
                       "%.1f GWei" % self.avg_gas_price(day_transactions),
                       "%.8f ETH" % self.avg_gas_cost(day_transactions),
                       "%.8f ETH" % self.total_gas_cost(day_transactions)]

        outgoing_transactions = list(filter(lambda tx: tx['from'].lower() == self.arguments.address.lower(), transactions))

        table = Texttable(max_width=250)
        table.set_deco(Texttable.HEADER)
        table.set_cols_dtype(['t', 't', 't', 't', 't'])
        table.set_cols_align(['l', 'r', 'r', 'r', 'r'])
        table.set_cols_width([11, 15, 25, 20, 20])
        table.add_rows([["Day", "# transactions", "Average gas price", "Average gas cost", "Total gas cost"]]
                       + list(table_data(outgoing_transactions)))

        print(f"")
        print(f"Gas usage summary for: {self.arguments.address}")
        print(f"")
        print(table.draw())
        print(f"")
        print(f"Number of transactions: {len(outgoing_transactions)}")
        print(f"Total gas cost: %.8f ETH" % self.total_gas_cost(transactions))
        print(f"")

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
    def gas_price(transaction: dict) -> int:
        return int(transaction['gasPrice'])

    @staticmethod
    def gas_cost(transaction: dict) -> int:
        return int(transaction['gasUsed']) * int(transaction['gasPrice'])

    def get_transactions(self) -> list:
        with self.get_db() as db:
            print(f"Found {len(db.all())} transactions for '{self.arguments.address}' in local cache.")
            print(f"Fetching new transactions from etherscan.io...")

            while True:
                # Get all existing transactions in the db
                all_transactions = db.all()
                existing_hashes = set(map(lambda tx: tx['hash'], all_transactions))
                max_block_number = max(map(lambda tx: int(tx['blockNumber']), all_transactions)) \
                    if len(all_transactions) > 0 else 0

                # Fetch a new batch of transactions, select only the new ones
                new_transactions = []
                for transaction in self.fetch_transactions(max_block_number):
                    if transaction['hash'] not in existing_hashes:
                        existing_hashes.add(transaction['hash'])
                        new_transactions.append(transaction)

                # Insert new transactions into the db
                db.insert_multiple(new_transactions)

                # We carry on until no new transactions are being discovered
                if len(new_transactions) > 0:
                    print(f"Fetched {len(new_transactions)} new transactions (block number #{max_block_number})...")
                else:
                    print(f"All new transactions fetched from etherscan.io.")
                    break

            return db.all()

    def get_db(self):
        db_folder = user_cache_dir("petrometer", "maker")

        try:
            os.makedirs(db_folder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        db_file = os.path.join(db_folder, self.arguments.address.lower() + ".txdb")
        return TinyDB(db_file, storage=CachingMiddleware(JSONStorage))

    def fetch_transactions(self, start_block: int) -> list:
        assert(isinstance(start_block, int))

        url = f"https://api.etherscan.io/api?module=account&" \
              f"action=txlist&" \
              f"address={self.arguments.address.lower()}&" \
              f"startblock={start_block}&" \
              f"endblock=99999999&" \
              f"page=1&" \
              f"offset=100&" \
              f"sort=asc&" \
              f"apikey={self.arguments.etherscan_api_key}"

        # Always wait some time before sending a request as we do not want to be banned by etherscan.io
        time.sleep(0.2)

        result = requests.get(url, timeout=26).json()
        if result['message'] != 'OK':
            raise Exception(f"Invalid etherscan.io response: {result}")

        return result['result']


if __name__ == '__main__':
    Petrometer(sys.argv[1:]).main()
