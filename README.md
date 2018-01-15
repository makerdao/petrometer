# petrometer

[![Build Status](https://travis-ci.org/makerdao/petrometer.svg?branch=master)](https://travis-ci.org/makerdao/petrometer)
[![codecov](https://codecov.io/gh/makerdao/petrometer/branch/master/graph/badge.svg)](https://codecov.io/gh/makerdao/petrometer)

`petrometer` is a tool which summarizes daily and total gas consumption of all transactions sent
from a specified Ethereum address.

It uses the etherscan.io API (<https://etherscan.io/apis>) to download the transaction data as it's
much more effective than querying an Ethereum node directly. What even more, it caches the downloaded
data between invocations and only downloads new transactions when run again. Thanks to `appdirs`
(<https://pypi.python.org/pypi/appdirs>), standard OS locations are used for storing cached data.

You do need an etherscan.io API key (<https://etherscan.io/apis>) in order to use this tool,
it needs to be passed as the `--etherscan-api-key` parameter. You need to create an etherscan.io
account (<https://etherscan.io/register>) in order to be able to generate an API key.

<https://chat.makerdao.com/channel/keeper>

## Installation

This project uses *Python 3.6.2*.

In order to clone the project and install required third-party packages please execute:
```
git clone https://github.com/makerdao/petrometer.git
git submodule update --init --recursive
pip3 install -r requirements.txt
```

## Usage

```
usage: petrometer [-h] --etherscan-api-key ETHERSCAN_API_KEY address

positional arguments:
  address               Ethereum address to get the gas usage of

optional arguments:
  -h, --help            show this help message and exit
  --etherscan-api-key ETHERSCAN_API_KEY
                        Etherscan API key
```

Sample invocation:

```
bin/petrometer --etherscan-api-key ABCDFDBCBAFDBCFBDFCBFDBAFB 0x1212121212343434343456565656565454545454
```

Sample output:

```
Gas usage summary for: 0x00......................................

    Day       # transactions        Average gas price              Average gas cost                  Total gas cost        
===========================================================================================================================
2018-01-06                 12                   39.7 GWei         0.005078854742238021 ETH         0.060946256906856247 ETH
2018-01-07                 22                   22.0 GWei         0.003037521765674030 ETH         0.066825478844828673 ETH
2018-01-08                 76                   27.7 GWei         0.003806332034057282 ETH         0.289281234588353420 ETH

Number of transactions: 351
Total gas cost: 1.526090324569235879 ETH
```

## License

See [COPYING](https://github.com/makerdao/petrometer/blob/master/COPYING) file.
