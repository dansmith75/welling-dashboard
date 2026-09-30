#!/bin/bash
cd "$(dirname "$0")"
python3 update_welling.py
printf "\nPress any key to close..."
read -n 1 -s
