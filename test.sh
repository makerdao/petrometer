#!/bin/sh

py.test --cov=petrometer --cov-report=term --cov-append tests/
