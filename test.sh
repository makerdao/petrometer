#!/bin/sh

ETHERSCAN_API_KEY=${ETHERSCAN_API_KEY} py.test --cov=petrometer --cov-report=term --cov-append tests/ $@
