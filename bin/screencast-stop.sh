#!/bin/bash
cd "$(dirname "$0")/.."
[ -f state/screencast.pid ] && kill "$(cat state/screencast.pid)" 2>/dev/null && echo stopped || echo "not running"
rm -f state/screencast.pid
