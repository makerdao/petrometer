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
    def __init__(self, args: list, **kwargs):
        parser = argparse.ArgumentParser(prog='petrometer')
        parser.add_argument("address", help="Ethereum address to get the gas usage of", type=str)
        parser.add_argument("--etherscan-api-key", help="Etherscan API key", required=True, type=str)

        self.arguments = parser.parse_args(args)

    def main(self):
        transactions = self.get_transactions()
        self.print_daily_gas_usage(transactions)

    def print_daily_gas_usage(self, transactions):
        def table_data():
            for day, day_transactions in groupby(transactions, self.by_day):
                day_transactions = list(day_transactions)

                # Calculate some values
                no_of_transactions = len(day_transactions)
                avg_gas_price = self.avg_gas_price(day_transactions)
                avg_gas_cost = self.avg_gas_cost(day_transactions)
                total_gas_cost = self.total_gas_cost(day_transactions)

                yield [day.strftime('%Y-%m-%d'),
                       no_of_transactions,
                       "%.1f GWei" % avg_gas_price,
                       "%.18f ETH" % avg_gas_cost,
                       "%.18f ETH" % total_gas_cost]

        table = Texttable(max_width=250)
        table.set_deco(Texttable.HEADER)
        table.set_cols_dtype(['t', 't', 't', 't', 't'])
        table.set_cols_align(['l', 'r', 'r', 'r', 'r'])
        table.set_cols_width([11, 15, 20, 30, 30])
        table.add_rows([["Day", "# transactions", "Average gas price", "Average gas cost", "Total gas cost"]] + list(table_data()))

        print("")
        print(f"Gas usage summary for: {self.arguments.address}")
        print("")
        print(table.draw())
        print("")
        print("Total gas cost: %.18f ETH" % self.total_gas_cost(transactions))
        print("")

    def avg_gas_price(self, transactions):
        return numpy.mean(list(map(self.gas_price, transactions))) / 10 ** 9

    def avg_gas_cost(self, transactions):
        return numpy.mean(list(map(self.gas_cost, transactions))) / 10 ** 18

    def total_gas_cost(self, transactions):
        result = 0
        for x in map(self.gas_cost, transactions):
            result += x
        return result / 10 ** 18
        # return numpy.sum(list(map(self.gas_cost, transactions))) / 10 ** 18

    @staticmethod
    def by_day(transaction: dict):
        transaction_timestamp = datetime.datetime.fromtimestamp(int(transaction['timeStamp']), tz=pytz.UTC)
        return transaction_timestamp.replace(hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def gas_price(transaction: dict) -> int:
        return int(transaction['gasPrice'])

    @staticmethod
    def gas_cost(transaction: dict) -> int:
        x = int(transaction['gasUsed']) * int(transaction['gasPrice'])
        assert(x > 0)
        return x

    def get_transactions(self) -> list:
        db = self.get_db()

        print(f"Found {len(db.all())} transactions for '{self.arguments.address}' in local cache.")
        print(f"Fetching new transactions from etherscan.io...")

        while True:
            # Get all existing transactions in the db
            all_transactions = db.all()
            max_block_number = max(map(lambda tx: int(tx['blockNumber']), all_transactions)) \
                if len(all_transactions) > 0 else 0

            # Fetch a new batch of transactions
            new_transactions_found = 0
            new_transactions = self.fetch_transactions(max_block_number)
            for transaction in new_transactions:
                Tx = Query()
                if len(db.search(Tx.hash == transaction['hash'])) == 0:
                    db.insert(transaction)
                    new_transactions_found += 1

            # We carry on until no new transactions are being discovered
            if new_transactions_found > 0:
                print(f"Fetched {new_transactions_found} new transactions (block number #{max_block_number})...")
            else:
                print(f"All new transactions fetched from etherscan.io.")
                break

        all_transactions = db.all()

        db.close()

        print(f"Total number of transactions: {len(all_transactions)}.")

        return all_transactions

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
        time.sleep(0.3)

        result = requests.get(url).json()
        if result['message'] != 'OK':
            raise Exception(f"Invalid etherscan.io response: {result}")

        return result['result']


if __name__ == '__main__':
    Petrometer(sys.argv[1:]).main()
