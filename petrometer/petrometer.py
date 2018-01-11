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
import sys

import os

import errno
import requests
import time
from appdirs import user_cache_dir
from tinydb import TinyDB, JSONStorage, Query
from tinydb.middlewares import CachingMiddleware


class Petrometer:
    def __init__(self, args: list, **kwargs):
        parser = argparse.ArgumentParser(prog='petrometer')
        parser.add_argument("address", help="Ethereum address to get the gas usage of", type=str)
        parser.add_argument("--etherscan-api-key", help="Etherscan API key", required=True, type=str)

        self.arguments = parser.parse_args(args)
        self.db = self.get_db()

    def main(self):
        self.refresh_transactions()
        self.db.close()

    def get_db(self):
        db_folder = user_cache_dir("petrometer", "maker")

        try:
            os.makedirs(db_folder)
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise

        db_file = os.path.join(db_folder, self.arguments.address.lower() + ".txdb")
        return TinyDB(db_file, storage=CachingMiddleware(JSONStorage))

    def refresh_transactions(self):
        print(f"Found {len(self.db.all())} transactions for '{self.arguments.address}' in local cache.")
        print(f"Fetching new transactions from etherscan.io...")

        while True:
            # Get all existing transactions in the db
            all_transactions = self.db.all()
            max_block_number = max(map(lambda tx: int(tx['blockNumber']), all_transactions)) if len(all_transactions) > 0 else 0

            # Fetch a new batch of transactions
            new_transactions_found = 0
            transactions = self.get_transactions(max_block_number)
            for transaction in transactions:
                Tx = Query()
                if len(self.db.search(Tx.hash == transaction['hash'])) == 0:
                    self.db.insert(transaction)
                    new_transactions_found += 1

            # We carry on until no new transactions are being discovered
            if new_transactions_found == 0:
                break
            else:
                print(f"Fetched {new_transactions_found} new transactions...")

        print(f"All new transactions fetched from etherscan.io.")
        print(f"Total number of transactions: {len(self.db.all())}.")

    def get_transactions(self, start_block: int):
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
