#!/usr/bin/python3

import logging
import sys

sys.path.append(r'/home/adam/ibCur')
from market import ibApi

import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--conf', type=str, required=True)
args = parser.parse_args()

ibApi.startGatewayWatchdog(args.conf)
